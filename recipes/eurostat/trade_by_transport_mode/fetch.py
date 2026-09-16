#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — EU各国の貿易を輸送手段別（海上・航空・道路ほか）に額と重量で取る。

  ★dissemination API には無い。Comext のバルク（.7z）にある。DS-059331 は404。
  ★.dat には品目別の行と PRODUCT=TOTAL の合計行が同居する。全部足すと二重計上。
  ★相手国 QS は「船舶・航空機への積込み」。ジェット燃料が航空貨物に紛れ込む。
  ★Comext はその年のEU定義を使う。英国は2019年のファイルに1行も出てこない（当時は域内）。
    古い年をそのまま引けばよく、--exclude-partner は新しい年を旧定義に合わせるときだけ。
  詳細は recipe.md。

使い方:
    python fetch.py --year 2025 --reporters FR,PT --scope extra
    python fetch.py --year 2025 --reporters FR,PT --scope extra --exclude-partner GB
    python fetch.py --list-years
"""
import argparse, csv, hashlib, html, json, re, sys, urllib.parse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

BASE = "https://ec.europa.eu/eurostat/api/dissemination/files"
DIR = "comext/COMEXT_DATA/TRANSPORT_HS"
UA = {"User-Agent": "Mozilla/5.0"}
EU27 = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
        "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
# ★国ではない特殊コード。QS は船舶・航空機への積込み（bunkers and stores）
SPECIAL = {"QR", "QS", "QU", "QV", "QW", "QX", "QY", "QZ"}
MODE = {"1": "海上", "2": "鉄道", "3": "道路", "4": "航空", "5": "郵便",
        "7": "固定施設", "8": "内陸水路", "9": "自走", "0": "その他"}
ORDER = ["海上", "航空", "道路", "鉄道", "内陸水路", "固定施設", "自走", "郵便", "その他"]


def listing():
    r = httpx.get(BASE, params={"dir": DIR}, headers=UA, timeout=120, follow_redirects=True)
    r.raise_for_status()
    out = []
    for h in re.findall(r'href="([^"]*downfile=[^"]+)"', r.text):
        p = urllib.parse.unquote(html.unescape(h).split("downfile=")[1])
        if p.endswith(".7z"): out.append(p)
    return out


def download(year, cache_dir):
    """MM=52 が年計。trhs_v2_YYYY52.7z"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    dat = cache_dir / f"trhs_{year}52.dat"
    if dat.exists(): return dat
    stem = f"trhs_v2_{year}52.7z"
    if not any(p.endswith(stem) for p in listing()):
        raise SystemExit(f"{stem} が無い。--list-years で確認する")
    z = cache_dir / stem
    if not z.exists():
        url = BASE + "?downfile=" + urllib.parse.quote(f"{DIR}/{stem}", safe="")
        print(f"   取得中 {stem}（約48MB）…", file=sys.stderr)
        with httpx.stream("GET", url, headers=UA, timeout=900, follow_redirects=True) as r:
            r.raise_for_status()
            with z.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20): f.write(chunk)
    try:
        import py7zr
    except ImportError:
        raise SystemExit("py7zr が要る（pip install py7zr）。.7z は zipfile では開けない")
    print(f"   展開中（約248MB）…", file=sys.stderr)
    with py7zr.SevenZipFile(z) as a: a.extractall(cache_dir)
    if not dat.exists():
        raise SystemExit(f"{dat.name} が出てこない: {list(cache_dir.iterdir())[:5]}")
    return dat


def aggregate(dat, reporters, flow, scope, exclude):
    """★PRODUCT=TOTAL の行だけ使う。品目別と混ぜると二重計上になる。"""
    want = {"export": "2", "import": "1"}[flow]
    agg = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    miss = defaultdict(lambda: [0, 0])          # 重量の欠測を数える
    with dat.open(newline="") as f:
        for r in csv.DictReader(f):
            rep = r["REPORTER"]
            if rep not in reporters or r["FLOW"] != want: continue
            if r["PRODUCT"] != "TOTAL": continue
            p = r["PARTNER"]
            if p in SPECIAL: continue
            # ★このファイルは域外のみ。EU27 判定は保険（年によって加盟国が違うため）
            if scope == "extra" and p in EU27: continue
            if p in exclude: continue
            b = MODE.get(r["TRANSPORT_MODE"], "その他")
            try: v = float(r["VALUE_EUR"] or 0)
            except ValueError: v = 0.0
            q = (r["QUANTITY_KG"] or "").strip()
            m = miss[(rep, b)]; m[0] += 1
            if q in ("", "0"): m[1] += 1
            agg[rep][b][0] += v
            agg[rep][b][1] += float(q) if q not in ("", "0") else 0.0
    return agg, miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--reporters", default="FR,PT", help="報告国 ISO2 カンマ区切り")
    ap.add_argument("--flow", choices=["export", "import"], default="export")
    ap.add_argument("--scope", choices=["extra", "all"], default="extra",
                    help="★TRANSPORT_HS は域外のみ。域内は TRANSPORT_NST07 側にある")
    ap.add_argument("--exclude-partner", default="",
                    help="相手国を除く。原問が「EUにイギリスを含む」ならGB")
    ap.add_argument("--list-years", action="store_true")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path("./data_bulk/eurostat_comext"))
    a = ap.parse_args()

    if a.list_years:
        ys = sorted({re.search(r"_(\d{4})52\.7z$", p).group(1)
                     for p in listing() if re.search(r"_\d{4}52\.7z$", p)})
        print(f"年計のある年 {len(ys)}件: {', '.join(ys)}")
        return 0

    reporters = [x.strip().upper() for x in a.reporters.split(",") if x.strip()]
    exclude = {x.strip().upper() for x in a.exclude_partner.split(",") if x.strip()}
    dat = download(a.year, a.cache_dir)
    agg, miss = aggregate(dat, set(reporters), a.flow, a.scope, exclude)

    rows = []
    for rep in reporters:
        d = agg.get(rep)
        if not d:
            print(f"   {rep}: 該当なし", file=sys.stderr); continue
        TV = sum(x[0] for x in d.values()); TQ = sum(x[1] for x in d.values())
        for b in ORDER:
            if b not in d: continue
            n, mq = miss[(rep, b)]
            rows.append({"報告国": rep, "年": a.year, "flow": a.flow, "scope": a.scope,
                         "除外相手国": ",".join(sorted(exclude)) or "-", "輸送手段": b,
                         "額_EUR": int(d[b][0]), "額_%": round(d[b][0] / TV * 100, 2),
                         "重量_t": int(d[b][1] / 1000), "重量_%": round(d[b][1] / TQ * 100, 2),
                         "重量欠測_%": round(mq / n * 100, 1) if n else 0.0})
    if not rows: raise SystemExit("0件。--reporters と --year を見直す")

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9)); today = datetime.now(JST).strftime("%Y%m%d")
    p = a.output_dir / f"{today}_comext_transport_{a.flow}_{a.scope}_{a.year}.csv"
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (p.with_name(p.stem + "_metadata.json")).write_text(json.dumps({
        "source": "Eurostat Comext bulk / COMEXT_DATA/TRANSPORT_HS",
        "file": dat.name, "year": a.year, "flow": a.flow, "scope": a.scope,
        "note": "PRODUCT=TOTAL の行のみ集計（品目別と混ぜると二重計上）。"
                "相手国コード Q* は国ではないので除外（QS=船舶・航空機への積込み）。"
                "★英国は2021年から域外。原問の年の定義に合わせること",
        "excluded_partners": sorted(exclude), "rows": len(rows),
        "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "retrieved_at": datetime.now(JST).isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"saved: {p.name}  rows={len(rows)}")
    for rep in reporters:
        rs = [r for r in rows if r["報告国"] == rep]
        if not rs: continue
        print(f"\n  {rep} {a.year}年 {a.flow} ({a.scope}"
              + (f", {'/'.join(sorted(exclude))}除く" if exclude else "") + ")")
        print(f"    {'手段':<8}{'額%':>8}{'重量%':>8}{'重量欠測%':>10}")
        for r in rs:
            print(f"    {r['輸送手段']:<8}{r['額_%']:>7.1f}%{r['重量_%']:>7.1f}%{r['重量欠測_%']:>9.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
