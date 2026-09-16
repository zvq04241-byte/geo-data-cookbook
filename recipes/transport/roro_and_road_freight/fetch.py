#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — 国境を越える道路貨物を、英国のロールオン統計とEUの道路貨物統計から取る。

  ★英国 DfT PORT0205 は「随伴トラック」と「無随伴トレーラー」が別カテゴリ。
    渡航時間が長い航路ほど無随伴に寄る（仏4.6% / 蘭76.6% / 西79.2% / 瑞98.7%）。
  ★これは「港」の統計。ユーロトンネルは入っていない。
  ★Eurostat road_go_ia_lgtt の geo は**車両の国籍**。積地国ではない。
  詳細は recipe.md。

使い方:
    python fetch.py --uk-roro --year 2025
    python fetch.py --uk-roro --years 2016,2019,2025 --countries France,Spain,Netherlands
    python fetch.py --eu-road --geo PT,ES,FR --unload UK
"""
import argparse, csv, hashlib, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

DFT_PAGE = ("https://www.gov.uk/government/statistical-data-sets/"
            "port-and-domestic-waterborne-freight-statistics-port")
EU = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/road_go_ia_lgtt"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
ACC = "Road goods vehicles with or without accompanying trailers"
UNA = "Unaccompanied road goods trailers & semi-trailers"
# 国ではない集計行。相手国の列に同居する
NOT_A_COUNTRY = re.compile(r"Small Flows|^UK Domestic$|^Unspecified$|^All ", re.I)


def dft_download(cache_dir, table="port0205"):
    """★URLはメディアIDつきで更新のたび変わる。ページから拾う。
       ★落としたファイルの表番号を Cover シートで必ず確かめる（0302と取り違えやすい）。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    ods = cache_dir / f"{table}.ods"
    if not ods.exists():
        html = httpx.get(DFT_PAGE, headers=UA, timeout=120, follow_redirects=True).text
        hits = [u for u in re.findall(r'href="(https://assets\.publishing[^"]+\.ods)"', html)
                if table in u.lower()]
        if not hits:
            raise SystemExit(f"{table}.ods のリンクが見つからない。ページの構成が変わった")
        print(f"   取得中 {hits[0].split('/')[-1]}…", file=sys.stderr)
        ods.write_bytes(httpx.get(hits[0], headers=UA, timeout=600,
                                  follow_redirects=True).content)
    try:
        import pandas as pd  # noqa
    except ImportError:
        raise SystemExit("pandas が要る")
    import pandas as pd
    try:
        cover = pd.read_excel(ods, engine="odf", sheet_name="Cover", header=None)
    except ImportError:
        raise SystemExit("odfpy が要る（pip install odfpy）。.ods は openpyxl では開けない")
    title = str(cover.iloc[0, 0])
    if table.upper().replace("PORT", "PORT") not in title.upper().replace(" ", "") \
            and table[-4:] not in title:
        print(f"   ※Cover の表題: {title[:70]}", file=sys.stderr)
    return ods, title


def uk_roro(ods, years, countries):
    import pandas as pd
    # ★Data シートは説明行が3行ある
    d = pd.read_excel(ods, engine="odf", sheet_name="Data", skiprows=3)
    d.columns = [str(c).strip() for c in d.columns]
    d = d[(d["Direction"] == "Both Directions") & d["Cargo Name"].isin([ACC, UNA])]
    if years: d = d[d["Year"].isin(years)]
    rows = []
    for (yr, cc), g in d.groupby(["Year", "Port of Load Unload Country"]):
        cc = str(cc)
        if NOT_A_COUNTRY.search(cc): continue
        if countries and cc not in countries: continue
        a = g[g["Cargo Name"] == ACC]; u = g[g["Cargo Name"] == UNA]
        at = float(a["Tonnage (thousands)"].sum()); ut = float(u["Tonnage (thousands)"].sum())
        au = float(a["Units (thousands)"].sum()); uu = float(u["Units (thousands)"].sum())
        if at + ut <= 0: continue
        rows.append({"年": int(yr), "相手国": cc,
                     "随伴トラック_千t": round(at, 1), "無随伴トレーラー_千t": round(ut, 1),
                     "計_千t": round(at + ut, 1), "無随伴_%": round(ut / (at + ut) * 100, 1),
                     "随伴_千台": round(au, 1), "無随伴_千台": round(uu, 1),
                     "随伴1台当たりt": round(at / au, 1) if au else None,
                     "無随伴1台当たりt": round(ut / uu, 1) if uu else None})
    return sorted(rows, key=lambda r: (-r["年"], -r["計_千t"]))


def eu_road(geos, unload):
    rows = []
    for g in geos:
        r = httpx.get(EU, params={"format": "JSON", "lang": "EN", "geo": g,
                                  "c_unload": unload, "unit": "THS_T",
                                  "tra_type": "TOTAL", "nst07": "TOTAL"},
                      headers=UA, timeout=300)
        if r.status_code != 200:
            print(f"   {g}: {r.status_code}", file=sys.stderr); continue
        j = r.json()
        idx = j["dimension"]["time"]["category"]["index"]
        inv = {v: k for k, v in idx.items()}
        for k, v in j["value"].items():
            rows.append({"車両国籍": g, "揚地国": unload, "年": int(inv[int(k)]),
                         "千トン": round(float(v), 1)})
    return sorted(rows, key=lambda r: (r["車両国籍"], r["年"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uk-roro", action="store_true")
    ap.add_argument("--eu-road", action="store_true")
    ap.add_argument("--year", type=int)
    ap.add_argument("--years", default="", help="カンマ区切り")
    ap.add_argument("--countries", default="", help="相手国名（DfT の表記。Irish Republic 等）")
    ap.add_argument("--geo", default="PT,ES,FR", help="車両の国籍 ISO2")
    ap.add_argument("--unload", default="UK", help="揚地国")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path("./data_bulk/uk_dft"))
    a = ap.parse_args()
    if not (a.uk_roro or a.eu_road): raise SystemExit("--uk-roro か --eu-road が要る")

    rows, tag, src = [], "", ""
    if a.uk_roro:
        ys = [int(x) for x in a.years.split(",") if x.strip()] or ([a.year] if a.year else [])
        cs = {x.strip() for x in a.countries.split(",") if x.strip()}
        ods, title = dft_download(a.cache_dir)
        rows = uk_roro(ods, ys, cs); tag = "uk_roro"; src = f"UK DfT: {title[:90]}"
    if a.eu_road:
        gs = [x.strip().upper() for x in a.geo.split(",") if x.strip()]
        r2 = eu_road(gs, a.unload.upper())
        if rows:  # 両方指定されたら別ファイルにはせず eu を優先表示
            print("   ※--uk-roro と --eu-road は別々に実行する", file=sys.stderr)
        rows = r2; tag = "eu_road"; src = "Eurostat road_go_ia_lgtt"
    if not rows: raise SystemExit("0件")

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9)); today = datetime.now(JST).strftime("%Y%m%d")
    p = a.output_dir / f"{today}_{tag}.csv"
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    (a.output_dir / f"{today}_{tag}_metadata.json").write_text(json.dumps({
        "source": src,
        "note": "★DfTは『港』の統計でユーロトンネルを含まない。随伴と無随伴は別カテゴリで、"
                "足さないと道路貨物の全体にならない。Eurostat側の geo は車両の国籍であり積地国ではない",
        "rows": len(rows), "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "retrieved_at": datetime.now(JST).isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"saved: {p.name}  rows={len(rows)}")
    for r in rows[:16]:
        print("   " + "  ".join(f"{k}={v:,}" if isinstance(v, (int, float)) and k != "年"
                                else f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
