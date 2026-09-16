#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — OECD Data Explorer（SDMX）から任意のデータフローを取る。

  ★データのURLに `latest` は書けない（400）。バージョンは空でよい。
  ★次元数はデータフローごとに違う。--dims で確認してからキーのドット数を合わせる。
  詳細は recipe.md。

使い方:
    python fetch.py --list tax
    python fetch.py --dims OECD.CTP.TPS DSD_REV_COMP_OECD@DF_RSOECD
    python fetch.py --agency OECD.CTP.TPS --flow DSD_REV_COMP_OECD@DF_RSOECD \
           --key "JPN+USA+DNK+FRA......." --start 2018 --filter UNIT_MEASURE=PT_B1GQ,SECTOR=S13
"""
import argparse, csv, hashlib, io, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

ROOT = "https://sdmx.oecd.org/public/rest"
UA = {"User-Agent": "Mozilla/5.0"}
CSV_ACCEPT = {**UA, "Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}
XML_ACCEPT = {**UA, "Accept": "application/xml"}


def dataflows():
    r = httpx.get(f"{ROOT}/dataflow/all/all/latest", headers=XML_ACCEPT, timeout=300,
                  follow_redirects=True)
    r.raise_for_status()
    return re.findall(r'<(?:str|structure):Dataflow[^>]*id="([^"]+)"[^>]*agencyID="([^"]+)"', r.text)


def dims(agency, flow):
    r = httpx.get(f"{ROOT}/dataflow/{agency}/{flow}/latest", params={"references": "all"},
                  headers=XML_ACCEPT, timeout=300, follow_redirects=True)
    r.raise_for_status()
    d = re.findall(r'id="([A-Z0-9_]+)"\s+position="(\d+)"', r.text)
    return [x[0] for x in sorted(d, key=lambda x: int(x[1]))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default="")
    ap.add_argument("--dims", nargs=2, metavar=("AGENCY", "FLOW"))
    ap.add_argument("--agency", default=""); ap.add_argument("--flow", default="")
    ap.add_argument("--version", default="", help="空でよい。latest は400になる")
    ap.add_argument("--key", default="", help="次元をドットで区切る。TIME_PERIODは含めない")
    ap.add_argument("--start", type=int, default=2015)
    ap.add_argument("--filter", default="", help="列=値 のカンマ区切りで後フィルタ")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    a = ap.parse_args()

    if a.list:
        fl = dataflows()
        hit = [(ag, f) for f, ag in fl if a.list.lower() in f.lower()]
        print(f"「{a.list}」に一致 {len(hit)}件")
        for ag, f in hit[:40]: print(f"   {ag:<18}{f}")
        return 0
    if a.dims:
        d = dims(*a.dims)
        print(f"次元 {len(d)}個: {d}")
        print(f"キーの書き方（TIME_PERIODを除く{len(d)-1 if d[-1]=='TIME_PERIOD' else len(d)}段）: "
              + ".".join(["" for _ in range(len(d) - (1 if d[-1] == 'TIME_PERIOD' else 0))]))
        return 0
    if not (a.agency and a.flow and a.key):
        print("--agency --flow --key が要る（--dims で次元を確認してから）", file=sys.stderr); return 2

    # ★latest は 400。空か具体的な版で
    ver = f",{a.version}" if a.version else ""     # ★latest は 400 になる
    url = f"{ROOT}/data/{a.agency},{a.flow}{ver}/{a.key}"
    r = httpx.get(url, params={"startPeriod": a.start}, headers=CSV_ACCEPT, timeout=300,
                  follow_redirects=True)
    if r.status_code == 400 and "version" in r.text.lower():
        raise SystemExit("400: データのURLに latest は書けない。--version を空か 1.0 に / "
                         + r.text[:100])
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if not rows:
        raise SystemExit("0件。キーのドット数（--dims で確認）とコードを疑う")
    for cond in [c for c in a.filter.split(",") if "=" in c]:
        k, v = cond.split("=", 1)
        rows = [x for x in rows if x.get(k) == v]
    rows = [x for x in rows if x.get("OBS_VALUE")]

    a.output_dir.mkdir(parents=True, exist_ok=True)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    stem = re.sub(r"[^A-Za-z0-9]+", "_", a.flow).strip("_").lower()
    p = a.output_dir / f"{today}_oecd_{stem}.csv"
    with p.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    yrs = sorted({int(x["TIME_PERIOD"]) for x in rows})
    (a.output_dir / f"{today}_oecd_{stem}_metadata.json").write_text(
        json.dumps({"source": "OECD Data Explorer (SDMX)", "url": url,
                    "agency": a.agency, "flow": a.flow, "version": a.version, "key": a.key,
                    "post_filter": a.filter, "rows": len(rows), "years": [yrs[0], yrs[-1]],
                    "areas": sorted({x.get("REF_AREA", "") for x in rows}),
                    "csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(JST).isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {p.name}  rows={len(rows)}  年 {yrs[0]}〜{yrs[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
