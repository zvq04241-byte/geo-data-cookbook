#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — Eurostat avia_par/avia_gor → 国ペア航空フロー（欧州・西アジア・アフリカ間）。

リファレンス実装。検証済みの「勝ちパターン」。
- 旅客: avia_par_<cc> (tra_meas=PAS_CRD), 貨物: avia_gor_<cc> (tra_meas=FRM_LD_NLD)
- 報告国＝欧州諸国＋トルコ。相手国の西アジア・アフリカを含む現行データ。

使い方:
    python fetch.py --measure pax  --year 2024 --output-dir ./output
    python fetch.py --measure cargo --year 2024 --output-dir ./output
"""
import argparse, json, urllib.request, sys, io, csv, hashlib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

DEFAULT_REPORTERS = ["de","fr","it","es","nl","be","at","ch","el","pt","se","pl","tr","no","dk","fi","ie","hu","ro"]
EUROPE = set("AT BE BG HR CY CZ DK EE FI FR DE EL GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE IS NO CH LI GB UK RS BA ME MK AL XK MD UA BY".split())
WEST_ASIA = set("TR SA AE QA KW BH OM IL JO LB IQ IR SY YE PS AM AZ GE".split())
AFRICA = set("EG MA TN DZ LY SD NG ZA KE ET GH SN CI CM TZ UG MU AO CD CG GA RW MZ ZW ZM MW NE ML BF BJ TG GN GM SL LR MR CV DJ SO ER KM SC NA BW SZ LS TD CF GQ ST EH SH".split())
ORDER = {"Europe": 0, "West Asia": 1, "Africa": 2}

def region(iso):
    if iso in EUROPE: return "Europe"
    if iso in WEST_ASIA: return "West Asia"
    if iso in AFRICA: return "Africa"
    return None

def fetch(ds, year, unit, meas):
    url = f"{API}/{ds}?format=JSON&lang=EN&freq=A&unit={unit}&tra_meas={meas}&time={year}"
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return json.loads(r.read())
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", choices=["pax", "cargo"], default="pax")
    ap.add_argument("--year", default="2024")
    ap.add_argument("--reporters", default=",".join(DEFAULT_REPORTERS))
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.measure == "pax":
        prefix, unit, meas, valcol, div = "avia_par", "PAS", "PAS_CRD", "pax_thousand", 1000
    else:
        prefix, unit, meas, valcol, div = "avia_gor", "T", "FRM_LD_NLD", "cargo_ton", 1

    flows, meta_pair, used = defaultdict(float), {}, {}
    for cc in args.reporters.split(","):
        data = None; yr = None
        for y in [args.year, str(int(args.year) - 1)]:
            d = fetch(f"{prefix}_{cc}", y, unit, meas)
            if d and d.get("value"):
                data, yr = d, y; break
        if not data:
            continue
        used[cc] = yr
        cat = data["dimension"]["airp_pr"]["category"]
        # ★ハマり所1: value のキーは"位置インデックス"。index で位置→コードに逆引きする
        pos2code = {v: k for k, v in cat["index"].items()}
        tmp = defaultdict(float)   # ★ハマり所2: 報告国内は空港ペアを sum
        for pos, v in data["value"].items():
            code = pos2code.get(int(pos))
            if not code:
                continue
            parts = code.split("_")
            if len(parts) != 4:
                continue
            rep_iso, _, part_iso, _ = parts
            if rep_iso == part_iso:           # ★国内線除外
                continue
            rr, pr = region(rep_iso), region(part_iso)
            if rr is None or pr is None:
                continue
            if rr == "Europe" and pr == "Europe":   # 欧州域内は除外（3地域"間"）
                continue
            key = frozenset({rep_iso, part_iso})
            tmp[key] += float(v)
            meta_pair[key] = (rep_iso, part_iso, rr, pr)
        for key, v in tmp.items():
            flows[key] = max(flows[key], v)   # ★ハマり所3: 報告国"間"は max（二重計上回避）

    rows = []
    for key, val in flows.items():
        a, b, ra, rb = meta_pair[key]
        (ca, cra), (cb, crb) = sorted([(a, ra), (b, rb)], key=lambda x: ORDER[x[1]])  # ★ハマり所4: 地域順で正規化
        pair = f"{cra}-{crb}" if cra != crb else f"{cra} 域内"
        rows.append({"route": f"{ca}-{cb}", "a_iso": ca, "b_iso": cb,
                     "a_region": cra, "b_region": crb, "region_pair": pair,
                     valcol: round(val / div, 1)})   # ★ハマり所5: 旅客は /1000（千人）
    rows.sort(key=lambda r: -r[valcol])

    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    out_csv = args.output_dir / f"{today}_eurostat_airflow_{args.measure}.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["route","a_iso","b_iso","a_region","b_region","region_pair",valcol])
        w.writeheader(); w.writerows(rows)
    meta = {"source": "Eurostat " + ("avia_par (PAS_CRD)" if args.measure == "pax" else "avia_gor (FRM_LD_NLD)"),
            "year": args.year, "reporters_used": used, "rows": len(rows),
            "unit": "千人/年(双方向)" if args.measure == "pax" else "トン/年(双方向)",
            "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
            "retrieved_at": datetime.now(JST).isoformat()}
    (args.output_dir / f"{today}_eurostat_airflow_{args.measure}_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_csv.name}  rows={len(rows)}  top={rows[0]['route']}={rows[0][valcol]}")

if __name__ == "__main__":
    main()
