#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — ILOSTAT の産業別就業者（DF_EMP_TEMP_SEX_ECO_NB）を取る。

  賃金の ilo/wages_ranking とは **次元数が違う**（あちらは4、こちらは5）。
  キーは REF_AREA.FREQ.MEASURE.SEX.ECO。詳細は recipe.md。

使い方:
    python fetch.py --countries JPN,CHE,ARE,HUN --mode tertiary
    python fetch.py --countries JPN --mode isic
    python fetch.py --countries JPN,CHE --mode sector
    python fetch.py --countries JPN --isic K
    python fetch.py --countries ARE,PHL --mode tertiary --year 2008   # 古い年は ISIC Rev.3 で組む

分母の取り決め（モードごとに1系統に固定する）:
    tertiary / isic / --isic … その国・年の ISIC の合計（Rev.4 なら ECO_ISIC4_TOTAL、Rev.3 なら ECO_ISIC3_TOTAL）
    sector                   … ECO_SECTOR_TOTAL（無ければその国は出さず、metadata の dropped に残す）
"""
import argparse, csv, hashlib, io, json, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

BASE = "https://sdmx.ilo.org/rest/data/ILO,DF_EMP_TEMP_SEX_ECO_NB"
ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"   # ★XMLになるのを防ぐ

# 第3次産業の4区分（Singelmann型）。ILOSTAT側にこの集計は無い＝本レシピの取り決め
TERTIARY = {
    "ISIC4": {
        "流通関連サービス": ["G", "H", "J"],          # 卸小売・運輸保管・情報通信
        "消費関連サービス": ["I", "R", "S", "T"],      # 宿泊飲食・芸術娯楽・その他・家事
        "生産関連サービス": ["K", "L", "M", "N"],      # 金融保険・不動産・専門技術・管理支援
        "社会関連サービス": ["O", "P", "Q"],           # 公務・教育・保健福祉
    },
    "ISIC3": {
        "流通関連サービス": ["G", "I"],                # 卸売小売・運輸倉庫通信
        "消費関連サービス": ["H", "P"],                # ホテル・レストラン・家事
        "生産関連サービス": ["J", "K"],                # 金融・不動産賃貸事業サービス
        "社会関連サービス": ["L", "M", "N"],           # 公務・教育・保健社会事業
    },
}
# 4区分に入らない第3次産業。「その他」に出す（X=分類不能 は第3次に入れず、別の列に出す）
TERTIARY_OTHER = {"ISIC4": ["U"],          # 治外法権機関
                  "ISIC3": ["O", "Q"]}     # その他のサービス・治外法権機関
DIVISIONS = {"ISIC4": [chr(c) for c in range(ord("A"), ord("U") + 1)],
             "ISIC3": [chr(c) for c in range(ord("A"), ord("Q") + 1)]}


def fetch(countries, start):
    # ★5次元。空の段はドットで置く（JPN.SEX_T. だと 422）
    key = f"{'+'.join(countries)}.A..SEX_T."
    r = httpx.get(f"{BASE}/{key}", params={"startPeriod": start},
                  headers={"Accept": ACCEPT}, timeout=300, follow_redirects=True)
    if r.status_code == 422:
        raise SystemExit(f"キーの次元数が合いません（5次元）: {r.text[:120]}")
    if r.status_code == 404 and "No data" in r.text[:100]:
        return []
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def isic_rev(v: dict) -> str | None:
    """その国・年の ISIC の版。Rev.4 の合計があれば Rev.4、無ければ Rev.3。"""
    if v.get("ECO_ISIC4_TOTAL"):
        return "ISIC4"
    if v.get("ECO_ISIC3_TOTAL"):
        return "ISIC3"
    return None


def latest(V, area, mode):
    """★最新年は国ごとに違う。そのモードの分母が取れる最新年を国ごとに選ぶ"""
    if mode == "sector":
        ys = [y for (a, y), v in V.items() if a == area and v.get("ECO_SECTOR_TOTAL")]
    else:
        ys = [y for (a, y), v in V.items() if a == area and isic_rev(v)]
    return max(ys) if ys else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", required=True, help="ISO3 カンマ区切り")
    ap.add_argument("--mode", default="tertiary", choices=["tertiary", "isic", "sector"])
    ap.add_argument("--isic", default="", help="単一のISIC Rev.4 大分類だけ欲しいとき（例 K）")
    ap.add_argument("--start", type=int, default=2015)
    ap.add_argument("--year", type=int, default=0, help="年を揃えたいとき（既定は国ごとの最新）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    a = ap.parse_args()
    ccs = [c.strip().upper() for c in a.countries.split(",") if c.strip()]
    start = min(a.start, a.year) if a.year else a.start   # --year 2008 で --start 2015 のままだと0件になる
    mode = "isic_one" if a.isic else a.mode
    rows = fetch(ccs, start)
    if not rows:
        raise SystemExit("0件。国コード（ISO3）と年を確認")

    V = defaultdict(dict)
    for x in rows:
        if x["OBS_VALUE"]:
            V[(x["REF_AREA"], int(x["TIME_PERIOD"]))][x["ECO"]] = float(x["OBS_VALUE"])

    out, meta_years, dropped, checks = [], {}, {}, {}
    for c in ccs:
        y = a.year or latest(V, c, a.mode)
        if not y or (c, y) not in V:
            dropped[c] = "該当年なし"
            print(f"  {c}: 該当年なし", file=sys.stderr); continue
        v = V[(c, y)]
        rev = isic_rev(v)
        if a.mode == "sector" and not a.isic:
            tot = v.get("ECO_SECTOR_TOTAL")
            denom = "ECO_SECTOR_TOTAL"
        else:
            tot = v.get(f"ECO_{rev}_TOTAL") if rev else None
            denom = f"ECO_{rev}_TOTAL" if rev else None
        if not tot:
            dropped[c] = f"{y}年に分母（{denom or 'ISIC の合計'}）が無い"
            print(f"  {c}: {dropped[c]}", file=sys.stderr); continue
        meta_years[c] = y
        rec = {"iso3": c, "year": y, "total_employment": tot, "denominator": denom}
        chk = {}
        if rev and a.mode != "sector":
            # ISIC 大分類の積み上げと合計の照合。欠けた大分類と差を残す（ハマり所9・10）
            have = [d for d in DIVISIONS[rev] if f"ECO_{rev}_{d}" in v]
            missing = [d for d in DIVISIONS[rev] if d not in have]
            stacked = sum(v[f"ECO_{rev}_{d}"] for d in have) + v.get(f"ECO_{rev}_X", 0)
            chk = {"isic_rev": rev, "missing_divisions": missing,
                   "sum_gap_pct": round((stacked - tot) / tot * 100, 2)}
            if missing or abs(chk["sum_gap_pct"]) > 0.5:
                print(f"  {c} {y}: {rev} 欠けた大分類={missing} 積み上げと合計の差={chk['sum_gap_pct']}%",
                      file=sys.stderr)
            rec["isic_rev"] = rev
        if a.isic:
            k = f"ECO_ISIC4_{a.isic.upper()}"
            if rev != "ISIC4":
                dropped[c] = f"{y}年は {rev}。--isic は Rev.4 の記号（Rev.3 では別の業種を指す）"
                print(f"  {c}: {dropped[c]}", file=sys.stderr); continue
            rec[f"isic_{a.isic.upper()}_pct"] = round(v[k] / tot * 100, 2) if k in v else None
        elif a.mode == "sector":
            for s, lab in (("AGR", "第1次"), ("IND", "第2次"), ("SER", "第3次")):
                k = f"ECO_SECTOR_{s}"
                rec[f"{lab}_pct"] = round(v[k] / tot * 100, 2) if k in v else None
            if "ECO_SECTOR_X" in v:
                rec["分類不能_pct"] = round(v["ECO_SECTOR_X"] / tot * 100, 2)
            parts = [rec[f"{lab}_pct"] for lab in ("第1次", "第2次", "第3次")]
            chk = {"sum_pct": round(sum(p for p in parts if p is not None) + rec.get("分類不能_pct", 0), 2),
                   "missing": [lab for lab, p in zip(("第1次", "第2次", "第3次"), parts) if p is None]}
        elif a.mode == "isic":
            pre = "isic_" if rev == "ISIC4" else "isic3_"   # 版が違えば同じ記号でも別の業種
            for k, val in sorted(v.items()):
                if k.startswith(f"ECO_{rev}_") and not k.endswith("TOTAL"):
                    rec[k.replace(f"ECO_{rev}_", pre) + "_pct"] = round(val / tot * 100, 2)
        else:  # tertiary
            groups = TERTIARY[rev]
            ser_codes = [d for cs in groups.values() for d in cs] + TERTIARY_OTHER[rev]
            ser = sum(v.get(f"ECO_{rev}_{d}", 0) for d in ser_codes)
            rec["第3次産業就業者割合"] = round(ser / tot * 100, 1)
            got = 0.0
            for lab, codes in groups.items():
                s = sum(v.get(f"ECO_{rev}_{d}", 0) for d in codes)
                rec[lab] = round(s / ser * 100, 1) if ser else None
                got += s
            # その他＝4区分に入らない第3次（Rev.4 は U、Rev.3 は O・Q）。4区分＋その他＝100%
            rec["その他"] = round((ser - got) / ser * 100, 1) if ser else None
            # X（分類不能）は第3次に入れない。分母（合計）には含まれるので、大きい国では第3次割合が低めに出る
            rec["分類不能X_pct"] = round(v.get(f"ECO_{rev}_X", 0) / tot * 100, 1)
        checks[c] = chk
        out.append(rec)

    if not out:
        raise SystemExit(f"出力0件: {dropped}")
    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    p = a.output_dir / f"{today}_ilostat_employment_{a.isic.lower() or a.mode}.csv"
    cols = sorted({k for r in out for k in r}, key=lambda k: (k not in ("iso3", "year"), k))
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    measures = sorted({x["MEASURE"] for x in rows})
    (a.output_dir / f"{today}_ilostat_employment_{a.isic.lower() or a.mode}_metadata.json").write_text(
        json.dumps({"source": "ILO ILOSTAT SDMX — DF_EMP_TEMP_SEX_ECO_NB",
                    "key": "REF_AREA.FREQ.MEASURE.SEX.ECO（5次元）",
                    "measure": measures,   # 応答の MEASURE 列の値（EMP_TEMP_NB＝就業者。労働力人口ではない）
                    "mode": mode,
                    "scope": f"指定した{len(ccs)}か国のうち値のある{len(out)}か国",
                    "denominator_rule": ("ECO_SECTOR_TOTAL" if a.mode == "sector" and not a.isic
                                         else "その国・年の ISIC の合計（ECO_ISIC4_TOTAL か ECO_ISIC3_TOTAL）"),
                    "tertiary_mapping": ({"groups": TERTIARY, "other": TERTIARY_OTHER}
                                         if mode == "tertiary" else None),
                    "years_by_country": meta_years,
                    "dropped": dropped,
                    "checks_by_country": checks,
                    "rows": len(out),
                    "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(JST).isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {p.name}  rows={len(out)}  dropped={len(dropped)}")
    for r in out:
        print("   " + "  ".join(f"{k}={v}" for k, v in r.items() if k != "total_employment"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
