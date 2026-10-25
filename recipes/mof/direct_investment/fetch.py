#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — 財務省「直接投資残高（地域別・業種別）」を取る。

  ★シート1=対外、シート2=対内。A列=地域、B列=国で、国を足すと地域と二重になる。
  ★末尾の ＯＥＣＤ／ＡＳＥＡＮ／ＥＵ／東欧・ロシア等は再掲。合計に足さない。
  ★2024年からURLに data/ が挟まる。詳細は recipe.md。
  ★単位は**億円**（表題の「（単位：億円）」を読んで確かめる）。「.」は該当データなし、「Ⅹ」は報告3件未満の秘匿。

使い方:
    python fetch.py --years 2019-2025
    python fetch.py --years 2025 --direction inward
    python fetch.py --years 2025 --level country
"""
import argparse, csv, hashlib, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

VAULT = Path("./data_bulk/other_primary/mof")
B = "https://www.mof.go.jp/policy/international_policy/reference/iip"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
REGIONS = ["アジア", "北米", "中南米", "大洋州", "欧州", "中東", "アフリカ"]
RESTATED = ["ＯＥＣＤ諸国", "ＡＳＥＡＮ", "ＥＵ", "東欧・ロシア等"]   # ★再掲。合計に足さない
OTHER_A = ["国際機関"]          # A列に出る、地域でも再掲でもない行（2019〜2025年末で値は「.」）
SHEET_TITLE = {"1": "対外直接投資残高", "2": "対内直接投資残高"}


def check_file(p, year):
    """中身を開いて年・単位を確かめる（大きさだけでは別年・エラーページを見分けられない）。"""
    import pandas as pd
    if p.read_bytes()[:2] != b"PK":
        raise SystemExit(f"{p.name} は xlsx でない")
    x = pd.ExcelFile(p)
    for sh, want in SHEET_TITLE.items():
        if sh not in x.sheet_names:
            raise SystemExit(f"{p.name} にシート {sh} が無い（{x.sheet_names}）")
        d = pd.read_excel(x, sheet_name=sh, header=None, nrows=5)
        t = " ".join(str(v) for v in d.values.ravel() if str(v) != "nan")
        if want not in t or f"{year}年末" not in t:
            raise SystemExit(f"{p.name} シート{sh} の表題が「{want}」「{year}年末」でない: {t[:80]}")
        m = re.search(r"単位：(\S+?)）", t)
        if not m or m.group(1) != "億円":
            raise SystemExit(f"{p.name} シート{sh} の単位が億円でない: {m.group(1) if m else '見つからない'}")


def ensure(year):
    VAULT.mkdir(parents=True, exist_ok=True)
    p = VAULT / f"dip{year}.xlsx"
    if p.exists():
        check_file(p, year)
        return p
    for u in (f"{B}/data/dip{year}.xlsx", f"{B}/dip{year}.xlsx"):   # ★2024年から data/
        r = httpx.get(u, headers=UA, timeout=180, follow_redirects=True)
        if r.status_code == 200 and r.content[:2] == b"PK":
            p.write_bytes(r.content)
            check_file(p, year)
            print(f"取得 {p.name} {len(r.content)/1000:.0f}KB {u}", file=sys.stderr)
            return p
    raise SystemExit(f"{year}年のファイルが見つからない（2026-10 の確認では 2019年末〜。2018年は404）")


def read(year, sheet):
    import pandas as pd
    d = pd.read_excel(ensure(year), sheet_name=sheet, header=None)
    reg, cty, cur, tot = {}, {}, None, None
    dropped = []                                          # 値が数でなく落とした行（名前, 記号）
    A = [str(v).strip() for v in d.iloc[:, 0]]
    start = A.index("合計") if "合計" in A else None      # 本体は A列の「合計」の行から
    if start is None:
        raise SystemExit(f"{year}年 シート{sheet}: A列に「合計」の行が無い（様式変更）")
    for i in range(start, len(d)):
        a, b, v = A[i], str(d.iloc[i, 1]).strip(), d.iloc[i, 2]
        try:
            val = float(v)
        except (TypeError, ValueError):
            val = None                                    # ★「.」＝該当データなし、「Ⅹ」＝秘匿
        if a == "合計" and val is not None:
            tot = val
        elif a in REGIONS:
            cur = a
            if val is not None: reg[a] = val
            else: dropped.append((a, str(v).strip()))
        elif a in RESTATED or a in OTHER_A:
            cur = None                                    # ★再掲・国際機関以降は拾わない
            if a in OTHER_A and val is not None:
                raise SystemExit(f"{year}年 シート{sheet}: 「{a}」に値 {val} がある（地域の合計と合わせ方を決め直す）")
        elif a != "nan":
            raise SystemExit(f"{year}年 シート{sheet}: A列に知らない区分「{a}」（区分名の変更か）")
        elif b != "nan" and cur:
            if b.startswith("(") or b.startswith("（"):
                cur = None                                # 注の始まり
            elif val is not None:
                cty[b] = (cur, val)
            else:
                dropped.append((b, str(v).strip()))
    missing = [r for r in REGIONS if r not in reg]
    if tot is None or missing:
        raise SystemExit(f"{year}年 シート{sheet}: 合計={tot} / 値の無い地域 {missing}")
    return tot, reg, cty, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2025", help="2019-2025 のように範囲、または 2019,2025")
    ap.add_argument("--direction", default="outward", choices=["outward", "inward"])
    ap.add_argument("--level", default="region", choices=["region", "country"])
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    a = ap.parse_args()
    if re.fullmatch(r"\d{4}-\d{4}", a.years):
        y0, y1 = map(int, a.years.split("-")); ys = list(range(y0, y1 + 1))
    elif re.fullmatch(r"\d{4}(,\d{4})*", a.years):
        ys = [int(x) for x in a.years.split(",")]
    else:
        raise SystemExit(f"--years は 2019-2025 か 2019,2025 の形で（{a.years}）")
    sheet = "1" if a.direction == "outward" else "2"
    rows, checks, inputs = [], {}, {}
    for y in ys:
        tot, reg, cty, dropped = read(y, sheet)
        inputs[y] = hashlib.sha256(ensure(y).read_bytes()).hexdigest()
        resid = tot - sum(reg.values())                   # 地域の内訳に入らない分（「Ⅹ」等）
        checks[y] = {"total": round(tot, 1), "sum_regions": round(sum(reg.values()), 1),
                     "residual": round(resid, 1), "n_countries": len(cty), "dropped": dropped}
        if abs(resid) > abs(tot) * 0.01:
            raise SystemExit(f"{y}年: 地域の計 {sum(reg.values()):,.0f} が合計 {tot:,.0f} と1%以上ずれる")
        if a.level == "region":
            for k, v in list(reg.items()) + [("（地域の内訳に入らない分）", resid)]:
                rows.append(dict(year=y, direction=a.direction, level="region", name=k,
                                 value_100m_jpy=round(v, 1), pct=round(v / tot * 100, 2)))
        else:
            for k, (r, v) in cty.items():
                rows.append(dict(year=y, direction=a.direction, level="country", region=r,
                                 name=k, value_100m_jpy=round(v, 1), pct=round(v / tot * 100, 2)))
        if dropped:
            print(f"   {y}年 値が数でなく落とした行: {dropped}", file=sys.stderr)
    if not rows:
        raise SystemExit("1行も取れなかった")
    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9)); today = datetime.now(JST).strftime("%Y%m%d")
    p = a.output_dir / f"{today}_mof_fdi_{a.direction}_{a.level}.csv"
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (a.output_dir / f"{today}_mof_fdi_{a.direction}_{a.level}_metadata.json").write_text(
        json.dumps({"source": "財務省 直接投資残高（地域別・業種別）",
                    "sheet": f"{sheet}（{'対外' if sheet=='1' else '対内'}）",
                    "unit": "億円（表題の「単位：億円」で確認。列名 value_100m_jpy）", "years": ys,
                    "scope": ("7地域＋地域の内訳に入らない分。割合の分母はシートの「合計」" if a.level == "region" else
                              "表に掲載のある国だけ（全ての国ではない）。割合の分母はシートの「合計」"),
                    "verification": checks, "input_sha256": inputs,
                    "note": "ＯＥＣＤ／ＡＳＥＡＮ／ＥＵ／東欧・ロシア等は再掲のため除外。「.」＝該当データなし、「Ⅹ」＝報告3件未満の秘匿（表の注）。"
                            "業種別の列は取っていない。",
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
