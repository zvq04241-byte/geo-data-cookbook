#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — AQUASTAT 国別 水資源賦存量（国内IRWR・総TRWR・1人当たり）。

AQUASTAT のネイティブ API/バルクは公開エンドポイントが辿りにくいため、
**World Bank Data360 の FAO_AS（AQUASTAT ミラー）** を取得層に使う。
指標コードは FAO_AS_<AQUASTAT変数ID>。

取得指標:
  - 総 TRWR  = FAO_AS_4188  (Total renewable water resources, 10^9 m3/yr)
  - 国内IRWR = FAO_AS_4157  (Total internal renewable water resources, 10^9 m3/yr)
  - 総人口   = FAO_AS_4104  (Total population, 10^3 inhabitants)
1人当たり(総)は Data360 に無い(4174 は空)ため、TRWR と総人口から算出する。

使い方:
    python fetch.py --countries EGY,SAU,PAK,NGA --year 2022 --output-dir ./output
    python fetch.py --countries EGY,SAU,PAK,NGA            --output-dir ./output   # 各指標の最新年

出力: <date>_aquastat_water_resources.csv ＋ _metadata.json
"""
import argparse, json, urllib.request, urllib.error, sys, io, csv, hashlib, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API = "https://data360api.worldbank.org/data360/data"
DB = "FAO_AS"
IND_TRWR = "FAO_AS_4188"   # 総 renewable (km3/yr)
IND_IRWR = "FAO_AS_4157"   # ★総 internal renewable。4187 ではない（下記ハマり所2）
IND_POP = "FAO_AS_4104"    # 総人口 (10^3 inhab)

# ISO3 → 日本語名（必要分のみ。未知は ISO3 をそのまま使う）
JP = {"EGY": "エジプト", "SAU": "サウジアラビア", "PAK": "パキスタン",
      "NGA": "ナイジェリア", "IRQ": "イラク", "IND": "インド", "ETH": "エチオピア",
      "COD": "コンゴ民主共和国", "BGD": "バングラデシュ", "DZA": "アルジェリア"}


class DataFetchError(Exception):
    pass


def _get_json(indicator, ref_area, retries=3):
    """Data360 data API を叩いて value 配列を返す。HTTPエラーは最大3回リトライ。"""
    url = f"{API}?DATABASE_ID={DB}&INDICATOR={indicator}&REF_AREA={ref_area}"
    last = None
    for i in range(retries):
        try:
            # ★User-Agent 必須: 付けないと Data360 は 403 Forbidden を返す
            req = urllib.request.Request(url, headers={
                "Accept": "application/json", "User-Agent": "Mozilla/5.0 (aquastat-fetch)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read()).get("value", [])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise DataFetchError(f"{indicator}/{ref_area}: {last}")


def _pick(values, year):
    """指定年の観測値を返す。無指定/不在なら LATEST_DATA→最新 TIME_PERIOD。"""
    if not values:
        return None
    if year:
        yv = [v for v in values if v.get("TIME_PERIOD") == str(year)]
        if yv:
            return yv[0]
    flagged = [v for v in values if v.get("LATEST_DATA")]
    if flagged:
        return max(flagged, key=lambda v: int(v["TIME_PERIOD"]))
    return max(values, key=lambda v: int(v["TIME_PERIOD"]))


def _scaled(obs):
    """OBS_VALUE(文字列) × 10^UNIT_MULT を float で返す。"""
    return float(obs["OBS_VALUE"]) * (10 ** int(obs["UNIT_MULT"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="EGY,SAU,PAK,NGA", help="ISO3 のカンマ区切り")
    ap.add_argument("--year", default=None, help="対象年（未指定なら各指標の最新）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows, years_used = [], set()
    for iso in [c.strip().upper() for c in args.countries.split(",") if c.strip()]:
        trwr_o = _pick(_get_json(IND_TRWR, iso), args.year)
        irwr_o = _pick(_get_json(IND_IRWR, iso), args.year)
        pop_o = _pick(_get_json(IND_POP, iso), args.year)
        if not (trwr_o and irwr_o and pop_o):
            print(f"  WARN: {iso} は一部指標が欠損（skip）")
            continue
        trwr = _scaled(trwr_o)        # m3/yr
        irwr = _scaled(irwr_o)        # m3/yr
        pop = _scaled(pop_o)          # inhabitants
        ext = trwr - irwr
        # ★1人当たり = 総水資源(m3) ÷ 人口(人)。指標年が指標間でずれうるので年も記録
        per_cap = trwr / pop if pop else None
        rows.append({
            "iso3": iso, "country": JP.get(iso, iso),
            "irwr_km3": round(irwr / 1e9, 1),          # 10^9 m3 = km3
            "trwr_km3": round(trwr / 1e9, 1),
            "external_km3": round(ext / 1e9, 1),
            "external_pct": round(ext / trwr * 100, 0) if trwr else None,
            "population_million": round(pop / 1e6, 1),
            "trwr_per_capita_m3": round(per_cap, 0) if per_cap else None,
            "year_trwr": trwr_o["TIME_PERIOD"], "year_irwr": irwr_o["TIME_PERIOD"],
            "year_pop": pop_o["TIME_PERIOD"],
            "obs_status_trwr": trwr_o.get("OBS_STATUS"),
        })
        years_used.update({trwr_o["TIME_PERIOD"], irwr_o["TIME_PERIOD"], pop_o["TIME_PERIOD"]})

    if not rows:
        raise DataFetchError("有効な行が1つも取得できなかった")

    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    cols = ["iso3", "country", "irwr_km3", "trwr_km3", "external_km3", "external_pct",
            "population_million", "trwr_per_capita_m3", "year_trwr", "year_irwr",
            "year_pop", "obs_status_trwr"]
    out_csv = args.output_dir / f"{today}_aquastat_water_resources.csv"
    with open(out_csv, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)

    meta = {
        "source": "FAO AQUASTAT via World Bank Data360 (DATABASE_ID=FAO_AS)",
        "indicators": {"TRWR": IND_TRWR, "IRWR": IND_IRWR, "population": IND_POP,
                       "per_capita": "computed = TRWR / population (4174 is empty in Data360)"},
        "api": API, "countries": [r["iso3"] for r in rows],
        "years_in_data": sorted(years_used), "rows": len(rows),
        "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "retrieved_at": datetime.now(JST).isoformat(),
    }
    (args.output_dir / f"{today}_aquastat_water_resources_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_csv.name}  rows={len(rows)}")
    for r in rows:
        print(f"  {r['country']:<10} IRWR={r['irwr_km3']:>6} TRWR={r['trwr_km3']:>6} "
              f"外来={r['external_pct']:>3.0f}%  1人当={r['trwr_per_capita_m3']:>6.0f} m3")


if __name__ == "__main__":
    main()
