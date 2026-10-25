#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — UN Tourism（旧UNWTO）の観光統計を一括zipから取る。

  World Bank WDI の `ST.INT.RCPT.CD` は中国が1997〜2004年の8件しかない（保管庫の WDI_CSV で確認）。
  一次の UN Tourism（2026年5月版 zip）の観光収入は 1995〜2024年・214の報告国・地域。詳細は recipe.md。

使い方:
    python fetch.py --list
    python fetch.py --domain inbound_expenditure --countries China,France,Poland,Mexico
    python fetch.py --domain inbound_arrivals --countries Japan --output-dir ./output
    python fetch.py --refresh                       # 最新版zipを取り直す
"""
import argparse, csv, hashlib, io, json, re, sys, urllib.request, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

VAULT = Path("./data_bulk/other_primary/unwto")
PAGE = "https://www.unwto.org/tourism-statistics/key-tourism-statistics"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
# フォルダ名の一部 → 呼び名
DOMAINS = {
    "domestic_trips": "01_Domestic/01_Total_trips",
    "domestic_accommodation": "01_Domestic/02_Accommodation",
    "inbound_arrivals": "02_Inbound/01_Total_arrivals",
    "inbound_expenditure": "02_Inbound/02_Expenditure",      # ★観光収入
    "inbound_by_region": "02_Inbound/03_Total_arrivals_by_region",
    "inbound_by_purpose": "02_Inbound/04_Total_arrivals_by_main_purpose",
    "inbound_by_transport": "02_Inbound/05_Total_arrivals_by_mode_of_transport",
    "inbound_accommodation": "02_Inbound/06_Accommodation",
    "outbound_departures": "03_Outbound/01_Total_departures",
    "outbound_expenditure": "03_Outbound/02_Expenditure",
    "accommodation_hotels": "04_Accommodation/01_Accommodation",
    "macroeconomic": "05_Macroeconomic",
    "employment": "06_Employment",
    "sdgs": "07_SDGs",
}


def get(url, n=None):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180)
    return r.read() if n is None else r.read(n)


def latest_zip_url():
    """掲載ページから最新の一括zipのURLを拾う（ファイル名に年月が入る）"""
    html = get(PAGE, 1_200_000).decode("utf-8", "replace")
    urls = re.findall(r'href="(https?://[^"]*bulk_data_download[^"]*\.zip)"', html)
    if not urls:
        raise RuntimeError("掲載ページに一括zipのリンクが見つからない（構成が変わった可能性）")
    return sorted(urls)[-1]


def ensure_zip(refresh=False):
    VAULT.mkdir(parents=True, exist_ok=True)
    have = sorted(VAULT.glob("UN_Tourism_bulk_*.zip"))
    if have and not refresh:
        return have[-1]
    url = latest_zip_url()
    name = "UN_Tourism_bulk_" + (re.search(r"(\d{2}_\d{4})\.zip", url) or ["", "latest"])[1] + ".zip"
    p = VAULT / name
    if not p.exists():
        p.write_bytes(get(url))
        print(f"取得 {p.name}  {p.stat().st_size/1e6:.1f}MB  ← {url}", file=sys.stderr)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="inbound_expenditure", choices=sorted(DOMAINS))
    ap.add_argument("--countries", default="", help="英語名 カンマ区切り。空なら全件")
    ap.add_argument("--indicator", default="travel",
                    help="収入/支出の別: travel（既定・教材の国際観光収入）/ total / passenger")
    ap.add_argument("--indicator-contains", default="",
                    help="expenditure 以外で indicator_label を部分一致で1つに絞る"
                         "（例: 'overnight visitors (tourists)'）。到着客数などは複数指標が同じ表に入る")
    ap.add_argument("--from-year", type=int, default=1995)
    ap.add_argument("--partner", default="auto", choices=["auto","world","breakdown","all"],
                    help="相手先の扱い。auto=…_by_region 等は内訳、ほかは World")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    import pandas as pd

    zp = ensure_zip(a.refresh)
    z = zipfile.ZipFile(zp)
    if a.list:
        for i in z.infolist():
            if i.filename.endswith(".xlsx"):
                print(f"  {i.filename}  {i.file_size/1e6:.1f}MB")
        return 0

    if a.partner == "auto":
        a.partner = "breakdown" if "_by_" in a.domain else "world"
    key = DOMAINS[a.domain]
    names = [i for i in z.namelist() if key in i and i.endswith(".xlsx")]
    if not names:
        raise RuntimeError(f"{key} に該当するxlsxが無い: {[i for i in z.namelist() if i.endswith('.xlsx')][:5]}")
    # ★1枚目は Overview（説明文）。必ず "Data" を読む
    df = pd.read_excel(io.BytesIO(z.read(names[0])), sheet_name="Data")
    src_years = [int(df.year.min()), int(df.year.max())]
    n_reporters_file = int(df.reporter_area_label.nunique())
    # ★相手先の扱いはドメインで変わる。一律に World で絞ると地域別の中身が消える
    #   （2026-09-15、inbound_by_region を World で潰して28行にしてしまった）
    if "partner_area_label" in df:
        if a.partner == "world":
            df = df[df.partner_area_label == "World"]
        elif a.partner == "breakdown":
            df = df[df.partner_area_label != "World"]
        # partner=all はそのまま
    if "indicator_label" in df and a.domain.endswith("expenditure"):
        # ★total / travel / passenger transport が同じ表に混在する。足すと二重計上
        pick = {"travel": " - travel - ", "total": " - total - ",
                "passenger": " - passenger transport - "}[a.indicator]
        df = df[df.indicator_label.str.contains(pick, regex=False)]
    elif "indicator_label" in df and a.indicator_contains:
        df = df[df.indicator_label.str.contains(a.indicator_contains, regex=False)]
        if df.empty:
            raise RuntimeError(f"--indicator-contains {a.indicator_contains!r} に一致する指標が無い")
    indicators = sorted(df.indicator_label.unique()) if "indicator_label" in df else []
    if len(indicators) > 1:
        # 到着客数（visitors / tourists / same-day / cruise）・宿泊（guests / overnights）等が混在。
        # 足したり平均したりすると意味のない値になる
        print(f"★ 指標が {len(indicators)} 種混在（--indicator-contains で1つに絞る）: {indicators}",
              file=sys.stderr)
    if a.countries:
        want = [c.strip() for c in a.countries.split(",")]
        have = set(df.reporter_area_label.unique())
        miss = [c for c in want if c not in have]
        if miss:
            import difflib
            raise RuntimeError(f"UN Tourism に無い国名: {miss} / 近いもの: "
                               + str({m: difflib.get_close_matches(m, have, 3, 0.6) for m in miss}))
        df = df[df.reporter_area_label.isin(want)]
    df = df[df.year >= a.from_year]

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    out = a.output_dir / f"{today}_unwto_{a.domain}.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    reps = sorted(df.reporter_area_label.unique())
    meta = {"source": "UN Tourism (旧UNWTO) bulk data download",
            "zip": zp.name, "member": names[0], "sheet": "Data",
            "domain": a.domain, "indicator_filter": a.indicator if a.domain.endswith("expenditure") else None,
            "unit": sorted(set(df.get("unit", pd.Series(dtype=str)).dropna().unique())),
            "indicators": indicators,
            "years": [int(df.year.min()), int(df.year.max())],
            "source_years": src_years,
            "n_reporters_in_file": n_reporters_file,
            "n_reporters": len(reps),
            "requested_countries": [c.strip() for c in a.countries.split(",")] if a.countries else None,
            "scope": (f"指定した {len(reps)} 報告国・地域" if a.countries else
                      f"このファイルの報告国・地域 全{len(reps)}（香港・マカオ・台湾は別行。年で報告国が変わる）"),
            "countries": reps,
            "rows": len(df),
            "csv_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "retrieved_at": datetime.now(JST).isoformat()}
    (a.output_dir / f"{today}_unwto_{a.domain}_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out.name}  rows={len(df)}  年 {meta['years'][0]}〜{meta['years'][1]}  単位 {meta['unit']}")
    if a.countries and len(indicators) <= 1:
        p = df.pivot_table(index="year", columns="reporter_area_label", values="value", aggfunc="first")
        for y in (p.index.min(), p.index.max()):
            print(f"   {int(y)}年  " + "  ".join(f"{c} {p.loc[y,c]:,.0f}" for c in p.columns if p.loc[y, c] == p.loc[y, c]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
