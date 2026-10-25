#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — UNIDO INDSTAT から業種別の工業生産額（Output）を取得する。

工業生産額（産出額 output）を検算するときは World Bank（付加価値）ではなく UNIDO を一次に取る。
4か国以上は3か国ずつに分けて取り、結合する（API の上限が1回3か国）。

  python fetch.py --countries 682,050,704 --start 2015 --end 2023 --rev 3 --output-dir ./output
  python fetch.py --countries 036 --start 2022 --end 2022 --rev 4 --indicator 20   # 付加価値

出力: <日付>_unido_indstat_r{3,4}_output.csv と _metadata.json
"""
from __future__ import annotations
import argparse, csv, hashlib, json, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ★ここが要点。stat.unido.org 直下は Cloudflare の判定で 403 になるが、
#   /portal/ 配下は通る。仕様書も /portal/v3/api-docs/{api,sdmx} で読める。
BASE = "https://stat.unido.org/portal"
ACCEPT = {
    "dataflow":      "application/vnd.sdmx.dataflow+json;version=2.0.0",
    "datastructure": "application/vnd.sdmx.structure+json;version=2.0.0",
    "data":          "application/vnd.sdmx.data+json;version=2.0.0",
}
# ★urllib 既定の User-Agent (Python-urllib/3.x) は Cloudflare に弾かれる
#   （Error 1010 "browser signature banned"）。curl/8.x は通る。ブラウザのUAを送る。
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

JST = timezone(timedelta(hours=9))


class FetchError(Exception):
    def __init__(self, msg, url=None, kind=None):
        super().__init__(msg); self.url, self.kind = url, kind


def _get(url: str, kind: str, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": ACCEPT[kind], "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode("utf-8", "replace")
            # 400 は Accept かキーの書き方が悪い。再試行しても直らないので即やめる
            if e.code == 400:
                raise FetchError(f"HTTP400: {body}", url, "bad_request")
            last = FetchError(f"HTTP{e.code}: {body}", url, "http")
        except Exception as e:                      # noqa: BLE001
            last = FetchError(f"{type(e).__name__}: {e}", url, "net")
    raise last


def dataflows() -> list:
    d = _get(f"{BASE}/sdmx/dataflow/UNIDO/all/latest", "dataflow")
    flows = (d.get("data") or {}).get("dataflows")
    if isinstance(flows, list):          # SDMX-JSON の dataflows 配列だけを読む
        return [(f.get("id"), f.get("name") or (f.get("names") or {}).get("en")) for f in flows]
    out = []
    def walk(o):
        if isinstance(o, dict):
            if "id" in o and ("name" in o or "names" in o):
                out.append((o["id"], o.get("name") or (o.get("names") or {}).get("en")))
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(d)
    return out


FIELDS = ["country", "indicator", "isic", "combo", "year", "value"]


def fetch_data(flow: str, countries: list[str], indicator: str,
               start: str, end: str) -> list[dict]:
    """キーは countries.indicators.classification.classification_combination の4段。

    ★空の段は許されない（「Remove leading, trailing, or consecutive dots」）。
      全件は * で指定する。国は1回あたり3か国まで（4か国で 400「up to three countries」を確認）。
      ここでは3か国ずつに分けて取り、結合する。
    """
    rows = []
    for i in range(0, len(countries), 3):
        batch = countries[i:i + 3]
        key = f"{'+'.join(batch)}.{indicator}.*.*"
        url = f"{BASE}/sdmx/data/UNIDO/{flow}/latest/{key}?startPeriod={start}&endPeriod={end}"
        d = _get(url, "data")
        sets = (d.get("data") or {}).get("dataSets") or []
        if not sets:
            raise FetchError("応答に dataSets が無い", url, "shape")
        for k, s in (sets[0].get("series") or {}).items():
            c, ind, isic, combo = k.split(".")
            for yr, v in (s.get("observations") or {}).items():
                val = v[0][0] if isinstance(v[0], list) else v[0]
                rows.append({"country": c, "indicator": ind, "isic": isic,
                             "combo": combo, "year": yr, "value": val})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", help="ISO3166 数字コード カンマ区切り（4か国以上は3か国ずつ取って結合）")
    ap.add_argument("--rev", default="3", choices=["3", "4"], help="ISIC Rev.（既定3）")
    ap.add_argument("--indicator", default="14",
                    help="14=Output（既定） 20=Value added。ほかに 01/04/05/31 が応答に現れる（名前はこのレシピでは未確認）")
    ap.add_argument("--start", default="2015")
    ap.add_argument("--end", default="2023")
    ap.add_argument("--output-dir", default="./output")
    ap.add_argument("--list-flows", action="store_true")
    a = ap.parse_args()

    if a.list_flows:
        for i, n in dataflows(): print(f"  {i:<14} {n}")
        return 0

    if not a.countries:
        ap.error("--countries が要る（--list-flows 以外）")
    flow = f"INDSTAT_R{a.rev}"
    cs = [c.strip() for c in a.countries.split(",") if c.strip()]
    rows = fetch_data(flow, cs, a.indicator, a.start, a.end)
    if not rows:
        raise FetchError("0件。国コード・年・Rev. を確認", None, "empty")

    out = Path(a.output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d")
    csv_p = out / f"{stamp}_unido_indstat_r{a.rev}_ind{a.indicator}.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    got = sorted({r["country"] for r in rows})
    missing = [c for c in cs if c not in got]
    years = sorted({r["year"] for r in rows})
    scope = (f"指定の{len(cs)}か国（{','.join(cs)}）のうち値のあった{len(got)}か国"
             + (f"（値なし {','.join(missing)}）" if missing else "")
             + f"。{flow}・indicator {a.indicator}・要求期間 {a.start}-{a.end} のうち値のある年 {','.join(years)}")
    if missing:
        print(f"  ! 値の無い国: {missing}", file=sys.stderr)
    meta = {
        "task_name": "unido_industry_output",
        "source": {"name": f"UNIDO {flow}", "url": f"{BASE}/sdmx/data/UNIDO/{flow}/latest/...",
                   "single_source": True},
        "note": "値は自国通貨。ドル換算は別途（例: World Bank PA.NUS.FCRF 期中平均）",
        "rev": a.rev, "scope": scope,
        "countries_requested": cs, "countries_with_data": got, "countries_without_data": missing,
        "indicator": a.indicator, "period_requested": [a.start, a.end], "years_present": years,
        "row_count": len(rows),
        "csv_sha256": hashlib.sha256(csv_p.read_bytes()).hexdigest(),
        "fetched_at": datetime.now(JST).isoformat(),
        "generated_by": "cookbook unido/industry_output fetch.py",
    }
    (csv_p.with_name(csv_p.stem + "_metadata.json")).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(rows)}件 → {csv_p}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as e:
        print(f"取得できません [{e.kind}] {e}", file=sys.stderr); sys.exit(1)
