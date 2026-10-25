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

# 要素番号（平年値CSVの3列目）。定義は気象庁「アメダス 平年値ファイルの形式」
# https://www.data.jma.go.jp/stats/data/mdrr/normal/2020/doc/format_amedas.pdf （月・年別平年値の要素番号表）
ELEM_TEMP = "0500"   # 気温 月・年平均 0.1℃
ELEM_WIND = "2600"   # 風速 月・年平均 0.1m/s
ELEM_PREC = "4000"   # 降水量 月・年合計 0.1mm
ELEM_SNOW = "6300"   # 積雪差1時間差 月・年合計 1cm（＝降雪量）
# ★旧版は降雪を 1500 で読んでいたが、1500 は「日最低気温＜0.0℃ 月・年間日数（0.1日）」＝冬日の日数（2026-10-26 修正）

# 1行の並び（同PDFの記録様式）: 0 種別(21) / 1 観測所番号 / 2 要素番号 / 3 資料年数 / 4 統計開始年 / 5 統計終了年 /
#   6,7 1月の値・RMK … 28,29 12月の値・RMK / 30,31 年の値・RMK  → 32列
# RMK: 8=正常値、0=統計値なし（同PDF「リマーク」）。それ以外の値は文書に無いので値なしとして数える
N_COLS = 32
RMK_OK = "8"

METRICS = {
    # key: (表示名, 単位, 要素番号, 年の値の求め方)
    "mean_temp": ("年平均気温", "°C", ELEM_TEMP, "annual"),
    "max_temp": ("最暖月平均気温", "°C", ELEM_TEMP, "max_month"),
    "annual_prec": ("年降水量", "mm", ELEM_PREC, "annual"),
    "annual_wind": ("年平均風速", "m/s", ELEM_WIND, "annual"),
    "annual_snow": ("年降雪量", "cm", ELEM_SNOW, "annual"),
}
SCALE = {ELEM_TEMP: 10.0, ELEM_WIND: 10.0, ELEM_PREC: 10.0, ELEM_SNOW: 1.0}
CACHE_VERSION = 2


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


def load_station_table(cache_dir: Path, refresh: bool = False) -> tuple[dict, dict]:
    """amedastable.json から {block_no: {name, lat, lon}}。lat/lon は [度,分]→十進。"""
    cache = cache_dir / "amedastable.json"
    if cache.exists() and not refresh:
        body = cache.read_bytes()
        info = {"from_cache": True, "mtime": datetime.fromtimestamp(
            cache.stat().st_mtime, timezone.utc).astimezone().isoformat()}
    else:
        body = _get(AMEDAS_TABLE_URL, timeout=30).content
        cache.write_bytes(body)
        info = {"from_cache": False,
                "mtime": datetime.now(timezone.utc).astimezone().isoformat()}
    info["sha256"] = hashlib.sha256(body).hexdigest()
    raw = json.loads(body.decode("utf-8"))
    table = {}
    for bn, inf in raw.items():
        lat = inf.get("lat", [0, 0])
        lon = inf.get("lon", [0, 0])
        table[bn] = {
            "name": inf.get("kjName", bn),
            "lat": round(lat[0] + lat[1] / 60.0, 4),
            "lon": round(lon[0] + lon[1] / 60.0, 4),
        }
    return table, info


def _value(row: list[str] | None, how: str, scale: float) -> tuple[float | None, str]:
    """要素の1行から年の値。(値, 理由)。理由は "" か 値なしの理由。"""
    if row is None:
        return None, "要素の行なし"
    if how == "annual":
        if row[31] != RMK_OK:
            return None, f"年のRMK={row[31]}"
        return round(int(row[30]) / scale, 1), ""
    rmks = {row[7 + 2 * i] for i in range(12)}
    if rmks != {RMK_OK}:
        return None, f"月のRMK={''.join(sorted(rmks))}"
    return round(max(int(row[6 + 2 * i]) for i in range(12)) / scale, 1), ""


def parse_normals_zip(zip_bytes: bytes, table: dict) -> tuple[dict, dict]:
    """平年値ZIP をパースして ({block_no: {name, lat, lon, 要素ごとの行}}, 落とした記録)。

    ハマり所: 値とRMKが交互に並ぶ（月の値は cols[6 + i*2]、年の値は cols[30]）。3列目=要素番号。
    落とした局・行は数えて返す（黙って捨てない）。
    """
    records = {}
    skipped = {"csv_total": 0, "not_in_station_table": [], "bad_rows": []}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            skipped["csv_total"] += 1
            bn = name.split("_")[-1].replace(".csv", "")
            if bn not in table:
                skipped["not_in_station_table"].append(bn)
                continue
            elems = {}
            for line in zf.read(name).decode("utf-8").strip().split("\n"):
                cols = [c.strip() for c in line.split(",")]
                if len(cols) != N_COLS or cols[1] != bn:
                    skipped["bad_rows"].append(f"{bn}:{cols[2] if len(cols) > 2 else '?'}")
                    continue
                elems[cols[2]] = cols
            records[bn] = {"name": table[bn]["name"], "lat": table[bn]["lat"],
                           "lon": table[bn]["lon"],
                           "elems": {e: elems.get(e) for e in SCALE}}
    return records, skipped


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="気象庁 AMeDAS 平年値 観測所別テーブル取得")
    ap.add_argument("--metric", default="mean_temp", choices=list(METRICS.keys()),
                    help="降順ソートに使う指標 (default mean_temp)")
    ap.add_argument("--top-n", type=int, default=0,
                    help="上位N (0=値のある全観測所、既定)")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "amedas_normals")
    ap.add_argument("--refresh", action="store_true", help="キャッシュを使わず取り直す")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    label, unit, elem, how = METRICS[args.metric]

    # ─── 取得（観測所表＋平年値ZIP。どちらも生のままキャッシュし、ハッシュを metadata に残す）───
    zip_cache = args.cache_dir / "normal_amedas_monthly.zip"
    try:
        table, table_info = load_station_table(args.cache_dir, refresh=args.refresh)
        if zip_cache.exists() and not args.refresh:
            zip_bytes = zip_cache.read_bytes()
            zip_info = {"from_cache": True, "mtime": datetime.fromtimestamp(
                zip_cache.stat().st_mtime, timezone.utc).astimezone().isoformat()}
        else:
            zip_bytes = _get(NORMALS_ZIP_URL).content
            zip_cache.write_bytes(zip_bytes)
            zip_info = {"from_cache": False,
                        "mtime": datetime.now(timezone.utc).astimezone().isoformat()}
    except DataFetchError as e:
        logging.error("取得失敗: %s", e)
        return 1
    zip_info["sha256"] = hashlib.sha256(zip_bytes).hexdigest()
    records, skipped = parse_normals_zip(zip_bytes, table)
    if skipped["bad_rows"]:  # 記録様式（32列）が変わった＝読み方が合わない
        logging.error("列数の合わない行 %d 件（例 %s）", len(skipped["bad_rows"]),
                      skipped["bad_rows"][:5])
        return 1
    logging.info("ZIP内CSV %d、座標表に無く外した局 %d、読んだ局 %d",
                 skipped["csv_total"], len(skipped["not_in_station_table"]), len(records))

    # ─── 指標の値がある観測所・降順 ───
    rows, no_value = [], {}
    for bn, d in records.items():
        r = {"key": bn, "name": d["name"], "lat": d["lat"], "lon": d["lon"]}
        for m, (_, _, e, h) in METRICS.items():
            r[m], _why = _value(d["elems"][e], h, SCALE[e])
        row = d["elems"][elem]
        v, why = _value(row, how, SCALE[elem])
        if v is None:
            no_value[why] = no_value.get(why, 0) + 1
            continue
        r["years"], r["start"], r["end"] = int(row[3]), row[4], row[5]
        rows.append(r)
    rows.sort(key=lambda r: r[args.metric], reverse=True)
    n_with_value = len(rows)
    if args.top_n > 0:
        rows = rows[:args.top_n]
    if not rows:
        logging.error("指標 %s を持つ観測所がありません", args.metric)
        return 1
    n_short = sum(1 for r in rows if r["years"] != 30)
    scope = (f"{label}の平年値がある{n_with_value}観測所"
             + (f"のうち上位{len(rows)}" if args.top_n > 0 else "すべて")
             + f"（ZIP内{skipped['csv_total']}局のうち座標表にある{len(records)}局が母数。"
             f"うち{n_short}局は資料年数が30年未満で、統計期間が1991-2020年より短い）")

    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_amedas_normals_{args.metric}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    fields = ["Rank", "Area", "Value", "BlockNo", "Lat", "Lon",
              "MeanTemp", "MaxTemp", "AnnualPrec", "AnnualWind", "AnnualSnow", "Unit",
              "NormYears", "NormStart", "NormEnd"]
    with open(out_csv, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["name"], r[args.metric], r["key"], r["lat"], r["lon"],
                        r["mean_temp"], r["max_temp"], r["annual_prec"],
                        r["annual_wind"], r["annual_snow"], unit,
                        r["years"], r["start"], r["end"]])

    meta = {
        "task_name": f"amedas_normals_{args.metric}",
        "source": {"name": "気象庁 AMeDAS 平年値 1991-2020",
                   "urls": {"table": AMEDAS_TABLE_URL, "normals": NORMALS_ZIP_URL},
                   "format_doc": "https://www.data.jma.go.jp/stats/data/mdrr/normal/2020/doc/format_amedas.pdf",
                   "single_source": True},
        "query": {"metric": args.metric, "metric_label": label, "element_code": elem,
                  "top_n": args.top_n},
        "scope": scope,
        "n_csv_in_zip": skipped["csv_total"],
        "skipped_not_in_station_table": skipped["not_in_station_table"],
        "n_stations_read": len(records),
        "n_stations_with_value": n_with_value,
        "no_value_reasons": no_value,
        "n_rows_years_lt_30": n_short,
        "inputs": {"normals_zip": zip_info, "station_table": table_info},
        "units": unit,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "row_count": len(rows),
        "normals_period": "1991-2020（資料年数30年未満の局は NormStart〜NormEnd が短い）",
        "missing_value_treatment": "RMK=8（正常値）以外の値は使わない。理由別の件数は no_value_reasons",
        "notes": ("要素番号 0500=気温/4000=降水量/2600=風速/6300=積雪差1時間差の合計（降雪量）。"
                  "年の値は気象庁が収録した年の値（cols[30]）を使う。最暖月は月の値の最大。"),
    }
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    logging.info("出力: %s (%d観測所, sha256=%s…)",
                 out_csv.name, len(rows), meta["csv_sha256"][:12])

    print(f"\n== AMeDAS 平年値 {label} 降順 ({len(rows)}観測所) ==")
    print(f"   範囲: {scope}")
    for r in rows[:5]:
        print(f"  {r['name']:<8}  {r[args.metric]:>7}{unit}  ({r['key']})")
    print("  …")
    for r in rows[-3:]:
        print(f"  {r['name']:<8}  {r[args.metric]:>7}{unit}  ({r['key']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
