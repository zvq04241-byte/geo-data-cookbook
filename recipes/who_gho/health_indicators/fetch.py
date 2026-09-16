#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — WHO Global Health Observatory の保健指標を取る。

  ★Dim1 は 'BTSX' ではなく 'SEX_BTSX'。間違えても HTTP 200 で空配列が返る。
  ★WDI の SH.STA.OWAD.ZS は「過体重(BMI≥25)」。WHO の肥満(BMI≥30)とは別物。
  詳細は recipe.md。

使い方:
    python fetch.py --list obes
    python fetch.py --indicator NCD_BMI_30C --countries USA,ARE,DNK,PHL
"""
import argparse, csv, hashlib, json, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

BASE = "https://ghoapi.azureedge.net/api"
UA = {"User-Agent": "Mozilla/5.0"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indicator", default="")
    ap.add_argument("--countries", default="", help="ISO3 カンマ区切り。空なら全件")
    ap.add_argument("--sex", default="SEX_BTSX", help="SEX_BTSX(男女計)/SEX_MLE/SEX_FMLE")
    ap.add_argument("--list", default="", help="指標名をキーワードで探す")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    a = ap.parse_args()

    if a.list:
        j = httpx.get(f"{BASE}/Indicator", headers=UA, timeout=180).json()["value"]
        hit = [x for x in j if a.list.lower() in (x["IndicatorName"] or "").lower()]
        print(f"「{a.list}」に一致する指標 {len(hit)}件")
        for x in hit[:40]:
            print(f"   {x['IndicatorCode']:<22}{(x['IndicatorName'] or '')[:76]}")
        return 0
    if not a.indicator:
        print("--indicator か --list が要る", file=sys.stderr); return 2

    # ★or は括弧でくくる。SEX の接頭辞を忘れない
    f = ["SpatialDimType eq 'COUNTRY'"]
    if a.countries:
        ccs = [c.strip().upper() for c in a.countries.split(",")]
        f.append("(" + " or ".join(f"SpatialDim eq '{c}'" for c in ccs) + ")")
    if a.sex:
        f.append(f"Dim1 eq '{a.sex}'")
    r = httpx.get(f"{BASE}/{a.indicator}", params={"$filter": " and ".join(f)},
                  headers=UA, timeout=300)
    r.raise_for_status()
    v = r.json()["value"]
    if not v:
        raise SystemExit("0件。★Dim1 の接頭辞（SEX_BTSX）と指標コードを疑う。"
                         "フィルタが違っても200が返り空になる")
    D = defaultdict(dict)
    for x in v:
        if x.get("NumericValue") is not None:
            D[x["SpatialDim"]][int(x["TimeDim"])] = x["NumericValue"]

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    p = a.output_dir / f"{today}_who_gho_{a.indicator.lower()}.csv"
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh); w.writerow(["iso3", "year", "value"])
        for c in sorted(D):
            for y in sorted(D[c]): w.writerow([c, y, D[c][y]])
    (a.output_dir / f"{today}_who_gho_{a.indicator.lower()}_metadata.json").write_text(
        json.dumps({"source": "WHO Global Health Observatory (OData)",
                    "indicator": a.indicator, "sex_dim": a.sex,
                    "api": f"{BASE}/{a.indicator}", "rows": sum(len(x) for x in D.values()),
                    "countries": sorted(D), "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(JST).isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {p.name}  {len(D)}か国")
    for c in sorted(D):
        y = max(D[c]); print(f"   {c}  {y}年 {D[c][y]:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
