#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — 財務省「直接投資残高（地域別・業種別）」を取る。

  ★シート1=対外、シート2=対内。A列=地域、B列=国で、国を足すと地域と二重になる。
  ★末尾の ＯＥＣＤ／ＡＳＥＡＮ／ＥＵ／東欧・ロシア等は再掲。合計に足さない。
  ★2024年からURLに data/ が挟まる。詳細は recipe.md。

使い方:
    python fetch.py --years 2019-2025
    python fetch.py --years 2025 --direction inward
    python fetch.py --years 2025 --level country
"""
import argparse, csv, hashlib, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

VAULT = Path("./data_bulk/other_primary/mof")
B = "https://www.mof.go.jp/policy/international_policy/reference/iip"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
REGIONS = ["アジア", "北米", "中南米", "大洋州", "欧州", "中東", "アフリカ"]
RESTATED = ["ＯＥＣＤ諸国", "ＡＳＥＡＮ", "ＥＵ", "東欧・ロシア等"]   # ★再掲。合計に足さない


def ensure(year):
    VAULT.mkdir(parents=True, exist_ok=True)
    p = VAULT / f"dip{year}.xlsx"
    if p.exists():
        return p
    for u in (f"{B}/data/dip{year}.xlsx", f"{B}/dip{year}.xlsx"):   # ★2024年から data/
        r = httpx.get(u, headers=UA, timeout=180, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 5000:
            p.write_bytes(r.content)
            print(f"取得 {p.name} {len(r.content)/1000:.0f}KB", file=sys.stderr)
            return p
    raise SystemExit(f"{year}年のファイルが見つからない（2019年以降が公開）")


def read(year, sheet):
    import pandas as pd
    d = pd.read_excel(ensure(year), sheet_name=sheet, header=None)
    reg, cty, cur, tot = {}, {}, None, None
    for i in range(11, len(d)):
        a, b, v = str(d.iloc[i, 0]), str(d.iloc[i, 1]), d.iloc[i, 2]
        try:
            val = float(v)
        except (TypeError, ValueError):
            val = None                                    # ★「.」は秘匿。弾く
        if a == "合計" and val is not None:
            tot = val
        elif a in REGIONS:
            cur = a
            if val is not None: reg[a] = val
        elif a in RESTATED:
            cur = None                                    # ★再掲以降は拾わない
        elif b != "nan" and cur and val is not None:
            cty[b] = (cur, val)
    return tot, reg, cty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2025", help="2019-2025 のように範囲も可")
    ap.add_argument("--direction", default="outward", choices=["outward", "inward"])
    ap.add_argument("--level", default="region", choices=["region", "country"])
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    a = ap.parse_args()
    ys = ([int(x) for x in range(int(a.years.split("-")[0]), int(a.years.split("-")[1]) + 1)]
          if "-" in a.years else [int(x) for x in a.years.split(",")])
    sheet = "1" if a.direction == "outward" else "2"
    rows = []
    for y in ys:
        tot, reg, cty = read(y, sheet)
        if a.level == "region":
            s = sum(reg.values())
            for k, v in reg.items():
                rows.append(dict(year=y, direction=a.direction, level="region", name=k,
                                 value_million_jpy=round(v), pct=round(v / s * 100, 2)))
        else:
            for k, (r, v) in cty.items():
                rows.append(dict(year=y, direction=a.direction, level="country", region=r,
                                 name=k, value_million_jpy=round(v),
                                 pct=round(v / tot * 100, 2) if tot else None))
    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9)); today = datetime.now(JST).strftime("%Y%m%d")
    p = a.output_dir / f"{today}_mof_fdi_{a.direction}_{a.level}.csv"
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (a.output_dir / f"{today}_mof_fdi_{a.direction}_{a.level}_metadata.json").write_text(
        json.dumps({"source": "財務省 直接投資残高（地域別・業種別）",
                    "sheet": f"{sheet}（{'対外' if sheet=='1' else '対内'}）",
                    "unit": "百万円", "years": ys,
                    "note": "ＯＥＣＤ／ＡＳＥＡＮ／ＥＵ／東欧・ロシア等は再掲のため除外",
                    "rows": len(rows), "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(JST).isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {p.name}  rows={len(rows)}")
    if a.level == "region":
        for y in ys:
            r = [x for x in rows if x["year"] == y]
            print(f"   {y}年末  " + "  ".join(f"{x['name']}{x['pct']:.1f}%"
                  for x in sorted(r, key=lambda z: -z["pct"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
