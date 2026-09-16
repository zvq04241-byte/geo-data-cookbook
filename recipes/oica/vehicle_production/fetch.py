#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""oica/vehicle_production — OICA公式PDFから国別 自動車生産台数を取得（Wikipedia不使用）。

OICA(国際自動車工業連合会)は世界の自動車生産の一次出典。現行サイト
`https://oica.net/production-statistics/` は JS(jet-engine)描画で HTML には各年 top10 しか
埋め込まれず、DL できる公式PDFは「直近6年窓(2019-2024)」のみ。2000年など古い年は
現行サイトに存在せず、archive.org の当時のOICA公式PDF(id_=raw)を使う。いずれも直DL可。
★数値は空白区切り千位（"4 663 749"）で、列間も単一スペースだと語彙的に切れない
 → **pdftotext -layout** で列を多スペース化し `\\s{2,}` で列分割する（pypdf/naive splitは不可）。

使い方:
  python fetch.py --year 2024 --measure all  --output-dir ./output   # 直近窓(all=cars+CV)
  python fetch.py --year 2024 --measure cars --output-dir ./output   # 乗用車のみ
  python fetch.py --year 2000 --measure all  --output-dir ./output   # archive.orgの2000年公式
"""
import argparse, csv, json, re, subprocess, sys, datetime, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# OICA公式PDF。直近窓は6年(2019,2021,2022,2023,2024)を1ファイルに収める。
RECENT = {
    "all":  "https://oica.net/wp-content/uploads/2025/10/By-country-region-2024.pdf",
    "cars": "https://oica.net/wp-content/uploads/2025/10/Passenger-Cars-2024.pdf",
}
RECENT_YEARS = [2019, 2021, 2022, 2023, 2024]   # PDFの列順（2020は欠番）
# 2000年は現行サイトに無い → archive.org のOICA当時の公式PDF（列=1999,2000）。id_=原本(raw)修飾子。
ARCHIVE = {
    2000: {
        "all":  "http://web.archive.org/web/20011202143429id_/http://www.oica.net/htdocs/statistics/tableaux2000/worldprod_country.PDF",
        "cars": "http://web.archive.org/web/20010821090700id_/http://www.oica.net/htdocs/statistics/tableaux2000/worldprod_cars.PDF",
    },
}
ARCHIVE_YEARS = [1999, 2000]

# EU27（現27か国）判定用キー（各PDFの表記ゆれ込み・大文字先頭一致）
EU27_KEYS = {
    "AUSTRIA", "BELGIUM", "BULGARIA", "CROATIA", "CYPRUS", "CZECH", "DENMARK", "DANEMARK",
    "ESTONIA", "FINLAND", "FRANCE", "GERMANY", "GREECE", "HUNGARY", "IRELAND", "ITALY",
    "LATVIA", "LITHUANIA", "LUXEMBOURG", "MALTA", "NETHERLANDS", "POLAND", "PORTUGAL",
    "ROMANIA", "SLOVAK", "SLOVENIA", "SPAIN", "SWEDEN",
}


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 2000:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def pdf_layout_text(path: Path) -> str:
    """pdftotext -layout（poppler）で列位置を多スペースに保った本文を得る。"""
    try:
        return subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=60).stdout
    except FileNotFoundError:
        sys.exit("! pdftotext(poppler) が必要です（brew install poppler）。列の分離に不可欠。")


def parse_rows(text: str) -> dict:
    """{ラベル(大文字): [int,...]} 。列は2つ以上の空白で区切られている前提（-layout）。
    ラベル直後から%を含むセルの手前までの数値セルを値列とする。"""
    out = {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        cells = re.split(r"\s{2,}", line.strip())     # 列= 2+スペース区切り
        if len(cells) < 2:
            continue
        label = re.sub(r"\(\d+\)|,.*$", "", cells[0]).strip().upper()  # 脚注(1)/注記",cars only"除去
        if not re.match(r"^[A-Z]", label):
            continue
        vals = []
        for c in cells[1:]:
            c = c.strip()
            if "%" in c or not c:
                break
            if re.fullmatch(r"[\d ]+", c):            # 数値セル（内部空白=千位）
                vals.append(int(c.replace(" ", "")))
            else:
                break                                  # 相手先(VDA等)テキストで打切り
        if vals:
            out.setdefault(label, vals)
    return out


def val_at(rows, label_key, col):
    for lab, vals in rows.items():
        if lab == label_key and len(vals) > col:
            return vals[col]
    return None


def is_member(lab):
    return any(lab.startswith(k) for k in EU27_KEYS) and "DOUBLE" not in lab and "EUROPEAN" not in lab


def compute_eu27(rows, col):
    """EU27合計。直近PDFは公式行"EUROPEAN UNION 27 countries + UK"−UK。
    2000年は EU15行が無EU27なので 加盟国合算 − EU27内二重計上 で構成。"""
    reg = uk = None
    for lab, vals in rows.items():
        if len(vals) <= col:
            continue
        if lab.startswith("EUROPEAN UNION 27 COUNTRIES"):
            reg = vals[col]
        if lab.startswith("UNITED KINGDOM"):
            uk = vals[col]
    if reg is not None and uk is not None:
        return reg - uk, f"公式EU27+UK({reg:,})−UK({uk:,})"
    # 2000年など：加盟国合算 − EU27内二重計上
    members = {lab: vals[col] for lab, vals in rows.items() if is_member(lab) and len(vals) > col}
    dbl = 0
    for lab, vals in rows.items():
        if "DOUBLE" in lab and len(vals) > col:
            parties = [k for k in EU27_KEYS if k in lab]
            if len(parties) >= 2:                     # 両者ともEU27 → 重複を1回控除
                dbl += vals[col]
    total = sum(members.values()) - dbl
    return total, f"加盟{len(members)}か国合算−二重計上{dbl:,}"


def pick(rows, key, col):
    """国名で行を引く（Double Countings/地域行は除外・startswith優先）。"""
    for lab, vals in rows.items():
        if lab.startswith(key) and "DOUBLE" not in lab and "EUROPEAN" not in lab:
            return lab, (vals[col] if len(vals) > col else None)
    for lab, vals in rows.items():
        if key in lab and "DOUBLE" not in lab and "EUROPEAN" not in lab:
            return lab, (vals[col] if len(vals) > col else None)
    return None, None


def main():
    ap = argparse.ArgumentParser(description="OICA公式PDFから国別自動車生産台数を取得（一次・Wikipedia不使用）")
    ap.add_argument("--year", type=int, required=True, help="取得年（直近窓=2019/2021/2022/2023/2024, または 2000）")
    ap.add_argument("--measure", choices=["all", "cars"], default="all", help="all=全車種(cars+CV) / cars=乗用車のみ")
    ap.add_argument("--countries", default="GERMANY,FRANCE,SPAIN,CZECH",
                    help="出力する国（カンマ区切り・部分一致, 大文字）。EU27合計は常に付与")
    ap.add_argument("--output-dir", default="./output")
    ap.add_argument("--cache-dir", default="./cache")
    args = ap.parse_args()

    y = args.year
    if y in ARCHIVE:
        url, years = ARCHIVE[y][args.measure], ARCHIVE_YEARS
    elif y in RECENT_YEARS:
        url, years = RECENT[args.measure], RECENT_YEARS
    else:
        sys.exit(f"! 未対応の年 {y}。直近窓={RECENT_YEARS} または {sorted(ARCHIVE)} を指定。"
                 f"（現行サイトは6年窓のみ・古い年はarchive.org経由の対応追加が必要）")
    col = years.index(y)

    cache = Path(args.cache_dir); cache.mkdir(parents=True, exist_ok=True)
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    pdf = download(url, cache / f"oica_{args.measure}_{'archive2000' if y in ARCHIVE else 'recent'}.pdf")
    rows = parse_rows(pdf_layout_text(pdf))

    eu27, eu27_how = compute_eu27(rows, col)
    recs = []
    for c in [c.strip().upper() for c in args.countries.split(",") if c.strip()]:
        lab, v = pick(rows, c, col)
        recs.append({"country": c, "matched": lab, "value": v,
                     "share_eu27_pct": round(v / eu27 * 100, 2) if (v and eu27) else None})
    recs.append({"country": "EU27", "matched": eu27_how, "value": eu27, "share_eu27_pct": 100.0})

    stem = f"{datetime.date.today():%Y%m%d}_oica_{args.measure}_{y}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["country", "matched_label", "value", "share_eu27_pct"])
        for r in recs:
            w.writerow([r["country"], r["matched"], r["value"], r["share_eu27_pct"]])
    meta = {"source": "OICA (International Organization of Motor Vehicle Manufacturers)", "url": url,
            "year": y, "measure": args.measure, "eu27_method": eu27_how,
            "note": "現行oica.netは6年窓PDFのみ・2000はarchive.org公式(id_)。独(GERMANY)直近はcars only(OICA未報告CV除く)。Wikipedia不使用。",
            "retrieved_at": datetime.datetime.now().astimezone().isoformat()}
    (out / f"{stem}.metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in recs:
        print(f"{r['country']:9} {str(r['value']):>10}  {r['share_eu27_pct']}%  ({r['matched']})")
    print("CSV:", out / f"{stem}.csv")


if __name__ == "__main__":
    main()
