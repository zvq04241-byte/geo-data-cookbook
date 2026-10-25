#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — Eurostat avia_par/avia_gor → 国ペア航空フロー（欧州・西アジア・アフリカ間）。

リファレンス実装。検証済みの「勝ちパターン」。
- 旅客: avia_par_<cc> (tra_meas=PAS_CRD), 貨物: avia_gor_<cc> (tra_meas=FRM_LD_NLD)
- 報告国＝DEFAULT_REPORTERS（EU27＋EFTA＋加盟候補国のうち、Eurostat に表があるもの。
  確かめた記録は references/reporters_probe_20261026.csv）。
- 地域は国連の区分（references/m49_overview.csv）から引く。M49 から動かす国は MOVED に理由つきで書く。
- 取れなかった報告国は metadata の reporters_missing と scope に出す。通信の失敗は止める。

使い方:
    python fetch.py --measure pax  --year 2024 --output-dir ./output
    python fetch.py --measure cargo --year 2024 --output-dir ./output
"""
import argparse, json, urllib.request, urllib.error, sys, io, csv, hashlib
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
HERE = Path(__file__).resolve().parent

# EU27＋EFTA＋加盟候補国のうち、2026-10-26 に avia_par/avia_gor の表があった34か国。
# 表が無い（HTTP 404 "not available for dissemination"）: cz li al ua md ge xk
# 表はあるが2020年以降は空: uk（2019年まで。EU 離脱による）
# 2024年が空で2023年はある: ba（前年に落ちる。metadata に年が残る）
DEFAULT_REPORTERS = ("be bg dk de ee ie el es fr hr it cy lv lt lu hu mt nl at pl pt ro si sk fi se "
                     "is no ch me mk rs tr ba").split()

M49_CSV = HERE / "references" / "m49_overview.csv"
M49_SHA256 = "ccfd0a7b9b406b7b75bdfb4725af35adcca88e6102898401c46e29a796656037"
EUROSTAT_TO_ISO = {"EL": "GR", "UK": "GB"}          # Eurostat 独自の2文字
# M49 の区分から動かす国（理由を書く。ここに無い国は M49 どおり）
MOVED = {
    "CY": ("Europe", "M49 では西アジア。EU 加盟国で Eurostat の報告国なので欧州に入れる"),
    "IR": ("West Asia", "M49 では南アジア。旧版の地域割り（西アジア）を引き継ぐ。M49 どおりにするならこの行を消す"),
    "XK": ("Europe", "M49 の表に無い（コソボ）。Eurostat の相手国コードに現れる"),
}
ORDER = {"Europe": 0, "West Asia": 1, "Africa": 2}


def load_regions():
    h = hashlib.sha256(M49_CSV.read_bytes()).hexdigest()
    if h != M49_SHA256:
        raise SystemExit(f"★M49 の表が記録した版と違う（sha256 {h[:16]}…）。差し替えたなら M49_SHA256 を直す")
    reg = {}
    with open(M49_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            iso = (r["ISO-alpha2 Code"] or "").strip()
            if not iso and r["ISO-alpha3 Code"] == "NAM":
                iso = "NA"     # この表はナミビアの "NA" が欠測扱いで空になっている
            if not iso:
                raise SystemExit(f"★M49 の表に ISO2 が空の行: {r['Country or Area']}。対応を足す")
            if r["Region Name"] in ("Europe", "Africa"):
                reg[iso] = r["Region Name"]
            elif r["Sub-region Name"] == "Western Asia":
                reg[iso] = "West Asia"
            else:
                reg[iso] = None            # M49 にあるが3地域の外（例 US, CN, RU は欧州）
    for iso, (r, _) in MOVED.items():
        reg[iso] = r
    return reg


REGION = None


def region(code):
    """Eurostat の2文字コード → 'Europe' / 'West Asia' / 'Africa' / None（3地域外） / '?'（M49 に無い）"""
    global REGION
    if REGION is None:
        REGION = load_regions()
    iso = EUROSTAT_TO_ISO.get(code, code)
    return REGION.get(iso, "?")


def fetch(ds, year, unit, meas):
    """(data, status) を返す。status: ok / empty / not_disseminated / error:…"""
    url = f"{API}/{ds}?format=JSON&lang=EN&freq=A&unit={unit}&tra_meas={meas}&time={year}"
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return None, ("not_disseminated" if e.code == 404 else f"error:HTTP{e.code}")
    except Exception as e:
        return None, f"error:{type(e).__name__}"
    return (d, "ok") if d.get("value") else (None, "empty")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", choices=["pax", "cargo"], default="pax")
    ap.add_argument("--year", default="2024")
    ap.add_argument("--reporters", default=",".join(DEFAULT_REPORTERS))
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.measure == "pax":
        prefix, unit, meas, valcol, div = "avia_par", "PAS", "PAS_CRD", "pax_thousand", 1000
    else:
        prefix, unit, meas, valcol, div = "avia_gor", "T", "FRM_LD_NLD", "cargo_ton", 1

    requested = [c.strip().lower() for c in args.reporters.split(",") if c.strip()]
    flows, meta_pair, used, missing, errors = defaultdict(float), {}, {}, {}, {}
    dropped = Counter()          # 3地域外・M49 に無い相手で落とした値（コード別）
    for cc in requested:
        data = None; yr = None; tried = []
        for y in [args.year, str(int(args.year) - 1)]:
            d, st = fetch(f"{prefix}_{cc}", y, unit, meas)
            tried.append(f"{y}:{st}")
            if st == "ok":
                data, yr = d, y; break
            if st.startswith("error"):
                errors[cc] = tried; break
        if cc in errors:
            continue
        if not data:
            missing[cc] = "; ".join(tried)      # 404（表が無い）／空（その年の値が無い）
            continue
        used[cc] = yr
        cat = data["dimension"]["airp_pr"]["category"]
        # ★ハマり所1: value のキーは"位置インデックス"。index で位置→コードに逆引きする
        pos2code = {v: k for k, v in cat["index"].items()}
        tmp = defaultdict(float)   # ★ハマり所2: 報告国内は空港ペアを sum
        for pos, v in data["value"].items():
            code = pos2code.get(int(pos))
            parts = code.split("_") if code else []
            if len(parts) != 4:
                dropped["(コードの形が違う)"] += float(v)
                continue
            rep_iso, _, part_iso, _ = parts
            if rep_iso == part_iso:           # ★国内線除外（意図した除外。数えない）
                continue
            rr, pr = region(rep_iso), region(part_iso)
            if rr in (None, "?") or pr in (None, "?"):
                tag = part_iso if pr in (None, "?") else rep_iso
                dropped[f"{tag}({'M49に無い' if '?' in (rr, pr) else '3地域外'})"] += float(v)
                continue
            if rr == "Europe" and pr == "Europe":   # 欧州域内は除外（3地域"間"。意図した除外）
                continue
            key = frozenset({rep_iso, part_iso})
            tmp[key] += float(v)
            meta_pair[key] = (rep_iso, part_iso, rr, pr)
        for key, v in tmp.items():
            flows[key] = max(flows[key], v)   # ★ハマり所3: 報告国"間"は max（二重計上回避）

    if errors:
        raise SystemExit("★取得に失敗した報告国がある（通信・サーバ側）。部分集計を出さずに止める: "
                         + json.dumps(errors, ensure_ascii=False))

    fallback = sorted(c for c, y in used.items() if y != args.year)
    scope = (f"報告国{len(requested)}か国を要求（取得できたのは{len(used)}"
             + (f"。取れなかった: {','.join(missing)}" if missing else "")
             + (f"。前年値で代用: {','.join(fallback)}" if fallback else "")
             + "）。少なくとも一方が報告国である国ペアのみ。欧州域内・国内線・3地域外の相手は除く")
    if missing:
        print(f"[注意] 取れなかった報告国 {len(missing)}: {missing}", file=sys.stderr)

    rows = []
    for key, val in flows.items():
        a, b, ra, rb = meta_pair[key]
        (ca, cra), (cb, crb) = sorted([(a, ra), (b, rb)], key=lambda x: ORDER[x[1]])  # ★ハマり所4: 地域順で正規化
        pair = f"{cra}-{crb}" if cra != crb else f"{cra} 域内"
        rows.append({"route": f"{ca}-{cb}", "a_iso": ca, "b_iso": cb,
                     "a_region": cra, "b_region": crb, "region_pair": pair,
                     valcol: round(val / div, 1), "scope": scope})   # ★ハマり所5: 旅客は /1000（千人）
    rows.sort(key=lambda r: -r[valcol])

    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    out_csv = args.output_dir / f"{today}_eurostat_airflow_{args.measure}.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["route","a_iso","b_iso","a_region","b_region","region_pair",valcol,"scope"])
        w.writeheader(); w.writerows(rows)
    meta = {"source": "Eurostat " + ("avia_par (PAS_CRD)" if args.measure == "pax" else "avia_gor (FRM_LD_NLD)"),
            "year": args.year, "scope": scope,
            "reporters_requested": requested, "reporters_used": used, "reporters_missing": missing,
            "regions": "国連 M49（references/m49_overview.csv）。動かした国: "
                       + "; ".join(f"{k}→{v[0]}（{v[1]}）" for k, v in MOVED.items()),
            "dropped_partner_value": {k: round(v / div, 1) for k, v in dropped.most_common()},
            "dropped_note": "3地域外・M49 に無い相手で落とした値（報告国内の空港ペア合計。報告国間の max 前）",
            "rows": len(rows),
            "unit": "千人/年(双方向)" if args.measure == "pax" else "トン/年(双方向)",
            "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
            "retrieved_at": datetime.now(JST).isoformat()}
    (args.output_dir / f"{today}_eurostat_airflow_{args.measure}_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out_csv.name}  rows={len(rows)}  top={rows[0]['route']}={rows[0][valcol]}")
    print(f"scope: {scope}")

if __name__ == "__main__":
    main()
