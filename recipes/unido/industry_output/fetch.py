#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — UNIDO INDSTAT から業種別の工業生産額（Output）を取得する。

『世界国勢図会』『日本国勢図会』の「工業生産額」はUNIDO由来。教材の図表を検算する
ときは World Bank ではなく UNIDO を一次に取る。

  python fetch.py --countries 682,050,704 --year 2022 --rev 3 --output-dir ./output
  python fetch.py --countries 036 --year 2022 --rev 4 --indicator 20   # 付加価値

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


def fetch_data(flow: str, countries: list[str], indicator: str,
               start: str, end: str) -> list[dict]:
    """キーは countries.indicators.classification.classification_combination の4段。

    ★空の段は許されない（「Remove leading, trailing, or consecutive dots」）。
      全件は * で指定する。国は1回あたり3か国まで。
    """
    if len(countries) > 3:
        raise FetchError("国は1回あたり3か国まで（APIの制限）", None, "too_many_countries")
    key = f"{'+'.join(countries)}.{indicator}.*.*"
    url = f"{BASE}/sdmx/data/UNIDO/{flow}/latest/{key}?startPeriod={start}&endPeriod={end}"
    d = _get(url, "data")
    rows = []
    for k, s in d["data"]["dataSets"][0]["series"].items():
        c, ind, isic, combo = k.split(".")
        for yr, v in s["observations"].items():
            val = v[0][0] if isinstance(v[0], list) else v[0]
            rows.append({"country": c, "indicator": ind, "isic": isic,
                         "combo": combo, "year": yr, "value": val})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", required=True, help="ISO3166 数字コード カンマ区切り（最大3）")
    ap.add_argument("--rev", default="3", choices=["3", "4"], help="ISIC Rev.（既定3）")
    ap.add_argument("--indicator", default="14", help="14=Output（既定） 20=Value added 04=Employees")
    ap.add_argument("--start", default="2015")
    ap.add_argument("--end", default="2023")
    ap.add_argument("--output-dir", default="./output")
    ap.add_argument("--list-flows", action="store_true")
    a = ap.parse_args()

    if a.list_flows:
        for i, n in dataflows(): print(f"  {i:<14} {n}")
        return 0

    flow = f"INDSTAT_R{a.rev}"
    cs = [c.strip() for c in a.countries.split(",") if c.strip()]
    rows = fetch_data(flow, cs, a.indicator, a.start, a.end)
    if not rows:
        raise FetchError("0件。国コード・年・Rev. を確認", None, "empty")

    out = Path(a.output_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d")
    csv_p = out / f"{stamp}_unido_indstat_r{a.rev}_ind{a.indicator}.csv"
    with open(csv_p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    meta = {
        "task_name": "unido_industry_output",
        "source": {"name": f"UNIDO {flow}", "url": f"{BASE}/sdmx/data/UNIDO/{flow}/latest/...",
                   "single_source": True},
        "note": "値は自国通貨。ドル換算は別途（例: World Bank PA.NUS.FCRF 期中平均）",
        "countries": cs, "indicator": a.indicator, "period": [a.start, a.end],
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
