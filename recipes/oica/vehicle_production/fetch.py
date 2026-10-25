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
from __future__ import annotations
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

# EU27（現27か国）の国名。PDF の行ラベル（脚注・注記を外し大文字にしたもの）と**完全一致**で照合する。
# 表記ゆれ: OICA 2000年版は DANEMARK・SLOVAK REPUBLIC、直近版は SLOVAKIA・CZECH REPUBLIC。
EU27_NAMES = {
    "AUSTRIA": "AT", "BELGIUM": "BE", "BULGARIA": "BG", "CROATIA": "HR", "CYPRUS": "CY",
    "CZECH REPUBLIC": "CZ", "CZECHIA": "CZ", "DENMARK": "DK", "DANEMARK": "DK", "ESTONIA": "EE",
    "FINLAND": "FI", "FRANCE": "FR", "GERMANY": "DE", "GREECE": "GR", "HUNGARY": "HU",
    "IRELAND": "IE", "ITALY": "IT", "LATVIA": "LV", "LITHUANIA": "LT", "LUXEMBOURG": "LU",
    "MALTA": "MT", "NETHERLANDS": "NL", "POLAND": "PL", "PORTUGAL": "PT", "ROMANIA": "RO",
    "SLOVAKIA": "SK", "SLOVAK REPUBLIC": "SK", "SLOVENIA": "SI", "SPAIN": "ES", "SWEDEN": "SE",
}
EU15_CODES = {"AT", "BE", "DK", "FI", "FR", "DE", "GR", "IE", "IT", "LU", "NL", "PT", "ES", "SE"}
assert len(set(EU27_NAMES.values())) == 27


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


NUM = re.compile(r"(?<!\S)(\d{1,3}(?: \d{3})*|N/A)(?!\S)")


def parse_rows(text: str, years: list[int]) -> dict:
    """{ラベル: {"vals": {年: int|None}, "flag": 注記, "raw": 元ラベル}}。

    値は**見出しの年の列位置**に割り当てる（空欄の列があっても左に詰めない）。
    旧版は空欄を詰めて読み、2000年版の DANEMARK（2000年だけ 18台）を1999年の値にしていた。
    """
    lines = text.splitlines()
    tok = lambda y: rf"(?<!\S){y}(?!\S)"          # 「1999-2000」のような題の中の年は見出しにしない
    head = next((ln for ln in lines if all(re.search(tok(y), ln) for y in years)), None)
    if head is None:
        raise ValueError(f"見出しに年 {years} がそろう行が無い")
    ends = [re.search(tok(y), head).end() for y in years]
    out = {}
    for line in lines:
        m = re.match(r"\s*(\S.*?)(?=\s{2,}|$)", line)
        if not m:
            continue
        raw = m.group(1).strip()
        label = re.sub(r"\(\d+\)", "", raw)
        flag = ""
        if "," in label:
            label, flag = label.split(",", 1)
            flag = flag.strip()
        label = re.sub(r"^-\s*", "", label).strip().upper()
        if not re.match(r"^[A-Z]", label):
            continue
        vals = {}
        for t in NUM.finditer(line, m.end()):
            if t.end() > ends[-1] + 12:          # 年の列より右（増減率など）は読まない
                break
            i = min(range(len(ends)), key=lambda k: abs(ends[k] - t.end()))
            if years[i] in vals:                 # 組版で右にずれて詰まったセル（例「29 891 N/A」）は右の空き列へ
                free = [k for k in range(i + 1, len(ends)) if years[k] not in vals]
                if not free:
                    raise ValueError(f"1つの列に2つの値: {raw!r} {years[i]}")
                i = free[0]
            vals[years[i]] = None if t.group(1) == "N/A" else int(t.group(1).replace(" ", ""))
        if vals and label not in out:
            out[label] = {"vals": vals, "flag": flag, "raw": raw}
    return out


def v_of(rows, label, y):
    r = rows.get(label)
    return None if r is None else r["vals"].get(y)


def dc_rows(rows, y, codes: set):
    """Double Countings のうち、両方の国が codes に入る行の (ラベル, 値)。"""
    hits = []
    for lab, r in rows.items():
        if not lab.startswith("DOUBLE COUNTINGS"):
            continue
        parties = [x.strip() for x in lab[len("DOUBLE COUNTINGS"):].split("/")]
        cc = [EU27_NAMES.get(x) for x in parties]
        if len(cc) == 2 and all(c in codes for c in cc if c) and all(cc):
            v = r["vals"].get(y)
            if v:
                hits.append((lab, v))
    return hits


TOL = 0.002   # 小計と内訳の和の差の許容（0.2%）。直近PDFは EU15 小計が内訳の和より最大21,000台（0.12%）小さい年がある


def _check(name_a, a, name_b, b):
    """小計と内訳の和を照らす。一致／差の記録／止める（差が TOL を超える）。"""
    if a == b:
        return f"{name_a} ＝ {name_b}（一致）"
    if abs(a - b) > TOL * a:
        raise ValueError(f"{name_a} と {name_b} {b:,} の差 {b - a:+,} が {TOL:.1%} を超える")
    print(f"  ! {name_a} と {name_b} {b:,} が {b - a:+,} 台ずれる（OICA の表のまま。値は小計の行を使う）")
    return f"{name_a} と {name_b} {b:,} の差 {b - a:+,}（OICA の表の小計と内訳が合わない。値は小計の行による）"


def compute_eu27(rows, y):
    """EU27合計と、照合・内訳の記録を返す。照合が合わなければ止める。"""
    members = {lab: r for lab, r in rows.items() if lab in EU27_NAMES}
    present = {lab: r["vals"].get(y) for lab, r in members.items() if r["vals"].get(y) is not None}
    found_codes = {EU27_NAMES[lab] for lab in present}
    absent = sorted(set(EU27_NAMES.values()) - found_codes)
    uk = v_of(rows, "UNITED KINGDOM", y)
    info = {"members_in_table": {lab: v for lab, v in present.items()},
            "eu27_countries_not_in_table": absent,
            "member_flags": {lab: members[lab]["flag"] for lab in present if members[lab]["flag"]}}
    reg = v_of(rows, "EUROPEAN UNION 27 COUNTRIES + UK", y)
    if reg is not None:
        if uk is None:
            raise ValueError("UNITED KINGDOM の行が無い")
        s = sum(present.values()) + uk
        info["check"] = _check(f"公式行 EU27+UK {reg:,}", reg, f"表の加盟国{len(present)}か国＋英国 の和", s)
        return reg - uk, f"公式EU27+UK({reg:,})−UK({uk:,})", info
    # 2000年: EU27 の行は無い（当時の区分は EU15）。EU15 行で照合してから、現27か国で組む
    eu15 = v_of(rows, "EUROPEAN UNION", y)
    if eu15 is None or uk is None:
        raise ValueError("EU27+UK 行も EUROPEAN UNION 行も無い（照合の相手が無いので止める）")
    p15 = {lab: v for lab, v in present.items() if EU27_NAMES[lab] in EU15_CODES}
    d15 = dc_rows(rows, y, EU15_CODES)
    s15 = sum(p15.values()) + uk - sum(v for _, v in d15)
    chk = _check(f"当時の EUROPEAN UNION 行 {eu15:,}", eu15, "EU15加盟国＋英国−二重計上 の和", s15)
    d27 = dc_rows(rows, y, set(EU27_NAMES.values()))
    total = sum(present.values()) - sum(v for _, v in d27)
    info["double_countings"] = dict(d27)
    info["check"] = chk + "。EU27 は照合の相手が無い自己合算"
    return total, f"表の加盟{len(present)}か国合算−二重計上{sum(v for _, v in d27):,}（自己合算）", info


def pick(rows, key, y):
    """国名で行を引く。完全一致を優先し、無ければ前方一致が1件だけのとき採る（複数なら止める）。"""
    if key in rows:
        return key, rows[key]["vals"].get(y), rows[key]["flag"]
    cand = [lab for lab in rows if lab.startswith(key) and not lab.startswith(("DOUBLE", "EUROPEAN"))]
    if len(cand) > 1:
        raise ValueError(f"{key} に複数の行が当たる: {cand}")
    if not cand:
        return None, None, ""
    lab = cand[0]
    return lab, rows[lab]["vals"].get(y), rows[lab]["flag"]


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
    try:
        rows = parse_rows(pdf_layout_text(pdf), years)
        eu27, eu27_how, eu27_info = compute_eu27(rows, y)
        recs = []
        for c in [c.strip().upper() for c in args.countries.split(",") if c.strip()]:
            lab, v, flag = pick(rows, c, y)
            if lab is None:
                raise ValueError(f"{c} の行が無い")
            recs.append({"country": c, "matched": lab, "value": v, "flag": flag,
                         "share_eu27_pct": round(v / eu27 * 100, 2) if (v and eu27) else None})
    except ValueError as e:
        sys.exit(f"! {e}")
    recs.append({"country": "EU27", "matched": eu27_how, "value": eu27,
                 "flag": "; ".join(f"{k}: {v}" for k, v in eu27_info["member_flags"].items()),
                 "share_eu27_pct": 100.0})
    scope = (f"指定の{len(recs) - 1}か国（{args.countries}）と EU27 合計。"
             f"EU27 は OICA の表に行がある加盟{len(eu27_info['members_in_table'])}か国の和"
             f"（表に無い国 {','.join(eu27_info['eu27_countries_not_in_table'])}）。"
             + ("注記つきの国（cars only 等）は車種の範囲が違う。" if eu27_info["member_flags"] else ""))

    stem = f"{datetime.date.today():%Y%m%d}_oica_{args.measure}_{y}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["country", "matched_label", "value", "share_eu27_pct", "flag", "scope"])
        for r in recs:
            w.writerow([r["country"], r["matched"], r["value"], r["share_eu27_pct"], r["flag"], scope])
    meta = {"source": "OICA (International Organization of Motor Vehicle Manufacturers)", "url": url,
            "year": y, "measure": args.measure, "countries_requested": args.countries,
            "scope": scope, "eu27_method": eu27_how, "eu27_detail": eu27_info,
            "note": ("現行oica.netは6年窓PDFのみ・2000はarchive.org公式(id_)。直近の全車種PDFは "
                     "独・フィンランドが cars only、仏が cars and LCV only、蘭・スウェーデンが yearly only（行ラベルの注記）。"
                     "注記は flag 列と eu27_detail.member_flags。Wikipedia不使用。"),
            "retrieved_at": datetime.datetime.now().astimezone().isoformat()}
    (out / f"{stem}.metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in recs:
        print(f"{r['country']:9} {str(r['value']):>10}  {r['share_eu27_pct']}%  ({r['matched']}) {r['flag']}")
    print("範囲:", scope)
    print("照合:", eu27_info["check"])
    print("CSV:", out / f"{stem}.csv")


if __name__ == "__main__":
    main()
