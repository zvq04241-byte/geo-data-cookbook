#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — 空港別の旅客数（欧州・米国・日本・フィリピン）を取る。

  ★世界を一括で取れる無料データは無い。ACI・OAG・ICAOは有料。国ごとに組む。
  ★Eurostat の空港次元は rep_airp。geo=FR を渡すと 400。詳細は recipe.md。

使い方:
    python fetch.py --eu CDG,FRA,MAD --year 2024      # 欧州（Eurostat）
    python fetch.py --eu CDG --year 2024 --detail     # EU域内/域外まで
    python fetch.py --us ATL,JFK --year 2024          # 米国（BTS T-100）
    python fetch.py --jp --year 2023                  # 日本の国内線空港間流動
    python fetch.py --jp-intl --year 2024             # 日本の国際線（出入国管理統計）
    python fetch.py --ph --year 2024                  # フィリピン（MIAA＝NAIA / CAAP＝地方）
    python fetch.py --list-eu-airports FR
"""
import argparse, csv, hashlib, json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

EU = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_paoa"
ES = "https://api.e-stat.go.jp/rest/3.0/app/json"
# 米国 BTS Socrata。★これは「グラフ表示ビュー」ではなく実テーブルのID
BTS = "https://data.bts.gov/resource/r495-tyji.json"
# フィリピン。NAIA は MIAA、地方空港は CAAP。**別系統**で、互いに相手の数字を持たない
MIAA_PDF = "https://www.miaa.gov.ph/images/stories/operational-statistics/{stem}_Total_Statistics.pdf"
MIAA_PAGE = "https://www.miaa.gov.ph/index.php/reports/operational-statistics"
CAAP_PAGE = "https://www.caap.gov.ph/aircraft-passenger-and-cargo-movements/"
# 日本の国際線は航空輸送統計に無い。出入国管理統計「港別 出入国者」で代える
ES_IMMIG = "0003449063"
UA = {"User-Agent": "Mozilla/5.0"}
# よく使う空港の略称 → Eurostat の rep_airp コード
ALIAS = {"CDG": "FR_LFPG", "ORY": "FR_LFPO", "FRA": "DE_EDDF", "MAD": "ES_LEMD",
         "AMS": "NL_EHAM", "FCO": "IT_LIRF", "MUC": "DE_EDDM", "BCN": "ES_LEBL",
         "LIS": "PT_LPPT", "VIE": "AT_LOWW", "CPH": "DK_EKCH", "ARN": "SE_ESSA"}
COV = {"TOTAL": "合計", "NAT": "国内線", "INTL": "国際線",
       "INTL_EU27_2020": "国際線(EU域内)", "INTL_XEU27_2020": "国際線(EU域外)"}


def eu_airports(cc):
    r = httpx.get(EU, params={"format": "JSON", "lang": "EN", "freq": "A", "time": "2024",
                              "tra_meas": "PAS_CRD", "unit": "PAS", "tra_cov": "TOTAL",
                              "schedule": "TOTAL"}, headers=UA, timeout=300)
    r.raise_for_status()
    lab = r.json()["dimension"]["rep_airp"]["category"]["label"]
    return {k: v for k, v in lab.items() if k.startswith(cc.upper() + "_")}


def eu_fetch(code, year, detail, departures=False):
    # ★rep_airp。geo ではない
    # ★PAS_CRD は到着＋出発。米BTS（出発のみ）と並べるときは PAS_CRD_DEP に揃える
    meas = "PAS_CRD_DEP" if departures else "PAS_CRD"
    covs = list(COV) if detail else ["TOTAL", "NAT", "INTL"]
    out = {}
    for c in covs:
        r = httpx.get(EU, params={"format": "JSON", "lang": "EN", "freq": "A", "time": str(year),
                                  "rep_airp": code, "tra_meas": meas, "unit": "PAS",
                                  "schedule": "TOTAL", "tra_cov": c}, headers=UA, timeout=300)
        if r.status_code == 400 and "GEO" in r.text:
            raise SystemExit("400: 空港の次元は rep_airp（geo ではない）")
        if r.status_code != 200: continue
        j = r.json()
        v = list(j["value"].values())
        if v: out[c] = v[0]
    return out


def jp_flow(year, appid):
    q = {"appId": appid, "statsDataId": "0003173927",
         "cdTime": f"{year}100000", "limit": 100000}
    j = json.load(urllib.request.urlopen(f"{ES}/getStatsData?" + urllib.parse.urlencode(q), timeout=300))
    sd = j["GET_STATS_DATA"]["STATISTICAL_DATA"]
    cls = {c["@id"]: {x["@code"]: x["@name"] for x in
                      (c["CLASS"] if isinstance(c["CLASS"], list) else [c["CLASS"]])}
           for c in sd["CLASS_INF"]["CLASS_OBJ"]}
    rows = []
    for v in sd["DATA_INF"]["VALUE"]:
        try: n = int(v["$"])
        except (ValueError, KeyError): continue
        rows.append(dict(発空港=cls["cat02"].get(v["@cat02"], v["@cat02"]),
                         着空港=cls["cat01"].get(v["@cat01"], v["@cat01"]), 旅客数=n))
    return rows


def us_fetch(code, year):
    """米国 BTS T-100 Segment Summary By Origin Airport。
       ★total と domestic しか無い。国際線＝total−domestic で出す。
       ★出発空港基準なので**出発便のみ**。到着を含む Eurostat とは直接比べられない。"""
    r = httpx.get(BTS, params={
        "$select": "sum(total_passengers) as tot, sum(domestic_passengers) as dom",
        "$where": f"origin_airport_code='{code}' AND year='{year}'"},
        headers=UA, timeout=300)
    r.raise_for_status()
    j = r.json()
    if not j or j[0].get("tot") is None:
        return {}
    tot, dom = float(j[0]["tot"]), float(j[0]["dom"])
    return {"合計(出発のみ)": int(tot), "国内線(出発のみ)": int(dom),
            "国際線(出発のみ)": int(tot - dom)}


def jp_intl(year, appid):
    """日本の国際線。航空輸送統計には無いので出入国管理統計「港別 出入国者」で代える。
       ★これは出入国者数で、航空旅客数ではない。乗り継ぎのみの客は入らない。"""
    m = httpx.get(f"{ES}/getMetaInfo", params={"appId": appid, "statsDataId": ES_IMMIG},
                  timeout=300).json()["GET_META_INFO"]
    ports = {x["@name"]: x["@code"] for c in m["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
             if c["@id"] == "cat03" for x in c["CLASS"] if "（空港）" in x["@name"]}
    rows = []
    for nm, cd in ports.items():
        d = httpx.get(f"{ES}/getStatsData", params={
            "appId": appid, "statsDataId": ES_IMMIG, "cdCat03": cd,
            "cdCat01": "1000", "cdCat02": "1000", "limit": 200}, timeout=300).json()
        vs = d["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"].get("VALUE", [])
        vs = vs if isinstance(vs, list) else [vs]
        n = sum(int(v["$"]) for v in vs
                if v["@time"].startswith(str(year)) and v["$"].lstrip("-").isdigit())
        if n: rows.append({"空港": nm, "国際線出入国者": n})
    return sorted(rows, key=lambda r: -r["国際線出入国者"])


def _miaa_pdf_url():
    """PDFのファイル名に更新日が入るので、ページから拾う。URLを決め打ちにしない。"""
    r = httpx.get(MIAA_PAGE, headers=UA, timeout=180, follow_redirects=True)
    m = re.search(r'href="(/images/stories/operational-statistics/[^"]*Total_Statistics\.pdf)"', r.text)
    if not m: raise SystemExit("MIAA: Total_Statistics.pdf のリンクが見つからない")
    return "https://www.miaa.gov.ph" + m.group(1)


def ph_naia(year, cache_dir):
    """マニラ NAIA。MIAA の Operational Statistics（PDF）。
       到着・出発 × 国際・国内 × 旅客、2018年〜。CAAP には NAIA の数字は無い（全部0）。"""
    import subprocess
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf = cache_dir / "miaa_total_statistics.pdf"
    if not pdf.exists():
        pdf.write_bytes(httpx.get(_miaa_pdf_url(), headers=UA, timeout=300,
                                  follow_redirects=True).content)
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         capture_output=True, text=True).stdout
    lines = txt.splitlines()
    out, sect = {}, None
    for i, ln in enumerate(lines):
        m = re.match(r"\s*(Arriving|Departing)\s+(International|Domestic)\s+"
                     r"(Passengers|Flights)\b", ln)
        if m:
            # 左右2段組み。同じ行の右半分が Departing 側
            sect = (m.group(2), m.group(3)); years = None
            for j in range(i, min(i + 4, len(lines))):
                if "Month" in lines[j]:
                    years = re.findall(r"\b(19|20)\d\d\b", lines[j])
                    years = re.findall(r"\b(?:19|20)\d\d\b", lines[j]); break
            for j in range(i, min(i + 20, len(lines))):
                if lines[j].lstrip().startswith("Total"):
                    halves = [h for h in re.split(r"\bTotal\b", lines[j]) if h.strip()]
                    for side, h in zip(("Arriving", "Departing"), halves):
                        nums = [int(x.replace(",", "")) for x in
                                re.findall(r"[\d,]{4,}", h)]
                        half = len(years) // 2 if years else 0
                        ys = years[:len(nums)] if years else []
                        for y, n in zip(ys, nums):
                            if int(y) == year:
                                out[f"{sect[1]}_{sect[0]}_{side}"] = n
                    break
    if not out: return {}
    g = lambda k: out.get(k, 0)
    return {"国際線": g("Passengers_International_Arriving") + g("Passengers_International_Departing"),
            "国内線": g("Passengers_Domestic_Arriving") + g("Passengers_Domestic_Departing"),
            "国際線(到着)": g("Passengers_International_Arriving"),
            "国際線(出発)": g("Passengers_International_Departing"),
            "国内線(到着)": g("Passengers_Domestic_Arriving"),
            "国内線(出発)": g("Passengers_Domestic_Departing")}


def ph_caap(year, cache_dir):
    """フィリピンの地方空港。CAAP の AirpasscarANNUAL-{year}.xls。
       ★NAIA と Mactan(セブ) は別運営で、この表では**行はあるが全部0**。"""
    import xlrd
    cache_dir.mkdir(parents=True, exist_ok=True)
    xls = cache_dir / f"caap_annual_{year}.xls"
    if not xls.exists():
        page = httpx.get(CAAP_PAGE, headers=UA, timeout=180, follow_redirects=True).text
        cands = [u for u in re.findall(r'href="([^"]+\.xls)"', page, re.I)
                 if f"ANNUAL-{year}" in u]
        if not cands: raise SystemExit(f"CAAP: {year}年のファイルが無い")
        xls.write_bytes(httpx.get(cands[0], headers=UA, timeout=300,
                                  follow_redirects=True).content)
    s = xlrd.open_workbook(str(xls)).sheet_by_name("passenger")
    agg, cur = {}, None
    for r in range(10, s.nrows):
        a = str(s.cell_value(r, 0)).strip()
        if a: cur = a
        v = s.cell_value(r, 14)
        if cur and isinstance(v, (int, float)) and v:
            agg[cur] = agg.get(cur, 0) + v
    # 空港名の (Int'l.) / (Dom.) が国際・国内の別。列ではない
    # ★A列には空港名だけでなく地方名（Region I / CAR…）と "Total" 行も混じる
    skip = re.compile(r"^(Total|Region\b|CAR$|NCR$|ARMM|BARMM|CIVIL AVIATION|AERODROME|"
                      r"PASSENGER MOVEMENT|Airport$)", re.I)
    return [{"空港": k, "旅客数": int(v),
             "区分": "国際線" if "Int" in k else ("国内線" if "Dom" in k else "計")}
            for k, v in sorted(agg.items(), key=lambda x: -x[1]) if v and not skip.match(k)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eu", default="", help="空港コード（CDG,FRA…か FR_LFPG 形式）")
    ap.add_argument("--us", default="", help="米国の空港コード（ATL,JFK…）")
    ap.add_argument("--jp", action="store_true", help="日本の国内線空港間旅客流動")
    ap.add_argument("--jp-intl", action="store_true", help="日本の国際線（出入国管理統計）")
    ap.add_argument("--ph", action="store_true", help="フィリピン（NAIA＋地方空港）")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--detail", action="store_true", help="EU域内/域外まで分ける")
    ap.add_argument("--departures", action="store_true",
                    help="出発便のみに揃える（米BTSと並べるとき）")
    ap.add_argument("--list-eu-airports", default="", metavar="CC")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path("./data_bulk/other_primary"))
    a = ap.parse_args()

    if a.list_eu_airports:
        d = eu_airports(a.list_eu_airports)
        print(f"{a.list_eu_airports} の空港 {len(d)}件")
        for k, v in sorted(d.items())[:60]: print(f"   {k:<12}{v}")
        return 0

    rows = []
    if a.eu:
        for q in [x.strip().upper() for x in a.eu.split(",")]:
            code = ALIAS.get(q, q)
            v = eu_fetch(code, a.year, a.detail, a.departures)
            if not v:
                print(f"   {q}: {a.year}年のデータなし", file=sys.stderr); continue
            sfx = "(出発のみ)" if a.departures else ""
            rows.append(dict(source="Eurostat avia_paoa", airport=code, year=a.year,
                             **{COV[k] + sfx: v[k] for k in v}))
    if a.us:
        for q in [x.strip().upper() for x in a.us.split(",")]:
            v = us_fetch(q, a.year)
            if not v:
                print(f"   {q}: {a.year}年のデータなし（BTSは2014年〜）", file=sys.stderr); continue
            rows.append(dict(source="BTS T-100 (r495-tyji)", airport=q, year=a.year, **v))
    if a.jp or a.jp_intl:
        appid = os.environ.get("ESTAT_APP_ID")
        if not appid:
            for line in (Path(".env")).read_text().splitlines():
                if line.startswith("ESTAT_APP_ID"): appid = line.split("=", 1)[1].strip().strip('"\'')
        if not appid: raise SystemExit("ESTAT_APP_ID が要る")
    if a.jp:
        for r in jp_flow(a.year, appid):
            rows.append(dict(source="e-Stat 航空輸送統計 第9表", year=a.year, **r))
    if a.jp_intl:
        for r in jp_intl(a.year, appid):
            rows.append(dict(source="e-Stat 出入国管理統計 港別出入国者", year=a.year, **r))
    if a.ph:
        v = ph_naia(a.year, a.cache_dir / "miaa")
        if v: rows.append(dict(source="MIAA Operational Statistics", 空港="NAIA(マニラ)",
                               year=a.year, **v))
        else: print(f"   NAIA: {a.year}年のデータなし（MIAAは2018年〜）", file=sys.stderr)
        for r in ph_caap(a.year, a.cache_dir / "caap"):
            rows.append(dict(source="CAAP Passenger Movement", year=a.year, **r))
    if not rows: raise SystemExit("--eu / --us / --jp / --jp-intl / --ph のどれかが要る")

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9)); today = datetime.now(JST).strftime("%Y%m%d")
    tag = ("ph" if a.ph else "jpintl" if a.jp_intl else "jp" if a.jp
           else "us" if a.us else "eu")
    p = a.output_dir / f"{today}_airport_passengers_{tag}.csv"
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    (a.output_dir / f"{today}_airport_passengers_{tag}_metadata.json").write_text(
        json.dumps({"source": "Eurostat avia_paoa / BTS T-100 / e-Stat 航空輸送統計調査 第9表・"
                              "出入国管理統計 / MIAA / CAAP",
                    "note": "空港単位。都市単位にするには複数空港を足す（東京=成田+羽田 等）。"
                            "★米BTSは出発便のみ、日本の国際線は出入国者数で、"
                            "到着＋出発の旅客数である欧州・比とは母数が違う",
                    "year": a.year, "rows": len(rows),
                    "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(JST).isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {p.name}  rows={len(rows)}")
    for r in rows[:12]:
        print("   " + "  ".join(f"{k}={v:,}" if isinstance(v, int) and k != "year"
                                else f"{k}={v}"
                                for k, v in r.items() if k != "source"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
