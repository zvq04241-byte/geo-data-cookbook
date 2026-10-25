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
    ap.add_argument("--countries", default="",
                    help="ISO3 カンマ区切り。空なら全 COUNTRY（地域・所得グループ・世界の行は常に含まない）")
    ap.add_argument("--sex", default="SEX_BTSX",
                    help="SEX_BTSX(男女計)/SEX_MLE/SEX_FMLE。'' で性別を絞らない（性別の次元が無い指標向け）")
    ap.add_argument("--list", default="", help="指標名をキーワードで探す")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    a = ap.parse_args()

    if a.list:
        j = httpx.get(f"{BASE}/Indicator", headers=UA, timeout=180).json()["value"]
        hit = [x for x in j if a.list.lower() in (x["IndicatorName"] or "").lower()]
        print(f"「{a.list}」に一致する指標 {len(hit)}件")
        for x in hit[:40]:
            print(f"   {x['IndicatorCode']:<22}{(x['IndicatorName'] or '')[:76]}")
        if len(hit) > 40:
            print(f"   …ほか {len(hit) - 40}件（表示は40件まで。語を絞る）")
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
    flt = " and ".join(f)
    r = httpx.get(f"{BASE}/{a.indicator}", params={"$filter": flt}, headers=UA, timeout=300)
    r.raise_for_status()
    j = r.json(); v = j["value"]; pages = 1
    # OData のページ送りが返ったら追う（2026-10-26 の確認では 14,112 行の指標でも返らなかった）
    while j.get("@odata.nextLink"):
        j = httpx.get(j["@odata.nextLink"], headers=UA, timeout=300).json()
        v += j["value"]; pages += 1
    if not v:
        raise SystemExit("0件。★Dim1 の接頭辞（SEX_BTSX）と指標コードを疑う。"
                         "フィルタが違っても200が返り空になる")
    D = defaultdict(dict)
    seen = defaultdict(list)
    skipped_null = 0
    for x in v:
        seen[(x["SpatialDim"], int(x["TimeDim"]))].append(
            {k: x.get(k) for k in ("Dim1", "Dim2", "Dim3")})
        if x.get("NumericValue") is not None:
            D[x["SpatialDim"]][int(x["TimeDim"])] = x["NumericValue"]
        else:
            skipped_null += 1
    # 同じ国・年に複数行＝性別以外の次元（年齢群・居住地等）がある。後勝ちで1つに潰さず止める
    dup = {k: d for k, d in seen.items() if len(d) > 1}
    if dup:
        k0 = next(iter(dup))
        raise SystemExit(f"同じ国・年に複数行が {len(dup)}組（例 {k0}: {dup[k0]}）。"
                         "次元（性別・年齢群・居住地等）が複数ある。--sex や $filter の Dim2 等で1行にする")
    dims_used = sorted({json.dumps(d[0], ensure_ascii=False) for d in seen.values()})
    missing = []
    if a.countries:
        missing = sorted(set(ccs) - set(D))
        if missing:
            print(f"★ 値が返らなかった国: {missing}（コードの誤りか、この指標に値が無い）", file=sys.stderr)
    if skipped_null:
        print(f"★ NumericValue が空の行を {skipped_null} 件落とした", file=sys.stderr)

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    sx = f"_{a.sex.lower()}" if a.sex else ""
    p = a.output_dir / f"{today}_who_gho_{a.indicator.lower()}{sx}.csv"
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh); w.writerow(["iso3", "year", "value"])
        for c in sorted(D):
            for y in sorted(D[c]): w.writerow([c, y, D[c][y]])
    (a.output_dir / f"{today}_who_gho_{a.indicator.lower()}{sx}_metadata.json").write_text(
        json.dumps({"source": "WHO Global Health Observatory (OData)",
                    "indicator": a.indicator, "sex_dim": a.sex,
                    "api": f"{BASE}/{a.indicator}", "filter": flt, "pages": pages,
                    "spatial_dim_type": "COUNTRY",
                    "scope": (f"指定した国 {len(ccs)}（値があったのは {len(D)}）" if a.countries else
                              f"WHO GHO の COUNTRY 全{len(D)}（地域・所得グループ・世界は含まない）"),
                    "dims_used": [json.loads(x) for x in dims_used],
                    "skipped_null_rows": skipped_null,
                    "missing_countries": missing,
                    "rows": sum(len(x) for x in D.values()),
                    "countries": sorted(D), "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(JST).isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {p.name}  {len(D)}か国")
    for c in sorted(D):
        y = max(D[c]); print(f"   {c}  {y}年 {D[c][y]:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
