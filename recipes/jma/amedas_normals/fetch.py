"""fetch.py — 気象庁 AMeDAS 平年値(1991-2020) 観測所別テーブル取得

気象庁の AMeDAS 月別平年値ZIP と観測所座標(amedastable.json)から、
観測所ごとの年平均気温・年降水量・年平均風速・年降雪量を取得し、
指定指標で降順に並べた CSV + metadata.json を出力する（地図用の間引きはしない＝全観測所）。

使い方:
    # 年平均気温で降順（既定）
    python fetch.py --output-dir ./output
    # 年降水量で降順
    python fetch.py --metric annual_prec --output-dir ./output

出力:
    output/YYYYMMDD_amedas_normals_<metric>.csv  … 観測所別平年値（指標降順）
    output/..._metadata.json

このレシピが扱う範囲:
- AMeDAS 観測所別の 1991-2020 平年値（年平均気温/年降水量/年平均風速/年降雪量）

このレシピが扱わない範囲:
- 地図描画・空間間引き → 各プロジェクト側（本レシピは素データ供給）
- 月別の細目 → 本レシピは年値に集約（月別が要るなら拡張）
- 観測所の標高・詳細メタ → amedastable の一部のみ使用
"""
import argparse
import csv
import hashlib
import io
import json
import logging
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

AMEDAS_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
NORMALS_ZIP_URL = ("https://www.data.jma.go.jp/stats/data/mdrr/normal/"
                   "2020/data/normal_amedas_monthly.zip")
UA = {"User-Agent": "Mozilla/5.0"}

# 要素コード（平年値CSVの3列目）。値は (0.1単位)。
ELEM_TEMP = "0500"   # 平均気温 0.1℃
ELEM_WIND = "2600"   # 平均風速 0.1m/s
ELEM_PREC = "4000"   # 降水量合計 0.1mm
ELEM_SNOW = "1500"   # 降雪量合計 cm

METRICS = {
    "mean_temp": ("年平均気温", "°C"),
    "max_temp": ("最暖月平均気温", "°C"),
    "annual_prec": ("年降水量", "mm"),
    "annual_wind": ("年平均風速", "m/s"),
    "annual_snow": ("年降雪量", "cm"),
}


class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source, self.url, self.kind, self.original = source, url, kind, original


def _get(url: str, retries: int = 3, timeout: int = 180) -> httpx.Response:
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as cl:
                r = cl.get(url, headers=UA)
                r.raise_for_status()
            return r
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError(source="JMA", url=url, kind="FETCH_FAIL",
                         message=f"failed after {retries} attempts", original=last_err)


def load_station_table(cache_dir: Path) -> dict:
    """amedastable.json から {block_no: {name, lat, lon}}。lat/lon は [度,分]→十進。"""
    cache = cache_dir / "amedastable.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
    else:
        raw = _get(AMEDAS_TABLE_URL, timeout=30).json()
        cache.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    table = {}
    for bn, info in raw.items():
        lat = info.get("lat", [0, 0])
        lon = info.get("lon", [0, 0])
        table[bn] = {
            "name": info.get("kjName", bn),
            "lat": round(lat[0] + lat[1] / 60.0, 4),
            "lon": round(lon[0] + lon[1] / 60.0, 4),
        }
    return table


def parse_normals_zip(zip_bytes: bytes, table: dict) -> dict:
    """平年値ZIP をパースして {block_no: {各指標}}。

    ハマり所: 月別値は 6列目以降の「1列おき」(cols[6 + i*2])。3列目=要素コード。
    """
    records = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            bn = name.split("_")[-1].replace(".csv", "")
            if bn not in table:
                continue
            elems = {}
            for line in zf.read(name).decode("utf-8").strip().split("\n"):
                cols = [c.strip() for c in line.split(",")]
                if len(cols) < 32:
                    continue
                try:
                    elems[cols[2]] = [int(cols[6 + i * 2]) for i in range(12)]
                except (ValueError, IndexError):
                    continue

            def monthly(code):
                m = elems.get(code)
                return m if m and any(v != 0 for v in m) else None

            m_t, m_w, m_p, m_s = (monthly(ELEM_TEMP), monthly(ELEM_WIND),
                                  monthly(ELEM_PREC), monthly(ELEM_SNOW))
            rec = {
                "name": table[bn]["name"],
                "lat": table[bn]["lat"], "lon": table[bn]["lon"],
                "mean_temp": round(sum(m_t) / 12 / 10.0, 1) if m_t else None,
                "max_temp": round(max(m_t) / 10.0, 1) if m_t else None,
                "annual_prec": round(sum(m_p) / 10.0, 1) if m_p else None,
                "annual_wind": round(sum(m_w) / 12 / 10.0, 1) if m_w else None,
                # 降雪は None=未観測 / 0=無雪 を区別（elems に 1500 が在るかで判定）
                "annual_snow": (sum(elems[ELEM_SNOW]) if ELEM_SNOW in elems else None),
            }
            records[bn] = rec
    return records


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="気象庁 AMeDAS 平年値 観測所別テーブル取得")
    ap.add_argument("--metric", default="mean_temp", choices=list(METRICS.keys()),
                    help="降順ソートに使う指標 (default mean_temp)")
    ap.add_argument("--top-n", type=int, default=0,
                    help="上位N (0=全観測所、既定)")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "amedas_normals")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    label, unit = METRICS[args.metric]

    # ─── 取得（観測所表＋平年値、いずれもキャッシュ）───
    records_cache = args.cache_dir / "station_records.json"
    if records_cache.exists():
        logging.info("キャッシュ使用: %s", records_cache)
        records = json.loads(records_cache.read_text(encoding="utf-8"))
    else:
        try:
            table = load_station_table(args.cache_dir)
            zip_bytes = _get(NORMALS_ZIP_URL).content
        except DataFetchError as e:
            logging.error("取得失敗: %s", e)
            return 1
        records = parse_normals_zip(zip_bytes, table)
        records_cache.write_text(json.dumps(records, ensure_ascii=False),
                                 encoding="utf-8")
    logging.info("観測所数(全要素読込): %d", len(records))

    # ─── 指標が存在する観測所のみ・降順 ───
    rows = [{"key": bn, **d} for bn, d in records.items()
            if d.get(args.metric) is not None]
    rows.sort(key=lambda r: r[args.metric], reverse=True)
    if args.top_n > 0:
        rows = rows[:args.top_n]
    if not rows:
        logging.error("指標 %s を持つ観測所がありません", args.metric)
        return 1

    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_amedas_normals_{args.metric}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    fields = ["Rank", "Area", "Value", "BlockNo", "Lat", "Lon",
              "MeanTemp", "MaxTemp", "AnnualPrec", "AnnualWind", "AnnualSnow", "Unit"]
    with open(out_csv, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["name"], r[args.metric], r["key"], r["lat"], r["lon"],
                        r["mean_temp"], r["max_temp"], r["annual_prec"],
                        r["annual_wind"], r["annual_snow"], unit])

    meta = {
        "task_name": f"amedas_normals_{args.metric}",
        "source": {"name": "気象庁 AMeDAS 平年値 1991-2020",
                   "urls": {"table": AMEDAS_TABLE_URL, "normals": NORMALS_ZIP_URL},
                   "single_source": True},
        "query": {"metric": args.metric, "metric_label": label, "top_n": args.top_n},
        "units": unit,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "row_count": len(rows),
        "normals_period": "1991-2020",
        "notes": ("要素コード 0500=平均気温/4000=降水量/2600=風速/1500=降雪。"
                  "月別値は CSV 6列目以降の1列おき。年平均気温=12か月平均。"
                  "降雪は None=未観測, 0=無雪 を区別。"),
    }
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    logging.info("出力: %s (%d観測所, sha256=%s…)",
                 out_csv.name, len(rows), meta["csv_sha256"][:12])

    print(f"\n== AMeDAS 平年値 {label} 降順 ({len(rows)}観測所) ==")
    for r in rows[:5]:
        print(f"  {r['name']:<8}  {r[args.metric]:>7}{unit}  ({r['key']})")
    print("  …")
    for r in rows[-3:]:
        print(f"  {r['name']:<8}  {r[args.metric]:>7}{unit}  ({r['key']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
