#!/usr/bin/env python3
"""欧州委員会「EU spending and revenue 2000-20XX」から、加盟国別の受取額（EU予算からの支出）と
支払額（拠出金＝自己財源）を取り出し、CSV + metadata を出力する。

使い方:
  python fetch.py                                # 最新の確定年（既定 2024）・全加盟国
  python fetch.py --year 2024 --countries DE,PL,NL,LU
  python fetch.py --year 2014 --payments national_contribution
  python fetch.py --list-years

勝ちパターン（重要・recipe.md 参照）:
  - 受取額＝「TOTAL EXPENDITURE」行、支払額＝「TOTAL own resources」行。**「TOTAL REVENUE」行には国別の値が無い**。
  - シートが年ごと。**見出しの行・ラベルの列・EU集計の列（EU-15/27/28）が年で違う** → 位置を決め打ちせず名前で探す。
  - NextGenerationEU（復興基金）の支出は「TOTAL EXPENDITURE」に入っていない（別ブロック「TOTAL NGEU」）。
  - 国はISO2。**ギリシャは EL**（GR ではない）。2020年までは UK の列がある。
  - 検算: 加盟国の合計 ＝ EU集計の列（受取・支払とも）。
"""
import argparse, csv, datetime, hashlib, json, re, sys
from pathlib import Path
import httpx
import pandas as pd

PAGE = "https://commission.europa.eu/strategy-and-policy/eu-budget/long-term-eu-budget/2021-2027/spending-and-revenue_en"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
NAMES = {"BE": "ベルギー", "BG": "ブルガリア", "CZ": "チェコ", "DK": "デンマーク", "DE": "ドイツ", "EE": "エストニア",
         "IE": "アイルランド", "EL": "ギリシャ", "ES": "スペイン", "FR": "フランス", "HR": "クロアチア", "IT": "イタリア",
         "CY": "キプロス", "LV": "ラトビア", "LT": "リトアニア", "LU": "ルクセンブルク", "HU": "ハンガリー", "MT": "マルタ",
         "NL": "オランダ", "AT": "オーストリア", "PL": "ポーランド", "PT": "ポルトガル", "RO": "ルーマニア",
         "SI": "スロベニア", "SK": "スロバキア", "FI": "フィンランド", "SE": "スウェーデン", "UK": "イギリス"}
# 加盟年（その年のシートの EU 集計に入るか）。UK は2020年まで（EU-28）。
JOINED = {"CY": 2004, "CZ": 2004, "EE": 2004, "HU": 2004, "LT": 2004, "LV": 2004, "MT": 2004, "PL": 2004,
          "SI": 2004, "SK": 2004, "BG": 2007, "RO": 2007, "HR": 2013}
LEFT = {"UK": 2020}
ROWS = {"receipts": "TOTAL EXPENDITURE",
        "own_resources": "TOTAL own resources",
        "national_contribution": "TOTAL national contribution",
        "ngeu": "TOTAL NGEU"}


def sha256_of(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def download(raw_dir):
    """配布ページから xlsx のリンクを探して落とす（文書IDは版ごとに変わるので決め打ちしない）。"""
    html = httpx.get(PAGE, headers=UA, timeout=60, follow_redirects=True).text
    m = re.search(r'href="([^"]*/document/download/[^"]*spending_and_revenue[^"]*\.xlsx)"', html)
    if not m:
        sys.exit("配布ページに spending_and_revenue の xlsx が見つからない（ページの作りが変わった）")
    url = m.group(1) if m.group(1).startswith("http") else "https://commission.europa.eu" + m.group(1)
    name = re.search(r"filename=([^&\"]+)", url).group(1)
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / f"{datetime.date.today():%Y%m%d}_{name}"
    if not out.exists():
        r = httpx.get(url, headers=UA, timeout=180, follow_redirects=True)
        r.raise_for_status()
        out.write_bytes(r.content)
    return out, url


def parse(xlsx, year):
    d = pd.read_excel(xlsx, sheet_name=str(year), header=None)
    iso = re.compile(r"^[A-Z]{2}$")
    # 見出し行＝国コードが最も多く並ぶ行（年で位置が違う）
    hr = max(range(min(25, len(d))), key=lambda i: sum(bool(iso.match(str(v).strip())) for v in d.iloc[i]))
    head = [str(v).strip() for v in d.iloc[hr]]
    agg_col = next(j for j, v in enumerate(head) if v.startswith("EU-"))
    # ★加盟前の国にも列がある（加盟前支援の受取が入る）。その年の加盟国だけを残す
    members = [(j, v) for j, v in enumerate(head) if j > agg_col and iso.match(v)
               and JOINED.get(v, 0) <= year and LEFT.get(v, 9999) >= year]

    def find(label):
        for i in range(len(d)):
            for c in range(min(6, d.shape[1])):
                if str(d.iloc[i, c]).strip().lower() == label.lower():
                    return i
        return None

    out = {}
    for key, label in ROWS.items():
        i = find(label)
        if i is None:
            continue
        vals = {code: pd.to_numeric(d.iloc[i, j], errors="coerce") for j, code in members}
        out[key] = {"row": i, "agg": float(pd.to_numeric(d.iloc[i, agg_col], errors="coerce")), "vals": vals}
    return head[agg_col], members, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--payments", default="own_resources", choices=["own_resources", "national_contribution"])
    ap.add_argument("--with-ngeu", action="store_true", help="受取額に NextGenerationEU の支出を足す（2021年〜）")
    ap.add_argument("--countries", default=None, help="ISO2 をカンマ区切り（例 DE,PL,NL,LU）。未指定は全加盟国")
    ap.add_argument("--xlsx", default=None, help="手元の xlsx を使う（指定しなければ配布ページから落とす）")
    ap.add_argument("--raw-dir", default="raw")
    ap.add_argument("--output-dir", default=".")
    ap.add_argument("--list-years", action="store_true")
    a = ap.parse_args()

    if a.xlsx:
        xlsx, url = Path(a.xlsx), "(local)"
    else:
        xlsx, url = download(Path(a.raw_dir))
    if a.list_years:
        print(" ".join(pd.ExcelFile(xlsx).sheet_names))
        return 0
    agg, members, rows = parse(xlsx, a.year)
    if "receipts" not in rows or a.payments not in rows:
        sys.exit(f"{a.year}年のシートに必要な行が無い: {sorted(rows)}（national_contribution は2020年まで）")

    rec, pay = rows["receipts"], rows[a.payments]
    checks = {}
    for k, r in (("receipts", rec), ("payments", pay)):
        s = float(sum(v for v in r["vals"].values() if pd.notna(v)))
        checks[k] = {"sum_members": round(s, 1), "eu_column": round(r["agg"], 1), "ok": abs(s - r["agg"]) < 1.0}
    ng = rows.get("ngeu") if a.with_ngeu else None
    if a.with_ngeu and ng is None:
        sys.exit(f"{a.year}年のシートに TOTAL NGEU が無い（2021年〜）")

    want = [c.strip().upper() for c in a.countries.split(",")] if a.countries else [c for _, c in members]
    table = []
    for code in want:
        if code not in rec["vals"]:
            sys.exit(f"{code} が {a.year}年の加盟国の列に無い（ギリシャは EL）")
        r = float(rec["vals"][code]) + (float(ng["vals"][code]) if ng else 0.0)
        p = float(pay["vals"][code])
        table.append((code, NAMES.get(code, code), round(r, 1), round(p, 1), round(r - p, 1)))
    table.sort(key=lambda x: x[4], reverse=True)

    outdir = Path(a.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.date.today():%Y%m%d}_eu_budget_{a.year}" + ("_ngeu" if ng else "")
    csv_path = outdir / f"{stem}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["iso2", "country", "receipts_eur_million", "payments_eur_million", "net_eur_million"])
        w.writerows(table)
    meta = {
        "task_name": f"EU予算 加盟国別 受取額・支払額 {a.year}年",
        "source": {"name": "European Commission, EU spending and revenue 2000-20XX", "page": PAGE, "url": url,
                   "file": xlsx.name, "file_sha256": sha256_of(xlsx), "sheet": str(a.year), "single_source": True},
        "query": {"receipts_row": ROWS["receipts"] + (" + TOTAL NGEU" if ng else ""),
                  "payments_row": ROWS[a.payments], "aggregate_column": agg, "countries": want},
        "units": "百万ユーロ（EUR million）",
        "fetched_at": datetime.datetime.now().astimezone().isoformat(),
        "csv_sha256": sha256_of(csv_path),
        "row_count": len(table),
        "verification": checks,
        "notes": "受取額は TOTAL EXPENDITURE（NGEU を含まない。--with-ngeu で足す）。支払額は TOTAL own resources"
                 "（関税＝伝統的自己財源を含む。港湾国の値が膨らむ）。TOTAL REVENUE 行は国別の値が無い。",
    }
    (outdir / f"{stem}_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"# EU予算 {a.year}年（百万ユーロ） 受取＝{meta['query']['receipts_row']} / 支払＝{ROWS[a.payments]}")
    for code, name, r, p, n in table:
        print(f"  {name:8} {code}  受取 {r:>10,.1f}  支払 {p:>10,.1f}  差引 {n:>+10,.1f}")
    for k, c in checks.items():
        print(f"検算 {k}: 加盟国の合計 {c['sum_members']:,.1f} / {agg} {c['eu_column']:,.1f} -> {'OK' if c['ok'] else 'NG'}")
    print(f"saved: {csv_path}")
    return 0 if all(c["ok"] for c in checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
