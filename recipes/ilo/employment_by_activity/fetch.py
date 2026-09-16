#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — ILOSTAT の産業別就業者（DF_EMP_TEMP_SEX_ECO_NB）を取る。

  賃金の ilo/wages_ranking とは **次元数が違う**（あちらは4、こちらは5）。
  キーは REF_AREA.FREQ.MEASURE.SEX.ECO。詳細は recipe.md。

使い方:
    python fetch.py --countries JPN,CHE,ARE,HUN --mode tertiary
    python fetch.py --countries JPN --mode isic
    python fetch.py --countries JPN,CHE --mode sector
    python fetch.py --countries JPN --isic K
"""
import argparse, csv, hashlib, io, json, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

BASE = "https://sdmx.ilo.org/rest/data/ILO,DF_EMP_TEMP_SEX_ECO_NB"
ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"   # ★XMLになるのを防ぐ

# 第3次産業の4区分（Singelmann型）。ILOSTAT側にこの集計は無い＝本レシピの取り決め
TERTIARY = {
    "流通関連サービス": ["G", "H", "J"],          # 卸小売・運輸保管・情報通信
    "消費関連サービス": ["I", "R", "S", "T"],      # 宿泊飲食・芸術娯楽・その他・家事
    "生産関連サービス": ["K", "L", "M", "N"],      # 金融保険・不動産・専門技術・管理支援
    "社会関連サービス": ["O", "P", "Q"],           # 公務・教育・保健福祉
}
SER_ALL = [c for v in TERTIARY.values() for c in v] + ["U"]   # U=治外法権機関


def fetch(countries, start):
    # ★5次元。空の段はドットで置く（JPN.SEX_T. だと 422）
    key = f"{'+'.join(countries)}.A..SEX_T."
    r = httpx.get(f"{BASE}/{key}", params={"startPeriod": start},
                  headers={"Accept": ACCEPT}, timeout=300, follow_redirects=True)
    if r.status_code == 422:
        raise SystemExit(f"キーの次元数が合いません（5次元）: {r.text[:120]}")
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def latest(rows, area):
    """★最新年は国ごとに違う。ISIC4の合計が取れる最新年を国ごとに選ぶ"""
    ys = {int(x["TIME_PERIOD"]) for x in rows
          if x["REF_AREA"] == area and x["ECO"] == "ECO_ISIC4_TOTAL" and x["OBS_VALUE"]}
    return max(ys) if ys else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", required=True, help="ISO3 カンマ区切り")
    ap.add_argument("--mode", default="tertiary", choices=["tertiary", "isic", "sector"])
    ap.add_argument("--isic", default="", help="単一のISIC大分類だけ欲しいとき（例 K）")
    ap.add_argument("--start", type=int, default=2015)
    ap.add_argument("--year", type=int, default=0, help="年を揃えたいとき（既定は国ごとの最新）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    a = ap.parse_args()
    ccs = [c.strip().upper() for c in a.countries.split(",")]
    rows = fetch(ccs, a.start)
    if not rows:
        raise SystemExit("0件。国コード（ISO3）と年を確認")

    V = defaultdict(dict)
    for x in rows:
        if x["OBS_VALUE"]:
            V[(x["REF_AREA"], int(x["TIME_PERIOD"]))][x["ECO"]] = float(x["OBS_VALUE"])

    out, meta_years = [], {}
    for c in ccs:
        y = a.year or latest(rows, c)
        if not y or (c, y) not in V:
            print(f"  {c}: 該当年なし", file=sys.stderr); continue
        v = V[(c, y)]; meta_years[c] = y
        tot = v.get("ECO_ISIC4_TOTAL") or v.get("ECO_SECTOR_TOTAL")
        if not tot: continue
        rec = {"iso3": c, "year": y, "total_employment": tot}
        if a.isic:
            k = f"ECO_ISIC4_{a.isic.upper()}"
            rec[f"isic_{a.isic.upper()}_pct"] = round(v.get(k, 0) / tot * 100, 2)
        elif a.mode == "sector":
            for s, lab in (("AGR", "第1次"), ("IND", "第2次"), ("SER", "第3次")):
                st = v.get("ECO_SECTOR_TOTAL", tot)
                rec[f"{lab}_pct"] = round(v.get(f"ECO_SECTOR_{s}", 0) / st * 100, 2)
        elif a.mode == "isic":
            for k, val in sorted(v.items()):
                if k.startswith("ECO_ISIC4_") and not k.endswith("TOTAL"):
                    rec[k.replace("ECO_ISIC4_", "isic_") + "_pct"] = round(val / tot * 100, 2)
        else:  # tertiary
            ser = sum(v.get(f"ECO_ISIC4_{c2}", 0) for c2 in SER_ALL)
            rec["第3次産業就業者割合"] = round(ser / tot * 100, 1)
            got = 0.0
            for lab, codes in TERTIARY.items():
                s = sum(v.get(f"ECO_ISIC4_{c2}", 0) for c2 in codes)
                rec[lab] = round(s / ser * 100, 1) if ser else None
                got += s
            rec["その他"] = round((ser - got) / ser * 100, 1) if ser else None   # ★U等の取りこぼし
        out.append(rec)

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    p = a.output_dir / f"{today}_ilostat_employment_{a.isic.lower() or a.mode}.csv"
    cols = sorted({k for r in out for k in r}, key=lambda k: (k not in ("iso3", "year"), k))
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    (a.output_dir / f"{today}_ilostat_employment_{a.isic.lower() or a.mode}_metadata.json").write_text(
        json.dumps({"source": "ILO ILOSTAT SDMX — DF_EMP_TEMP_SEX_ECO_NB",
                    "key": "REF_AREA.FREQ.MEASURE.SEX.ECO（5次元）",
                    "measure": "employment (就業者。労働力人口ではない)",
                    "tertiary_mapping": TERTIARY if a.mode == "tertiary" else None,
                    "years_by_country": meta_years, "rows": len(out),
                    "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(JST).isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {p.name}  rows={len(out)}")
    for r in out:
        print("   " + "  ".join(f"{k}={v}" for k, v in r.items() if k != "total_employment"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
