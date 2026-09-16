"""fetch.py — UN Comtrade 貿易相手国ランキング取得

UN Comtrade Public Preview API から、指定国の特定HS品目について、
貿易相手国の上位N国を取得して CSV + metadata.json に保存する。

使い方:
    # 日本の小麦 (HS=1001) 輸入 2023年 上位5カ国
    python fetch.py --reporter 392 --hs 1001 --flow M --year 2023 --top-n 5 \\
        --output-dir ./output

    # アメリカの自動車 (HS=8703) 輸出 2022年 上位10カ国
    python fetch.py --reporter 842 --hs 8703 --flow X --year 2022 --top-n 10

    # 輸入が500件で打ち切られる広範な品目 → 逆引き集計で相手国を復元
    python fetch.py --reporter 392 --hs TOTAL --flow M --year 2023 --reverse on

このレシピが扱う範囲:
- 特定国 × 特定HS品目 × 特定年 × 輸出 or 輸入 × 相手国ランキング
- 認証不要（Public Preview API）
- **500件打ち切り対応**: 輸入が打ち切られた場合、主要輸出国の対象国向け輸出を合算する
  逆引き集計（--reverse auto/on）で相手国ランキングを復元（輸出国側の値＝輸入国側と非対称）

このレシピが扱わない範囲:
- 多年時系列 → 別レシピ
- HS 2桁レベルでの集計 → cmdCode=TOTAL や 別レシピで
"""
from __future__ import annotations  # py3.9 で PEP604 `X | None` 注釈を使うため

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd


# ─── 定数 ───
COMTRADE_BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

# M49 country code → 表示用日本語名（教材用）
COUNTRY_M49_JP = {
    "392": "日本",     "156": "中国",        "842": "アメリカ",
    "276": "ドイツ",   "528": "オランダ",    "410": "韓国",
    "251": "フランス", "381": "イタリア",    "56":  "ベルギー",
    "826": "イギリス", "124": "カナダ",      "484": "メキシコ",
    "356": "インド",   "724": "スペイン",    "616": "ポーランド",
    "203": "チェコ",   "756": "スイス",      "40":  "オーストリア",
    "752": "スウェーデン", "643": "ロシア",  "764": "タイ",
    "360": "インドネシア", "702": "シンガポール", "704": "ベトナム",
    "458": "マレーシア", "608": "フィリピン", "36":  "オーストラリア",
    "554": "ニュージーランド", "76": "ブラジル", "32": "アルゼンチン",
    "804": "ウクライナ",
}

# 逆引き集計用の世界主要輸出国（M49）。500件打ち切り時に各国の対象国向け輸出を合算する。
# 工業国に加え、農産物の主要輸出国（豪・伯・亜・ウクライナ）も含める。
MAJOR_EXPORTERS = [
    156, 842, 276, 392, 528, 410, 251, 381,
    56, 826, 124, 484, 356, 724, 616, 203,
    756, 40, 752, 643, 764, 360, 702, 704,
    36, 76, 32, 804,
]


class DataFetchError(Exception):
    """データ取得失敗時の構造化例外。"""

    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source = source
        self.url = url
        self.kind = kind
        self.original = original


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_comtrade(
    reporter: str, cmd_code: str, flow: str, year: int,
    *, partner: str | None = None,
    max_records: int = 500, retries: int = 3, timeout: int = 60,
) -> tuple[list, str]:
    """UN Comtrade Public Preview API を叩いて raw レコード配列を返す。

    partner を指定すると相手国を絞り込む（逆引き集計で使用）。

    Returns:
        (records, request_url)

    Raises:
        DataFetchError: API障害・タイムアウト等で取得不能の場合
    """
    params = {
        "reportercode": reporter,
        "flowCode": flow,
        "period": str(year),
        "cmdCode": cmd_code,
        "maxRecords": str(max_records),
        "format": "JSON",
        "includeDesc": "True",
        "customsCode": "C00",   # General customs procedure (default)
        "motCode": "0",         # All modes of transport
    }
    if partner is not None:
        params["partnerCode"] = partner
    url = COMTRADE_BASE + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout) as cl:
                r = cl.get(
                    COMTRADE_BASE, params=params,
                    headers={"User-Agent": "cookbook-comtrade/1.0"},
                )
                r.raise_for_status()
                return r.json().get("data", []), url
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("fetch retry %d/%d: %s", i + 1, retries, e)

    raise DataFetchError(
        source="UN Comtrade", url=url, kind="HTTP_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def aggregate_by_partner(records: list, reporter_int: int, top_n: int) -> pd.DataFrame:
    """相手国別に集計してランキング DataFrame を返す。

    - partnerCode=0 (World) と partnerCode=reporter（自国）は除外
    - 金額は cifvalue（輸入の場合）or fobvalue（輸出の場合）を採用、
      無い方にフォールバック
    """
    by_partner: dict[int, dict] = {}
    for rec in records:
        pc = rec.get("partnerCode")
        if pc == 0 or pc is None or pc == reporter_int:
            continue
        if pc not in by_partner:
            by_partner[pc] = {
                "partner_code": pc,
                "partner_desc": rec.get("partnerDesc", str(pc)),
                "qty": 0.0,
                "value_usd": 0.0,
            }
        by_partner[pc]["qty"] += rec.get("qty") or 0
        by_partner[pc]["value_usd"] += (
            rec.get("cifvalue") or rec.get("fobvalue") or 0
        )

    if not by_partner:
        return pd.DataFrame()

    df = pd.DataFrame(by_partner.values())
    df = df.sort_values("value_usd", ascending=False).head(top_n).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    df["partner_jp"] = df["partner_code"].astype(str).map(COUNTRY_M49_JP).fillna("")
    return df[["rank", "partner_code", "partner_desc", "partner_jp", "qty", "value_usd"]]


def reverse_lookup_imports(
    reporter: str, cmd_code: str, year: int, top_n: int, *, timeout: int = 60,
) -> tuple[pd.DataFrame, float]:
    """500件打ち切り対策の逆引き集計（輸入のみ）。

    各主要輸出国(MAJOR_EXPORTERS)の「対象国(reporter)向け輸出(flow=X)」を引き、
    fobvalue を相手国ごとに合算してランキングする。
    輸入統計が打ち切られても、相手国側の輸出統計から相手国ランキングを復元できる。

    Returns:
        (df, world_val_reverse) — df は aggregate_by_partner と同じ列構成
    """
    reporter_int = int(reporter)
    targets = [e for e in MAJOR_EXPORTERS if e != reporter_int]
    by_partner: dict[int, dict] = {}
    dropped: list[int] = []          # 取得失敗で欠落した輸出国（カバレッジ記録用）
    for exporter in targets:
        try:
            recs, _ = fetch_comtrade(
                str(exporter), cmd_code, "X", year,
                partner=str(reporter), timeout=timeout,
            )
        except DataFetchError as e:
            logging.warning("逆引きスキップ exporter=%d: %s", exporter, e)
            dropped.append(exporter)
            continue
        # 対象国向け(partnerCode==reporter)の fobvalue を合算
        val = sum((x.get("fobvalue") or 0)
                  for x in recs if x.get("partnerCode") == reporter_int)
        if val <= 0:
            continue
        name = next((x.get("reporterDesc", str(exporter)) for x in recs), str(exporter))
        by_partner[exporter] = {
            "partner_code": exporter, "partner_desc": name,
            "qty": 0.0, "value_usd": float(val),
        }
    if not by_partner:
        return pd.DataFrame(), 0.0
    # ★カバレッジを明示：world_val_reverse は「取得できた輸出国の合算」であり全世界合計ではない。
    #   欠落国があると share 計算の分母が過小＝各国シェアが過大になるため、metadata へ残せるよう記録。
    n_ok, n_tgt = len(by_partner), len(targets)
    if dropped:
        logging.warning("逆引きカバレッジ %d/%d 国（欠落 %d: %s）。world_val_reverse は取得分の合算で"
                        "全世界合計ではない＝シェアは過大になり得る。",
                        n_ok, n_tgt, len(dropped), dropped)
    world_val_reverse = sum(v["value_usd"] for v in by_partner.values())
    df = pd.DataFrame(by_partner.values())
    df = df.sort_values("value_usd", ascending=False).head(top_n).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    df["partner_jp"] = df["partner_code"].astype(str).map(COUNTRY_M49_JP).fillna("")
    df.attrs["coverage"] = {"targets": n_tgt, "obtained": n_ok,
                            "dropped": dropped, "is_world_total": not dropped}
    return (df[["rank", "partner_code", "partner_desc", "partner_jp", "qty", "value_usd"]],
            world_val_reverse)


def extract_world_total(records: list) -> dict:
    """World (partnerCode=0) 行から合計値を抽出。"""
    world_row = next((r for r in records if r.get("partnerCode") == 0), None)
    if not world_row:
        return {"qty": 0, "value_usd": 0}
    return {
        "qty": world_row.get("qty") or 0,
        "value_usd": (
            world_row.get("cifvalue") or world_row.get("fobvalue") or 0
        ),
    }


def save_metadata(
    meta_path: Path, *, reporter: str, cmd_code: str, flow: str, year: int,
    top_n: int, request_url: str, out_csv: Path, row_count: int,
    record_count: int, truncated: bool, world_total: dict,
    used_reverse: bool = False,
) -> dict:
    flow_label = {"M": "輸入", "X": "輸出"}.get(flow.upper(), flow)
    meta = {
        "task_name": f"comtrade_{flow.lower()}_{reporter}_hs{cmd_code}_{year}_top{top_n}",
        "source": {
            "name": "UN Comtrade Public Preview API",
            "url": COMTRADE_BASE,
            "single_source": True,
        },
        "query": {
            "reporter_m49": reporter,
            "reporter_jp": COUNTRY_M49_JP.get(reporter, ""),
            "cmd_code_hs": cmd_code,
            "flow": flow.upper(),
            "flow_label": flow_label,
            "year": year,
            "top_n": top_n,
            "request_url": request_url,
        },
        "units": "qty: physical units (varies by HS), value_usd: US dollar",
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "api_record_count": record_count,
        "api_truncated_at_500": truncated,
        "used_reverse_lookup": used_reverse,
        "world_total": world_total,
        "missing_value_treatment": "公表値なしは0として加算（cifvalue/fobvalueのフォールバックあり）",
        "notes": (
            "貿易相手国ランキング。partnerCode=0(World) と自国は除外。"
            "500件打ち切り時は逆引き集計（主要輸出国の対象国向け輸出を合算）で相手国を復元する"
            "（--reverse auto/on）。used_reverse_lookup=true の行は逆引き推計値。"
        ),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(
        description="UN Comtrade 貿易相手国ランキング取得",
    )
    ap.add_argument("--reporter", required=True,
                    help="報告国の M49 コード (例: 392=日本, 842=米国)")
    ap.add_argument("--hs", required=True,
                    help="HS 品目コード (例: 1001=小麦, 8703=乗用車, TOTAL=全品目)")
    ap.add_argument("--flow", default="M", choices=["M", "X", "m", "x"],
                    help="M=輸入, X=輸出 (default: M)")
    ap.add_argument("--year", type=int, required=True,
                    help="対象年 (例: 2023)")
    ap.add_argument("--top-n", type=int, default=10,
                    help="上位N (default: 10)")
    ap.add_argument("--reverse", default="auto", choices=["auto", "on", "off"],
                    help="逆引き集計(輸入のみ): auto=500件打ち切り時のみ / on=常時 / off=しない")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"),
                    help="出力ディレクトリ")
    args = ap.parse_args()

    # Win cmd.exe (CP932) 対策
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    flow = args.flow.upper()
    reporter_int = int(args.reporter)

    # ─── API取得 ───
    logging.info(
        "Comtrade取得: reporter=%s(%s) hs=%s flow=%s year=%d",
        args.reporter, COUNTRY_M49_JP.get(args.reporter, "?"),
        args.hs, flow, args.year,
    )
    try:
        records, request_url = fetch_comtrade(
            args.reporter, args.hs, flow, args.year,
        )
    except DataFetchError as e:
        logging.error("取得失敗: %s", e)
        return 1

    if not records:
        logging.error(
            "データなし: reporter=%s hs=%s flow=%s year=%d",
            args.reporter, args.hs, flow, args.year,
        )
        return 1

    truncated = len(records) >= 500

    # ─── 集計（逆引き判定）───
    world_total = extract_world_total(records)
    df = aggregate_by_partner(records, reporter_int, args.top_n)
    used_reverse = False

    do_reverse = flow == "M" and (
        args.reverse == "on" or (args.reverse == "auto" and truncated)
    )
    if do_reverse:
        logging.info("逆引き集計を実行: 主要輸出国の対象国向け輸出を合算")
        df_rev, world_val_rev = reverse_lookup_imports(
            args.reporter, args.hs, args.year, args.top_n,
        )
        if not df_rev.empty:
            df = df_rev
            used_reverse = True
            # 逆引き時はシェア整合のため World 合計も逆引き合計に統一
            # （輸出国側報告値で揃える。輸入国側 World とは非対称で食い違うため）
            world_total = {"qty": 0, "value_usd": world_val_rev}
        else:
            logging.warning("逆引きで相手国を復元できず、直接取得結果を使用")

    if df.empty:
        logging.error("相手国データが集計できませんでした")
        return 1
    if truncated and not used_reverse:
        logging.warning("API が500件で打ち切られています。シェアは不正確な可能性あり")

    # ─── 出力 ───
    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_comtrade_{flow.lower()}_{args.reporter}_hs{args.hs}_{args.year}_top{args.top_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    df.to_csv(out_csv, index=False, encoding="utf-8")
    meta = save_metadata(
        out_meta,
        reporter=args.reporter, cmd_code=args.hs, flow=flow, year=args.year,
        top_n=args.top_n, request_url=request_url,
        out_csv=out_csv, row_count=len(df),
        record_count=len(records), truncated=truncated, world_total=world_total,
        used_reverse=used_reverse,
    )
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(df), meta["csv_sha256"][:12])
    logging.info("metadata: %s", out_meta)

    # ─── サマリ表示 ───
    flow_label = "輸入" if flow == "M" else "輸出"
    reporter_name = COUNTRY_M49_JP.get(args.reporter, f"M49={args.reporter}")
    print(f"\n== UN Comtrade {reporter_name} HS{args.hs} {flow_label} "
          f"Top {args.top_n} ({args.year}) ==")
    # 注: qty 単位は HS コードによって異なる（kg / tonnes / 個数 など）
    # qtyUnitAbbr 列で確認すること。下記は USD 表示のみ
    if world_total["value_usd"] > 0:
        print(f"  合計: ${world_total['value_usd']/1e6:,.0f}百万USD  "
              f"(qty raw: {world_total['qty']:,.0f} — 単位はAPI仕様参照)")
    print()
    for _, row in df.iterrows():
        name = row["partner_jp"] or row["partner_desc"]
        share = (row["value_usd"] / world_total["value_usd"] * 100
                 if world_total["value_usd"] > 0 else 0)
        print(f"  {row['rank']:>2}  {name:<25}  "
              f"${row['value_usd']/1e6:>10,.0f}M  ({share:>5.1f}%)")

    if used_reverse:
        print("\n  ※ 逆引き集計（相手国の輸出データから復元）を使用。500件打ち切りを回避。")
    elif truncated:
        print("\n  ⚠ APIが500件で打ち切られています。--reverse on で逆引き集計できます。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
