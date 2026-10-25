#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IEA Energy Statistics Data Browser から国別・電源別の年次発電量 (1990–) を取得する。

無料のデータブラウザ・バックエンド（手動 CSV ダウンロードと同一データ）を叩く：
    https://api.iea.org/stats?series=ELECTRICITYANDHEAT&countries=<CODE>
product="ELECTR" の行（電力。"HEAT" は熱）を抽出し、年 × 電源(flow) のワイド表(TWh)に整形して
CSV + metadata.json に保存する。単位は原系列 GWh → TWh 換算。

例:
    python fetch.py --countries USA,FRANCE,GERMANY --year-from 1990 --year-to 2024 --output-dir ./output
    python fetch.py --countries JAPAN --output-dir ./output

注意: IEA の有料 API プロダクト Monthly Electricity Statistics (api.iea.org/mes) は 2010– の月次のみ。
1990– の年次・電源別はこのデータブラウザ経路で無料取得できる（詳細 docs/api_notes/iea.md）。
Python 3.9 互換（型に X | None を使わない）。
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://api.iea.org/stats?series=ELECTRICITYANDHEAT&countries={code}"
DEFAULT_TTL_DAYS = 30

# 既知の正しい国コード（大文字フルネーム）。LLM が "DEUTHERY" 等に幻覚するのを防ぐための参照。
# 網羅ではない。ここに無い国は IEA の表記を確認してから追加すること。
KNOWN_CODES = {
    "USA", "CANADA", "MEXICO", "BRAZIL",
    "FRANCE", "GERMANY", "ITALY", "SPAIN", "GBR", "NETHERLANDS",  # UK は GBR。UNITEDKINGDOM は無効→179か国＋WORLD の全件が返る（2026-10-26 実測）
    "DENMARK", "SWEDEN", "NORWAY", "FINLAND", "POLAND", "AUSTRIA", "SWITZERLAND",
    "JAPAN", "KOREA", "CHINA", "INDIA", "AUSTRALIA", "TURKEY",
}

# IEA flow コード → 出力列名（発電量・電源別）。EHINDPROD=総生産。
# ★廃棄物は入れ子: EHWASTE(Waste 全体) ⊃ EHMUNWAST(Municipal waste) ⊃ EHMUNWASTR(同 renewable)。
FLOWS = {
    "EHCOAL": "coal", "EHOIL": "oil", "EHNATGAS": "natgas",
    "EHNUCLEAR": "nuclear", "EHYDRO": "hydro", "EWIND": "wind",
    "ESOLARPV": "solar", "EHSOLARTH": "solar_thermal", "EHBIOMASS": "biofuel", "EHGEOTHERM": "geothermal",
    "ETIDE": "tide", "EHMUNWASTR": "munwaste_renew", "EHMUNWAST": "munwaste",
    "EHWASTE": "waste", "EHOTHER": "other_src", "EHINDPROD": "total",
}
# 総生産の恒等式に使う、重ならない電源の集合（廃棄物は EHWASTE だけを数える）。
# 2026-10-26 実測（USA・GBR・DENMARK・JAPAN 1990–2025）で 合計/総生産 の差は最大 0.02%。
IDENTITY_COLS = ["coal", "oil", "natgas", "nuclear", "hydro", "wind", "solar", "solar_thermal",
                 "biofuel", "geothermal", "tide", "waste", "other_src"]
IDENTITY_TOL = 0.01   # 総生産の1%（実測の差 0.02% に十分な余裕。ゴミ応答は桁で外れる）


class DataFetchError(Exception):
    pass


def _cache_path(cache_dir: Path, code: str) -> Path:
    if not re.fullmatch(r"[A-Z0-9]+", code):
        raise DataFetchError(f"国コード '{code}' は英大文字・数字だけで書く（例 GERMANY, GBR）")
    return cache_dir / f"iea_ELECTRICITYANDHEAT_{code}.json"


def _check_one_country(data: list, code: str) -> None:
    """★不正な国コードは空でなく**全世界（179か国＋WORLD）**が返る（UNITEDKINGDOM・UNITEDSTATES・DEUTHERY で実測）。
    応答の country 列が1種類でなければ落とす。"""
    cs = {r.get("country") for r in data}
    if len(cs) != 1:
        raise DataFetchError(f"国コード '{code}' の応答に {len(cs)} か国が入っている（不正なコードで全件が返った）。"
                             f"英国は GBR、米国は USA")


def fetch_country_raw(code: str, cache_dir: Path, ttl_days: int, retries: int = 3) -> list:
    """1か国分の生 JSON を取得（mtime ベース TTL キャッシュ）。"""
    if code not in KNOWN_CODES:
        print(f"[warn] 国コード '{code}' は既知リストにありません。IEA表記の大文字フルネームか確認"
              f"（例: GERMANY であって DEUTHERY 等ではない）。", file=sys.stderr)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(cache_dir, code)
    if cp.exists():
        age_days = (time.time() - cp.stat().st_mtime) / 86400.0
        if 0 <= age_days <= ttl_days:          # mtime が未来（コピー等）なら期限切れ扱い
            try:
                data = json.loads(cp.read_text(encoding="utf-8"))
                _check_one_country(data, code)
                return data
            except (json.JSONDecodeError, DataFetchError) as e:
                print(f"[warn] キャッシュを使わず取り直す（{e}）", file=sys.stderr)
    url = BASE.format(code=urllib.parse.quote(code))
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            if not isinstance(data, list) or not data:
                raise DataFetchError(f"空応答（国コード '{code}' が不正の可能性）")
            _check_one_country(data, code)
            cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except DataFetchError:
            raise                                   # 不正なコードはリトライしても同じ
        except Exception as e:  # noqa
            last = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise DataFetchError(f"{code}: 取得失敗 ({last})")


def to_wide(raw: list, year_from: int, year_to: int, stats: Optional[dict] = None) -> pd.DataFrame:
    """raw JSON → 年 × 電源(TWh) のワイド表。product=ELECTR のみ。GWh→TWh。
    ★欠損は空欄（NaN）のまま残す。0 で埋めない。stats に null の件数・応答に無い電源を記録する。"""
    rows = {}
    n_null = 0
    for r in raw:
        if r.get("product") != "ELECTR":
            continue
        flow = r.get("flow")
        if flow not in FLOWS:
            continue
        v = r.get("value")
        if v is None:
            n_null += 1
            continue
        y = int(r["year"])
        if y < year_from or y > year_to:
            continue
        rows.setdefault(y, {})[FLOWS[flow]] = float(v) / 1000.0
    if not rows:
        raise DataFetchError("ELECTR 行が抽出できませんでした")
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    df.index.name = "year"
    df = df.reset_index()
    absent = [c for c in FLOWS.values() if c not in df.columns]
    for c in absent:
        df[c] = float("nan")                 # 応答に行が無い電源。0 とは書かない
    df = df[["year"] + list(FLOWS.values())]
    # 行の無い電源がある年（太陽光の始まる前など。0 か欠損かは応答からは分からない）。最新年の欠けもここに出る
    n_present = df[list(FLOWS.values())].notna().sum(axis=1)
    incomplete = [int(y) for y, n in zip(df.year, n_present) if n < n_present.max()]
    if stats is not None:
        stats.update({"null_values_skipped": n_null, "flows_absent_in_response": absent,
                      "years_with_fewer_flows": incomplete})
    _sanity_check(df)
    return df


def _sanity_check(df: pd.DataFrame) -> None:
    """正確性ガード（両側）: 重ならない電源の合計（IDENTITY_COLS）＝総生産(EHINDPROD) を年ごとに確かめる。
    過大・過小のどちらに外れても落とす。総生産が無い年も落とす。"""
    if df["total"].isna().any():
        raise DataFetchError(f"総生産(EHINDPROD)が無い年がある: {df.year[df.total.isna()].tolist()}")
    comp_sum = df[IDENTITY_COLS].sum(axis=1, skipna=True)
    dev = (comp_sum - df["total"]).abs()
    bad = df[dev > df["total"].abs() * IDENTITY_TOL + 0.01]
    if len(bad):
        i = bad.index[0]
        raise DataFetchError(
            f"整合性NG: 電源の合計が総生産(EHINDPROD)と合わない（{int(df.year[i])}年: 合計"
            f"{comp_sum[i]:.1f} / 総{df.total[i]:.1f} TWh、許容 {IDENTITY_TOL:.0%}）。")


def fetch(code: str, year_from: int, year_to: int, out_dir: Path,
          cache_dir: Optional[Path] = None, ttl_days: int = DEFAULT_TTL_DAYS) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "iea"
    raw = fetch_country_raw(code, cache_dir, ttl_days)
    stats = {}
    df = to_wide(raw, year_from, year_to, stats)
    y0, y1 = int(df.year.min()), int(df.year.max())
    date = datetime.datetime.now().strftime("%Y%m%d")
    slug = code.lower()
    csv_path = out_dir / f"{date}_iea_electricity_{slug}_{y0}_{y1}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")

    fossil = df[["coal", "oil", "natgas"]].sum(axis=1, min_count=1)
    meta = {
        "task_name": f"iea_electricity_{slug}_{y0}_{y1}",
        "source": {
            "name": "IEA — Energy Statistics Data Browser",
            "product": "World Energy Statistics & Balances (series=ELECTRICITYANDHEAT, product=ELECTR)",
            "url": BASE.format(code=code),
            "access": "free data browser backend (= manual CSV download と同一データ)",
            "single_source": True,
        },
        "query": {"country_code": code, "year_from": year_from, "year_to_requested": year_to,
                  "flows": list(FLOWS.keys())},
        "scope": f"1か国（{code}）・{y0}–{y1}年（要求 {year_from}–{year_to}。実際にある年まで）",
        "units": "TWh (source GWh; 1 TWh = 10^9 kWh). gross production (EHINDPROD).",
        "fetched_at": datetime.datetime.now().astimezone().isoformat(),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "row_count": int(len(df)),
        "year_range_actual": f"{y0}-{y1}",
        "missing_value_treatment": "value=null は欠損として空欄（0埋めしない）。応答に行が無い電源も空欄。総生産=EHINDPROD。",
        "missing_values": stats,
        "verification": {"identity": "coal+oil+natgas+nuclear+hydro+wind+solar+solar_thermal+biofuel+geothermal+tide+waste+other_src = total",
                         "tolerance": f"{IDENTITY_TOL:.0%} of total", "result": "OK（全年）"},
        "notes": "IEA一次データ単独。IEA無料APIプロダクト MES(api.iea.org/mes)は2010–月次のみ。"
                 "1990–の年次はこのデータブラウザ経路で取得。gross（総生産）。"
                 "最新年は電源が欠けることがある（missing_values.years_with_fewer_flows）。"
                 "廃棄物は入れ子（waste ⊃ munwaste ⊃ munwaste_renew）なので積み上げで重ねない。",
    }
    (out_dir / f"{csv_path.stem}_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {code}: {y0}-{y1} ({len(df)}年) -> {csv_path.name}")
    if stats["flows_absent_in_response"] or stats["years_with_fewer_flows"] or stats["null_values_skipped"]:
        print(f"   空欄: 応答に無い電源 {stats['flows_absent_in_response']} / 電源が欠ける年 "
              f"{stats['years_with_fewer_flows']} / null {stats['null_values_skipped']}件")
    print(f"   最新年 化石={fossil.iloc[-1]:.1f} 原子力={df.nuclear.iloc[-1]:.1f} "
          f"水力={df.hydro.iloc[-1]:.1f} 風力={df.wind.iloc[-1]:.1f} "
          f"太陽光={df.solar.iloc[-1]:.1f} 総={df.total.iloc[-1]:.1f} TWh")
    return csv_path


def main() -> int:
    ap = argparse.ArgumentParser(description="IEA データブラウザ：国別・電源別 年次発電量取得")
    ap.add_argument("--countries", required=True,
                    help="IEA国コード カンマ区切り（大文字フルネーム。例: USA,FRANCE,GERMANY,DENMARK,SWEDEN,JAPAN）")
    ap.add_argument("--year-from", type=int, default=1990)
    ap.add_argument("--year-to", type=int, default=2100)
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path, default=None)
    ap.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    args = ap.parse_args()
    codes = [c.strip() for c in args.countries.split(",") if c.strip()]
    rc = 0
    for code in codes:
        try:
            fetch(code, args.year_from, args.year_to, args.output_dir, args.cache_dir, args.ttl_days)
        except DataFetchError as e:
            print(f"!! {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
