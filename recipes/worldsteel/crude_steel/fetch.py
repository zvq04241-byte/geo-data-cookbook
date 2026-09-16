#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""worldsteel/crude_steel — 世界鉄鋼協会(worldsteel)公式PDFから国別 粗鋼生産量を取得（Wikipedia不使用）。

worldsteel は粗鋼生産の一次出典。サイト(`worldsteel.org`)はJS描画で WebFetch は本文を返さない
→ 公式PDFを直DLして pdftotext -layout でパースする。
 - 直近年: "World Steel in Figures"(年次) の "Crude steel production by process" 表。
   国名→先頭の数値=総粗鋼生産(百万t)。**EU27は "European Union (27)" 行が直接報告される**。
 - 2000年など: "Steel Statistical Yearbook 2002" の Table 4(Total Production of Crude Steel,
   千t・列=1992..2001)。EU27区分は当時無いので EU15行＋新規加盟国の合算で構成。
★罠: 同PDF内の "Apparent steel use"(見かけ消費) 表と混同しない（消費≠生産）。単位は年で違う(Mt/千t)。

使い方:
  python fetch.py --year 2024 --output-dir ./output     # WSIF(百万t)。EU27直接
  python fetch.py --year 2000 --output-dir ./output     # SSY2002 Table4(千t→百万t)。EU27=合算
"""
import argparse, csv, json, re, subprocess, sys, datetime, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

WSIF = "https://worldsteel.org/wp-content/uploads/World-Steel-in-Figures-2025-3.pdf"  # 直近(2024)
SSY2002 = "https://worldsteel.org/wp-content/uploads/Steel-Statistical-Yearbook-2002.pdf"  # 1992-2001
SSY_YEARS = list(range(1992, 2002))     # Table4 の列順（10列）

# 2000年EU27を作るための「EU15以外の現加盟国」（SSY2002表記）
NEW_MEMBERS = ["CZECH REPUBLIC", "POLAND", "HUNGARY", "SLOVAK REPUBLIC", "SLOVENIA",
               "ROMANIA", "BULGARIA", "ESTONIA", "LATVIA", "LITHUANIA", "CROATIA"]
COUNTRY_ALIASES = {"GERMANY": ["GERMANY", "F.R. GERMANY"], "CZECH": ["CZECH REPUBLIC", "CZECHIA"]}


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 2000:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        dest.write_bytes(r.read())
    return dest


def layout(path):
    try:
        return subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, timeout=90).stdout
    except FileNotFoundError:
        sys.exit("! pdftotext(poppler) が必要（brew install poppler）。")


def _cells(line):
    return [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]


def parse_wsif(text):
    """WSIF "Crude steel production by process" 表限定。行署名= [国, 総Mt, BOF%, EAF%, '-', '100.0']。
    先頭数値=総粗鋼生産(百万t)。順位番号を拾わないよう '- 100.0' 署名で限定。"""
    out = {}
    for line in text.splitlines():
        cs = _cells(line)
        if len(cs) >= 6 and cs[4] == "-" and cs[5].startswith("100") and re.fullmatch(r"\d+(?:\.\d+)?", cs[1] or ""):
            lab = re.sub(r"\s+e$", "", cs[0]).strip().upper()
            if re.match(r"^[A-Z(]", lab) and lab not in out:
                out[lab] = float(cs[1])
    return out


def parse_ssy_table4(text):
    """SSY2002 Table4(Total Production of Crude Steel, 千t・列1992-2001)。
    ★銑鉄など別表を拾わないよう、"Total Production of Crude Steel" ヘッダ〜次Table の窓に限定。"""
    lines = text.splitlines()
    # 目次(TOC)行は末尾がページ番号→除外。実ヘッダは "…Crude Steel" で終わる。
    start = next((i for i, ln in enumerate(lines)
                  if re.search(r"total production of crude steel", ln, re.I) and not re.search(r"\d\s*$", ln)), None)
    if start is None:
        return {}
    out = {}
    for ln in lines[start + 1:]:
        if re.match(r"\s*Table\s", ln):        # 次の表ヘッダで打切り
            break
        cs = _cells(ln)
        if len(cs) < 11 or not re.match(r"^[A-Z]", cs[0].strip().upper()):
            continue
        nums = []
        for c in cs[1:]:
            if re.fullmatch(r"[\d ]+", c):
                nums.append(int(c.replace(" ", "")))
            else:
                break
        if len(nums) >= 10 and cs[0].strip().upper() not in out:
            out[cs[0].strip().upper()] = nums[:10]
    return out


def get(rows, key):
    for alias in COUNTRY_ALIASES.get(key, [key]):
        for lab, v in rows.items():
            if lab == alias or lab.startswith(alias):
                return lab, v
    return None, None


def main():
    ap = argparse.ArgumentParser(description="worldsteel公式PDFから国別粗鋼生産量(百万t)を取得（一次・Wikipedia不使用）")
    ap.add_argument("--year", type=int, required=True, help="2024（WSIF）または 1992-2001（SSY2002, 例 2000）")
    ap.add_argument("--countries", default="GERMANY,FRANCE,SPAIN,CZECH")
    ap.add_argument("--output-dir", default="./output")
    ap.add_argument("--cache-dir", default="./cache")
    args = ap.parse_args()
    cache = Path(args.cache_dir); cache.mkdir(parents=True, exist_ok=True)
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    wanted = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    recs = {}

    if args.year == 2024:
        url = WSIF
        rows = parse_wsif(layout(download(url, cache / "worldsteel_wsif.pdf")))
        for c in wanted:
            _, v = get(rows, c); recs[c] = v
        _, eu = get(rows, "EUROPEAN UNION"); eu27, how = eu, "公式 European Union (27) 行"
    elif args.year in SSY_YEARS:
        url = SSY2002; col = SSY_YEARS.index(args.year)
        rows = parse_ssy_table4(layout(download(url, cache / "worldsteel_ssy2002.pdf")))
        for c in wanted:
            _, v = get(rows, c); recs[c] = round(v[col] / 1000, 3) if v else None
        _, eu15 = get(rows, "EUROPEAN UNION")   # EU15行にはUK含む→EU27ではUKを控除
        _, uk = get(rows, "UNITED KINGDOM")
        add = sum(rows[m][col] for m in NEW_MEMBERS if m in rows)
        eu27 = round((eu15[col] - uk[col] + add) / 1000, 1) if (eu15 and uk) else None
        how = (f"EU15({eu15[col]/1000:.1f})−UK({uk[col]/1000:.1f})＋新規加盟"
               f"{sum(1 for m in NEW_MEMBERS if m in rows)}か国合算") if (eu15 and uk) else "算出不可"
    else:
        sys.exit(f"! 未対応の年 {args.year}。2024(WSIF) か 1992-2001(SSY2002) を指定。")

    stem = f"{datetime.date.today():%Y%m%d}_worldsteel_crude_{args.year}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["country", "crude_steel_Mt", "share_eu27_pct"])
        for c in wanted:
            v = recs[c]; w.writerow([c, v, round(v / eu27 * 100, 2) if (v and eu27) else None])
        w.writerow(["EU27", eu27, 100.0])
    meta = {"source": "World Steel Association (worldsteel)", "url": url, "year": args.year,
            "unit": "million tonnes crude steel", "eu27_method": how,
            "note": "WSIFは百万t・EU27直接報告／SSY2002は千t・列1992-2001でEU27は合算。'Apparent steel use'(消費)と混同しない。Wikipedia不使用。",
            "retrieved_at": datetime.datetime.now().astimezone().isoformat()}
    (out / f"{stem}.metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    for c in wanted:
        v = recs[c]; print(f"{c:9} {str(v):>8} Mt  {round(v/eu27*100,2) if (v and eu27) else None}%")
    print(f"{'EU27':9} {str(eu27):>8} Mt  ({how})")
    print("CSV:", out / f"{stem}.csv")


if __name__ == "__main__":
    main()
