#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — AQUASTAT 国別 水資源賦存量（国内IRWR・総TRWR・1人当たり）。

AQUASTAT のネイティブ API/バルクは公開エンドポイントが辿りにくいため、
**World Bank Data360 の FAO_AS（AQUASTAT ミラー）** を取得層に使う。
指標コードは FAO_AS_<AQUASTAT変数ID>。

取得指標:
  - 総 TRWR  = FAO_AS_4188  (Total renewable water resources, 10^9 m3/yr)
  - 国内IRWR = FAO_AS_4157  (Total internal renewable water resources, 10^9 m3/yr)
  - 1人当たり = FAO_AS_4190 (Total renewable water resources per capita, m3/inhab/yr)
  - 依存率   = FAO_AS_4192 (Dependency ratio, %) … 算出した外来依存率の検算に使う
★2026-10-26、総人口 FAO_AS_4104 と 4174 は Data360 の指標一覧から消えていた（値0件）。
  以前は TRWR ÷ 4104 で1人当たりを算出していたが、今は AQUASTAT の 4190 をそのまま使う
  （2022年の4か国で、以前の算出値と1 m3 の位まで一致）。人口は TRWR ÷ 4190 で逆算して参考に出す。

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
IND_PCAP = "FAO_AS_4190"   # 1人当たり TRWR (m3/inhab/yr, UNIT_MULT=0)
IND_DEP = "FAO_AS_4192"    # 依存率 (%)＝外来の割合。算出値の検算用

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


def _pick(values, year, fallbacks=None, label=""):
    """指定年の観測値を返す。無指定/不在なら LATEST_DATA→最新 TIME_PERIOD。

    指定年が無くて別の年に落ちたときは fallbacks に記録する（黙って年をずらさない）。
    """
    if not values:
        return None
    if year:
        yv = [v for v in values if v.get("TIME_PERIOD") == str(year)]
        if yv:
            return yv[0]
        if fallbacks is not None:
            fallbacks.append(label)
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

    rows, years_used, skipped, fallbacks = [], set(), {}, []
    req = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    for iso in req:
        trwr_o = _pick(_get_json(IND_TRWR, iso), args.year, fallbacks, f"{iso}:TRWR")
        irwr_o = _pick(_get_json(IND_IRWR, iso), args.year, fallbacks, f"{iso}:IRWR")
        pcap_o = _pick(_get_json(IND_PCAP, iso), args.year, fallbacks, f"{iso}:per_capita")
        dep_o = _pick(_get_json(IND_DEP, iso), args.year, fallbacks, f"{iso}:dependency")
        if not (trwr_o and irwr_o and pcap_o):
            miss = [k for k, o in (("TRWR", trwr_o), ("IRWR", irwr_o), ("per_capita", pcap_o)) if not o]
            skipped[iso] = miss
            print(f"  WARN: {iso} は指標が欠損 {miss}（出力しない。metadata の skipped に記録）")
            continue
        trwr = _scaled(trwr_o)        # m3/yr
        irwr = _scaled(irwr_o)        # m3/yr
        per_cap = _scaled(pcap_o)     # m3/inhab/yr（AQUASTAT の値）
        pop = trwr / per_cap if per_cap else None   # 逆算した人口（参考）
        ext = trwr - irwr
        ext_pct = ext / trwr * 100 if trwr else None
        dep = float(dep_o["OBS_VALUE"]) if dep_o else None
        if dep is not None and ext_pct is not None and abs(dep - ext_pct) > 1:
            print(f"  WARN: {iso} 外来依存率の算出 {ext_pct:.1f}% と AQUASTAT の依存率 {dep:.1f}% が1ポイント超ずれる")
        rows.append({
            "iso3": iso, "country": JP.get(iso, iso),
            "irwr_km3": round(irwr / 1e9, 1),          # 10^9 m3 = km3
            "trwr_km3": round(trwr / 1e9, 1),
            "external_km3": round(ext / 1e9, 1),
            "external_pct": round(ext_pct, 0) if ext_pct is not None else None,
            "dependency_ratio_pct_aquastat": round(dep, 1) if dep is not None else None,
            "population_million": round(pop / 1e6, 1) if pop else None,   # TRWR ÷ 1人当たり で逆算
            "trwr_per_capita_m3": int(per_cap + 0.5) if per_cap else None,   # 四捨五入（round は偶数丸めで 1282.5→1282 になる）
            "year_trwr": trwr_o["TIME_PERIOD"], "year_irwr": irwr_o["TIME_PERIOD"],
            "year_per_capita": pcap_o["TIME_PERIOD"],
            "obs_status_trwr": trwr_o.get("OBS_STATUS"),
            "obs_status_irwr": irwr_o.get("OBS_STATUS"),
        })
        years_used.update({trwr_o["TIME_PERIOD"], irwr_o["TIME_PERIOD"], pcap_o["TIME_PERIOD"]})

    if not rows:
        raise DataFetchError("有効な行が1つも取得できなかった")

    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    cols = ["iso3", "country", "irwr_km3", "trwr_km3", "external_km3", "external_pct",
            "dependency_ratio_pct_aquastat", "population_million", "trwr_per_capita_m3",
            "year_trwr", "year_irwr", "year_per_capita", "obs_status_trwr", "obs_status_irwr"]
    out_csv = args.output_dir / f"{today}_aquastat_water_resources.csv"
    with open(out_csv, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)

    meta = {
        "source": "FAO AQUASTAT via World Bank Data360 (DATABASE_ID=FAO_AS)",
        "indicators": {"TRWR": IND_TRWR, "IRWR": IND_IRWR, "per_capita": IND_PCAP,
                       "dependency_ratio": IND_DEP,
                       "population": "TRWR / per_capita で逆算（4104 は 2026-10-26 時点で Data360 に無い）"},
        "api": API, "countries": [r["iso3"] for r in rows],
        "scope": f"指定した{len(req)}か国のうち3指標がそろう{len(rows)}か国",
        "skipped": skipped,
        "year_requested": args.year,
        "year_fallback": fallbacks,   # 指定年が無く最新年に落ちた 国:指標
        "obs_status_note": ("Data360 の OBS_STATUS は配信側で変わる（2026-06-12 は I、2026-10-26 は全行 A）。"
                            "推計かどうかの判断に使わない"),
        "years_in_data": sorted(years_used), "rows": len(rows),
        "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "retrieved_at": datetime.now(JST).isoformat(),
    }
    (args.output_dir / f"{today}_aquastat_water_resources_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_csv.name}  rows={len(rows)}  skipped={len(skipped)}")
    if fallbacks:
        print(f"  WARN: 指定年 {args.year} が無く最新年に落ちた: {fallbacks}")
    for r in rows:
        print(f"  {r['country']:<10} IRWR={r['irwr_km3']:>6} TRWR={r['trwr_km3']:>6} "
              f"外来={r['external_pct']:>3.0f}%  1人当={r['trwr_per_capita_m3']:>6.0f} m3")


if __name__ == "__main__":
    main()
