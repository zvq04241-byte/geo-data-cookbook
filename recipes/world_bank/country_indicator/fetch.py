"""fetch.py — World Bank Indicators API 国別指標取得

World Bank Indicators API V2 から、指定インジケータを指定国群について
取得し、最新値ランキング or 時系列を CSV + metadata.json に保存する。

使い方:
    # GDP (current US$) の上位30か国ランキング
    python fetch.py --indicator NY.GDP.MKTP.CD --mode ranking --top-n 30 \\
        --output-dir ./output

    # 日本/韓国/中国の人口時系列 (2000-2023)
    python fetch.py --indicator SP.POP.TOTL --mode trend \\
        --countries JPN,KOR,CHN --year-from 2000 --output-dir ./output

このレシピが扱う範囲:
- 単一インジケータ × 国群 × ranking or trend
- 主要50か国デフォルトリスト（カスタム指定可）
- 認証不要（公開API）

このレシピが扱わない範囲:
- 複数インジケータ同時取得 → 別レシピ
- 地域・所得階級別の集計 → 別レシピ
- "country" に Region/IncomeGroup を含む → 本レシピは個別国のみ
"""
import argparse
import csv
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


# ─── 定数 ───
WB_BASE = "https://api.worldbank.org/v2"

# ranking モード時のデフォルト国群（主要 49 か国、ISO3）
# 注意:
#   World Bank API は TWN（台湾）に対し page=0/total=0 を返す（多くの indicator
#   で台湾データは中国に統合される）。50カ国一括クエリ時に TWN を含めると、
#   全体が 4xx エラーになる現象が確認されている（2026-05-23）。
#   → デフォルトリストから TWN を除外。
#   台湾を含めたい場合は --countries で明示的に渡す（ただしデータは空）。
DEFAULT_COUNTRIES = [
    "USA", "CHN", "JPN", "DEU", "IND", "GBR", "FRA", "ITA", "CAN", "BRA",
    "RUS", "KOR", "AUS", "ESP", "MEX", "IDN", "NLD", "TUR", "CHE", "SAU",
    "POL", "ARG", "SWE", "BEL", "THA", "IRL", "ISR", "NOR", "AUT",
    "EGY", "ZAF", "PHL", "DNK", "BGD", "VNM", "MYS", "SGP", "HKG", "ARE",
    "COL", "PAK", "CHL", "FIN", "ROU", "CZE", "PRT", "GRC", "NZL", "KEN",
]


class DataFetchError(Exception):
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


def fetch_wb_indicator(
    indicator: str, countries: list[str],
    *, mrv: int = 10, retries: int = 3, timeout: int = 60,
) -> tuple[list, str]:
    """World Bank Indicators API を叩いて値配列を返す。

    Returns:
        (data_rows, request_url)
        data_rows: [{"countryiso3code": "JPN", "date": "2023", "value": 4.2e12, ...}, ...]

    World Bank API の特殊な仕様:
    - レスポンスは **2要素配列** `[meta, data]`
    - data[0] = メタデータ（page, total等）
    - data[1] = 実際の値配列
    - 1要素しか無い場合はエラー（指標 or 国コード誤り）
    """
    cc_str = ";".join(countries)
    url = f"{WB_BASE}/country/{cc_str}/indicator/{indicator}"

    def _get_page(cl, page):
        # per_page は上限側に大きく取り、さらに pages を辿って全ページ結合する
        params = {"format": "json", "mrv": str(mrv), "per_page": "1000", "page": str(page)}
        r = cl.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or len(data) < 2:
            raise DataFetchError(
                source="World Bank", url=url, kind="UNEXPECTED_RESPONSE",
                message=f"expected [meta, data] but got: {str(data)[:200]}",
            )
        return data[0] or {}, (data[1] or [])

    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout) as cl:
                meta, rows = _get_page(cl, 1)
                pages = int(meta.get("pages") or 1)
                for p in range(2, pages + 1):        # ★2ページ目以降も取得（500件超の欠落防止）
                    _m, more = _get_page(cl, p)
                    rows.extend(more)
            # ★完全性チェック: 取得件数が API メタの total 未満なら黙って欠落させず失敗させる
            total = int(meta.get("total") or len(rows))
            if len(rows) < total:
                raise DataFetchError(
                    source="World Bank", url=url, kind="INCOMPLETE_PAGING",
                    message=f"ページング未完: 取得 {len(rows)} 件 < total {total} 件",
                )
            return rows, url
        except (httpx.HTTPError, DataFetchError) as e:
            # WB は 200 でエラーボディ(id=120)を一時的に返すことがある＝リトライで回復する。
            last_err = e
            logging.warning("fetch retry %d/%d: %s", i + 1, retries, e)

    # リトライ尽き: DataFetchError は実際の種別のまま再送出（HTTP_FAIL で覆い隠さない）
    if isinstance(last_err, DataFetchError):
        raise last_err
    raise DataFetchError(
        source="World Bank", url=url, kind="HTTP_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def latest_per_country(rows: list[dict]) -> dict[str, dict]:
    """各国の最新非null値を抽出。

    World Bank API は古い年から新しい年へ降順ソートされて返るが、
    null も混じる。最新の非null を取得する。
    """
    by_cc: dict[str, dict] = {}
    for r in rows:
        if r.get("value") is None:
            continue
        cc = r.get("countryiso3code", "")
        if not cc:
            continue
        yr = int(r.get("date", "0"))
        if cc not in by_cc or yr > int(by_cc[cc].get("date", "0")):
            by_cc[cc] = r
    return by_cc


def build_ranking(
    by_cc: dict[str, dict], top_n: int, indicator_name: str,
) -> list[dict]:
    rows = []
    sorted_items = sorted(
        by_cc.values(), key=lambda r: float(r.get("value", 0) or 0),
        reverse=True,
    )
    for rank, r in enumerate(sorted_items[:top_n], 1):
        country = r.get("country", {}) if isinstance(r.get("country"), dict) else {}
        rows.append({
            "rank": rank,
            "iso3": r.get("countryiso3code", ""),
            "country": country.get("value", "") if country else r.get("country", ""),
            "year": r.get("date", ""),
            "value": r.get("value"),
            "indicator": r.get("indicator", {}).get("id", "") if isinstance(r.get("indicator"), dict) else indicator_name,
        })
    return rows


def build_trend(
    raw_rows: list[dict], year_from: int,
) -> list[dict]:
    """時系列モード: 国×年 で1行ずつ展開。"""
    out = []
    for r in raw_rows:
        if r.get("value") is None:
            continue
        try:
            yr = int(r.get("date", "0"))
        except ValueError:
            continue
        if yr < year_from:
            continue
        country = r.get("country", {}) if isinstance(r.get("country"), dict) else {}
        out.append({
            "iso3": r.get("countryiso3code", ""),
            "country": country.get("value", "") if country else "",
            "year": yr,
            "value": r.get("value"),
        })
    out.sort(key=lambda x: (x["iso3"], x["year"]))
    return out


def save_csv(rows: list[dict], out_path: Path) -> None:
    if not rows:
        return
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def save_metadata(
    meta_path: Path, *, indicator: str, mode: str, countries: list[str],
    mrv: int, request_url: str, out_csv: Path, row_count: int,
) -> dict:
    meta = {
        "task_name": f"wb_{indicator}_{mode}_{datetime.now().strftime('%Y%m%d')}",
        "source": {
            "name": "World Bank Indicators API V2",
            "url": WB_BASE,
            "request_url": request_url,
            "single_source": True,
        },
        "query": {
            "indicator": indicator,
            "mode": mode,
            "countries": countries,
            "country_count": len(countries),
            "mrv": mrv,
        },
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "missing_value_treatment": "value=null は除外（推測補完なし）",
        "notes": (
            "World Bank API は data[1] が値配列、data[0] はメタ。"
            "各国で最新非null年が異なるため metadata の year 列を必ず確認。"
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
        description="World Bank Indicators 国別取得",
    )
    ap.add_argument("--indicator", required=True,
                    help="WB インジケータコード (例: NY.GDP.MKTP.CD=GDP, SP.POP.TOTL=人口)")
    ap.add_argument("--mode", default="ranking", choices=["ranking", "trend"],
                    help="ranking=最新値順位 / trend=国×年時系列")
    ap.add_argument("--countries", default="",
                    help="ISO3 カンマ区切り (例: JPN,USA,CHN). 省略時は主要50か国")
    ap.add_argument("--top-n", type=int, default=30,
                    help="ranking モードの上位N (default: 30)")
    ap.add_argument("--year-from", type=int, default=2000,
                    help="trend モードの開始年 (default: 2000)")
    ap.add_argument("--mrv", type=int, default=10,
                    help="Most Recent Values の取得年数 (default: 10)")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"),
                    help="出力ディレクトリ")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    countries = (
        [c.strip().upper() for c in args.countries.split(",") if c.strip()]
        if args.countries else DEFAULT_COUNTRIES
    )
    mrv = max(args.mrv, (datetime.now().year - args.year_from + 1)
              if args.mode == "trend" else args.mrv)

    logging.info(
        "WB取得: indicator=%s mode=%s countries=%d mrv=%d",
        args.indicator, args.mode, len(countries), mrv,
    )
    try:
        raw_rows, request_url = fetch_wb_indicator(
            args.indicator, countries, mrv=mrv,
        )
    except DataFetchError as e:
        logging.error("取得失敗: %s", e)
        return 1

    if not raw_rows:
        logging.error(
            "データなし。インジケータコード or 国コードを確認してください。",
        )
        return 1
    logging.info("生レコード: %d 件", len(raw_rows))

    if args.mode == "ranking":
        by_cc = latest_per_country(raw_rows)
        out_rows = build_ranking(by_cc, args.top_n, args.indicator)
        logging.info("各国最新値: %d か国", len(by_cc))
    else:  # trend
        out_rows = build_trend(raw_rows, args.year_from)
        logging.info("時系列レコード: %d 行", len(out_rows))

    if not out_rows:
        logging.error("出力データなし")
        return 1

    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_wb_{args.indicator.replace('.', '_')}_{args.mode}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    save_csv(out_rows, out_csv)
    meta = save_metadata(
        out_meta, indicator=args.indicator, mode=args.mode, countries=countries,
        mrv=mrv, request_url=request_url, out_csv=out_csv,
        row_count=len(out_rows),
    )
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(out_rows), meta["csv_sha256"][:12])

    # サマリ表示
    if args.mode == "ranking":
        print(f"\n== World Bank {args.indicator} Top {args.top_n} ==")
        for r in out_rows[:min(20, len(out_rows))]:
            val = r["value"]
            v_str = f"{val:>18,.0f}" if val and val > 100 else f"{val:>18.3f}"
            print(f"  {r['rank']:>3}  {r['iso3']:<4} {r['country']:<25}  "
                  f"{v_str}  ({r['year']})")
    else:
        print(f"\n== World Bank {args.indicator} trend (since {args.year_from}) ==")
        # 国別に最初の3点だけ表示
        from collections import defaultdict
        by_country = defaultdict(list)
        for r in out_rows:
            by_country[r["iso3"]].append(r)
        for cc, rows in by_country.items():
            print(f"  [{cc}] {rows[0]['country']}: {len(rows)} 年分")
            for r in rows[:3]:
                print(f"    {r['year']}: {r['value']:,.0f}" if r['value'] else f"    {r['year']}: -")
            if len(rows) > 3:
                print(f"    ... (他 {len(rows)-3} 年)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
