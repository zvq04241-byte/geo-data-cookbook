"""fetch.py — ILO ILOSTAT 製造業 時間当たり賃金 国別ランキング取得（SDMX）

ILOSTAT の SDMX REST から製造業(ECO_AGGREGATE_MAN)の時間当たり賃金を取得し、
通貨(USD/PPP/LCU)別に国別ランキング上位N国を CSV + metadata.json に保存する。

時間給を直接報告していない国は「月給 ÷ (週実働時間 × 52/12)」で換算（週時間も無ければ月給/173h）。

使い方:
    # USD・上位20・2018年以降の最新値
    python fetch.py --currency USD --top-n 20 --output-dir ./output

    # PPP 調整・対象国を指定
    python fetch.py --currency PPP --countries LUX,CHE,USA,JPN --output-dir ./output

このレシピが扱う範囲:
- 製造業の時間当たり賃金（直接 or 月給換算）× 通貨 × 国別ランキング上位N（認証不要・SDMX-CSV）

このレシピが扱わない範囲:
- 産業横断・全産業平均 → ECO_AGGREGATE_TOTAL 等に変更（別パラメータ）
- 性別内訳 → SEX_T(計) 以外（別レシピ）
- 時系列推移 → 1か国の年次推移（別レシピ）
"""
from __future__ import annotations  # py3.9 で PEP604 `X | None` 注釈を使うため

import argparse
import csv
import hashlib
import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ─── 定数 ───
ILO_SDMX = "https://sdmx.ilo.org/rest/data/ILO"
ILO_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"

# 主要国（ISO alpha-3）— 高賃金〜低賃金を網羅
DEFAULT_COUNTRIES = [
    "LUX", "CHE", "NOR", "DNK", "USA", "BEL", "NLD", "AUT", "IRL", "FIN",
    "DEU", "FRA", "SWE", "AUS", "CAN", "GBR", "ITA", "NZL", "ISL", "ESP",
    "KOR", "JPN", "SGP", "EST", "CZE", "LVA", "LTU", "GRC", "POL", "SVK",
    "ROU", "HUN", "PRT", "BGR", "CHL", "CHN", "RUS", "TUR", "ARG", "BRA",
    "MEX", "THA", "ZAF", "COL", "VNM", "IND", "IDN", "PAK", "BGD", "NGA",
]
CUR_MAP = {"USD": "CUR_TYPE_USD", "PPP": "CUR_TYPE_PPP", "LCU": "CUR_TYPE_LCU"}
STANDARD_MONTHLY_HOURS = 173  # 週時間データが無い国の換算用標準値


class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source = source
        self.url = url
        self.kind = kind
        self.original = original


def fetch_sdmx_csv(url: str, retries: int = 3, timeout: int = 120) -> list[dict]:
    """SDMX-CSV を取得して dict のリストで返す。

    重要: Accept ヘッダで CSV を要求しないと SDMX-ML(XML) が返る。
    "No data" が冒頭にある場合は空（該当データなし）。
    """
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=15, read=timeout, write=30, pool=10),
                headers={"Accept": ILO_ACCEPT}, follow_redirects=True,
            ) as cl:
                r = cl.get(url)
            if r.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"status {r.status_code}", request=r.request, response=r)
            if "No data" in r.text[:100]:
                return []
            reader = csv.DictReader(io.StringIO(r.text))
            return list(reader)
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("SDMX retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError(
        source="ILO ILOSTAT", url=url, kind="SDMX_FETCH_FAIL",
        message=f"failed after {retries} attempts", original=last_err)


def latest_by_country(rows: list[dict], cur_filter: str | None = None) -> dict:
    """SDMX-CSV 行から {REF_AREA: (OBS_VALUE, TIME_PERIOD)} の最新年を返す。"""
    out: dict = {}
    for row in rows:
        cc = row.get("REF_AREA", "")
        if cur_filter and row.get("CUR", "") != cur_filter:
            continue
        val = row.get("OBS_VALUE", "")
        if not val:
            continue
        try:
            year = int(row.get("TIME_PERIOD", 0))
            val = float(val)
        except (ValueError, TypeError):
            continue
        if cc not in out or year > out[cc][1]:
            out[cc] = (val, year)
    return out


def build_urls(cc_str: str, year_from: int) -> dict:
    """3 データフローの SDMX URL を組み立てる。

    ハマり所: 時間給/月給は CUR 次元があるためキー末尾が "...MAN.?"（ドット有り）、
    週労働時間は CUR 次元が無いため "...MAN?"（ドット無し）。ドット数=次元数。
    """
    return {
        "hourly": (f"{ILO_SDMX},DF_EAR_EHRA_SEX_ECO_CUR_NB/"
                   f"{cc_str}.A.EAR_EHRA_NB.SEX_T.ECO_AGGREGATE_MAN.?"
                   f"startPeriod={year_from}&detail=dataonly"),
        "monthly": (f"{ILO_SDMX},DF_EAR_EMTA_SEX_ECO_CUR_NB/"
                    f"{cc_str}.A.EAR_EMTA_NB.SEX_T.ECO_AGGREGATE_MAN.?"
                    f"startPeriod={year_from}&detail=dataonly"),
        "hours": (f"{ILO_SDMX},DF_HOW_TEMP_SEX_ECO_NB/"
                  f"{cc_str}.A.HOW_TEMP_NB.SEX_T.ECO_AGGREGATE_MAN?"
                  f"startPeriod={year_from}&detail=dataonly"),
    }


def derive_hourly(countries: list[str], hourly: dict, monthly: dict,
                  hours: dict) -> dict:
    """国ごとに時間給を確定。直接報告→月給換算→月給/173h の順。"""
    results = {}
    for cc in countries:
        if cc in hourly:
            v, yr = hourly[cc]
            results[cc] = {"hourly": v, "year": yr, "source": "direct"}
        elif cc in monthly and cc in hours:
            mv, myr = monthly[cc]
            wh, wyr = hours[cc]
            monthly_hours = wh * 52 / 12
            if monthly_hours > 0:
                results[cc] = {"hourly": mv / monthly_hours,
                               "year": min(myr, wyr), "source": "monthly_div_hours"}
        elif cc in monthly:
            mv, myr = monthly[cc]
            results[cc] = {"hourly": mv / STANDARD_MONTHLY_HOURS,
                           "year": myr, "source": "monthly_div_173"}
    return results


def save_csv(ranked: list[dict], out_path: Path, *, currency: str, unit: str) -> None:
    fields = ["Rank", "Area", "Currency", "Value", "Year", "Source", "Unit"]
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for r in ranked:
            w.writerow([r["rank"], r["cc"], currency, round(r["hourly"], 2),
                        r["year"], r["source"], unit])


def save_metadata(meta_path: Path, *, currency: str, year_from: int, top_n: int,
                  urls: dict, out_csv: Path, row_count: int, n_direct: int,
                  n_derived: int, unit: str) -> dict:
    csv_bytes = out_csv.read_bytes()
    meta = {
        "task_name": f"ilostat_wages_manufacturing_{currency.lower()}_top{top_n}",
        "source": {
            "name": "ILO ILOSTAT (SDMX REST, manufacturing hourly earnings)",
            "urls": urls,
            "single_source": True,
        },
        "query": {
            "currency": currency, "currency_code": CUR_MAP.get(currency),
            "year_from": year_from, "top_n": top_n,
            "economic_activity": "ECO_AGGREGATE_MAN", "sex": "SEX_T",
        },
        "units": unit,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "derivation": {"direct": n_direct, "converted": n_derived},
        "notes": (
            "時間給は直接報告 or 月給÷(週時間×52/12) or 月給/173h で確定（source列に種別）。"
            "TIME_PERIOD は国ごとに最新年が異なる（全行同年ではない）。"
            "LCU は現地通貨で国際比較に不向き。USD/PPP 推奨。"
        ),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return meta


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="ILO ILOSTAT 製造業 時間賃金ランキング取得")
    ap.add_argument("--currency", default="USD", choices=list(CUR_MAP.keys()),
                    help="USD / PPP / LCU (default USD)")
    ap.add_argument("--top-n", type=int, default=20, help="上位N (default 20)")
    ap.add_argument("--year-from", type=int, default=2018,
                    help="この年以降の最新値を採用 (default 2018)")
    ap.add_argument("--countries", default=None,
                    help="ISO3 をカンマ区切りで指定（省略時は主要50か国）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    countries = ([c.strip().upper() for c in args.countries.split(",")]
                 if args.countries else DEFAULT_COUNTRIES)
    cc_str = "+".join(countries)
    cur_code = CUR_MAP[args.currency]
    unit = f"{args.currency}/h"
    urls = build_urls(cc_str, args.year_from)

    # ─── 3 データフロー取得 ───
    try:
        logging.info("SDMX 取得: hourly / monthly / hours（製造業, %s）", args.currency)
        rows_h = fetch_sdmx_csv(urls["hourly"])
        rows_m = fetch_sdmx_csv(urls["monthly"])
        rows_w = fetch_sdmx_csv(urls["hours"])
    except DataFetchError as e:
        logging.error("取得失敗: %s", e)
        return 1

    hourly = latest_by_country(rows_h, cur_code)
    monthly = latest_by_country(rows_m, cur_code)
    hours = latest_by_country(rows_w)  # 時間は通貨フィルタ不要
    logging.info("直接時間給=%d国 / 月給=%d国 / 週時間=%d国",
                 len(hourly), len(monthly), len(hours))

    results = derive_hourly(countries, hourly, monthly, hours)
    if not results:
        logging.error("該当データなし（year-from を下げる/国コードを確認）")
        return 1

    ranked = []
    for rank, (cc, d) in enumerate(
            sorted(results.items(), key=lambda x: -x[1]["hourly"])[:args.top_n], 1):
        ranked.append({"rank": rank, "cc": cc, **d})

    # ─── 出力 ───
    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_ilostat_wages_manufacturing_{args.currency.lower()}_top{args.top_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"
    save_csv(ranked, out_csv, currency=args.currency, unit=unit)
    n_direct = sum(1 for d in results.values() if d["source"] == "direct")
    meta = save_metadata(out_meta, currency=args.currency, year_from=args.year_from,
                         top_n=args.top_n, urls=urls, out_csv=out_csv,
                         row_count=len(ranked), n_direct=n_direct,
                         n_derived=len(results) - n_direct, unit=unit)
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(ranked), meta["csv_sha256"][:12])

    print(f"\n== ILO 製造業 時間賃金 Top {args.top_n} ({args.currency}) ==")
    for r in ranked:
        print(f"  {r['rank']:>3}  {r['cc']:<4}  {r['hourly']:>7.2f}{unit}  "
              f"{r['year']}  {r['source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
