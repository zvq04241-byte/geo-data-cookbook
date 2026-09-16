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
    "FRANCE", "GERMANY", "ITALY", "SPAIN", "GBR", "NETHERLANDS",  # UK は ISO3 の GBR（UNITEDKINGDOM は無効→全世界が返る）
    "DENMARK", "SWEDEN", "NORWAY", "FINLAND", "POLAND", "AUSTRIA", "SWITZERLAND",
    "JAPAN", "KOREA", "CHINA", "INDIA", "AUSTRALIA", "TURKEY",
}

# IEA flow コード → 出力列名（発電量・電源別）。EHINDPROD=総生産。
FLOWS = {
    "EHCOAL": "coal", "EHOIL": "oil", "EHNATGAS": "natgas",
    "EHNUCLEAR": "nuclear", "EHYDRO": "hydro", "EWIND": "wind",
    "ESOLARPV": "solar", "EHBIOMASS": "biofuel", "EHGEOTHERM": "geothermal",
    "ETIDE": "tide", "EHMUNWASTR": "munwaste_renew", "EHMUNWAST": "munwaste",
    "EHWASTE": "waste", "EHOTHER": "other_src", "EHINDPROD": "total",
}


class DataFetchError(Exception):
    pass


def _cache_path(cache_dir: Path, code: str) -> Path:
    return cache_dir / f"iea_ELECTRICITYANDHEAT_{code}.json"


def fetch_country_raw(code: str, cache_dir: Path, ttl_days: int, retries: int = 3) -> list:
    """1か国分の生 JSON を取得（mtime ベース TTL キャッシュ）。"""
    if code not in KNOWN_CODES:
        print(f"[warn] 国コード '{code}' は既知リストにありません。IEA表記の大文字フルネームか確認"
              f"（例: GERMANY であって DEUTHERY 等ではない）。", file=sys.stderr)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp = _cache_path(cache_dir, code)
    if cp.exists():
        age_days = (time.time() - cp.stat().st_mtime) / 86400.0
        if age_days <= ttl_days:
            return json.loads(cp.read_text(encoding="utf-8"))
    url = BASE.format(code=urllib.parse.quote(code))
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            if not isinstance(data, list) or not data:
                raise DataFetchError(f"空応答（国コード '{code}' が不正の可能性）")
            cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except Exception as e:  # noqa
            last = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise DataFetchError(f"{code}: 取得失敗 ({last})")


def to_wide(raw: list, year_from: int, year_to: int) -> pd.DataFrame:
    """raw JSON → 年 × 電源(TWh) のワイド表。product=ELECTR のみ。GWh→TWh。"""
    rows = {}
    for r in raw:
        if r.get("product") != "ELECTR":
            continue
        flow = r.get("flow")
        if flow not in FLOWS:
            continue
        v = r.get("value")
        if v is None:
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
    for c in FLOWS.values():
        if c not in df.columns:
            df[c] = 0.0
    df = df.fillna(0.0)
    _sanity_check(df)
    return df


def _sanity_check(df: pd.DataFrame) -> None:
    """正確性ガード: 不正な国コード等によるゴミ応答を検出して落とす。
    総生産(EHINDPROD)に対し、電源内訳の合計が大きく超過していたら不整合（例: DEUTHERY 幻覚）。
    smoke test（構造検査）は通っても中身が壊れている事故を防ぐ。"""
    comp_cols = ["coal", "oil", "natgas", "nuclear", "hydro", "wind", "solar",
                 "biofuel", "geothermal", "tide", "munwaste_renew"]
    comp_sum = df[comp_cols].sum(axis=1)
    bad = df[comp_sum > df["total"] * 1.10 + 1.0]  # 総生産を1割以上超過＝不整合
    if len(bad):
        y = int(bad.iloc[0]["year"])
        raise DataFetchError(
            f"整合性NG: 電源内訳の合計が総生産(EHINDPROD)を超過（{y}年: 内訳計"
            f"{comp_sum[bad.index[0]]:.1f} > 総{bad.iloc[0]['total']:.1f} TWh）。"
            f"国コードが不正な可能性（正しい大文字フルネームか確認。例 GERMANY を DEUTHERY 等に誤らない）。")


def fetch(code: str, year_from: int, year_to: int, out_dir: Path,
          cache_dir: Optional[Path] = None, ttl_days: int = DEFAULT_TTL_DAYS) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "iea"
    raw = fetch_country_raw(code, cache_dir, ttl_days)
    df = to_wide(raw, year_from, year_to)
    y0, y1 = int(df.year.min()), int(df.year.max())
    date = datetime.datetime.now().strftime("%Y%m%d")
    slug = code.lower()
    csv_path = out_dir / f"{date}_iea_electricity_{slug}_{y0}_{y1}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")

    fossil = (df.coal + df.oil + df.natgas)
    meta = {
        "task_name": f"iea_electricity_{slug}_{y0}_{y1}",
        "source": {
            "name": "IEA — Energy Statistics Data Browser",
            "product": "World Energy Statistics & Balances (series=ELECTRICITYANDHEAT, product=ELECTR)",
            "url": BASE.format(code=code),
            "access": "free data browser backend (= manual CSV download と同一データ)",
            "single_source": True,
        },
        "query": {"country_code": code, "year_from": year_from, "year_to": year_to,
                  "flows": list(FLOWS.keys())},
        "units": "TWh (source GWh; 1 TWh = 10^9 kWh). gross production (EHINDPROD).",
        "fetched_at": datetime.datetime.now().astimezone().isoformat(),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "row_count": int(len(df)),
        "year_range_actual": f"{y0}-{y1}",
        "missing_value_treatment": "value=null は欠損として skip（0埋めしない）。総生産=EHINDPROD。",
        "notes": "IEA一次データ単独。IEA無料APIプロダクト MES(api.iea.org/mes)は2010–月次のみ。"
                 "1990–の年次はこのデータブラウザ経路で取得。gross（総生産）。最新確定年はおおむね当年-2。",
    }
    (out_dir / f"{csv_path.stem}_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {code}: {y0}-{y1} ({len(df)}年) -> {csv_path.name}")
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
