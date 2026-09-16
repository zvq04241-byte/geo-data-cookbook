"""fetch.py — 気象庁 主要都市 年降雪量／最深積雪 ランキング取得（etrn スクレイプ）

気象庁 etrn(annually_s.php) の各都市ページをスクレイプし、指定した寒候年の
年合計降雪量（または最深積雪）で都市をランキングして CSV + metadata.json に出力する。

使い方:
    # 2024寒候年(2023年8月〜2024年7月)の年降雪量ランキング 上位15
    python fetch.py --year 2024 --top-n 15 --output-dir ./output

    # 最深積雪でランキング
    python fetch.py --year 2024 --metric maxsnow --output-dir ./output

このレシピが扱う範囲:
- 主要都市（既定20都市・雪国中心）× 単一寒候年 × 降雪量/最深積雪 ランキング（認証不要・HTMLスクレイプ）

このレシピが扱わない範囲:
- 1都市の長期時系列 → 別レシピ（未作成）
- AMeDAS 全観測点 → 別レシピ（observation point が桁違いに多い）
- 平年値 → JMA AMeDAS normals 系の別レシピ
"""
from __future__ import annotations  # py3.9 で PEP604 `X | None` 注釈を使うため

import argparse
import csv
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ETRN_URL = "https://www.data.jma.go.jp/stats/etrn/view/annually_s.php"

# 都市キー -> (block_no/WMO, prec_no, 日本語表示名)。雪国中心＋対照の大都市。
# block_no/prec_no は 既存の対応表由来。表示名を付与。
CITY_TABLE: dict[str, tuple[str, str, str]] = {
    "sapporo":   ("47412", "14", "札幌"),
    "asahikawa": ("47407", "12", "旭川"),
    "wakkanai":  ("47401", "11", "稚内"),
    "abashiri":  ("47409", "17", "網走"),
    "obihiro":   ("47417", "20", "帯広"),
    "kushiro":   ("47418", "19", "釧路"),
    "hakodate":  ("47430", "23", "函館"),
    "aomori":    ("47575", "31", "青森"),
    "akita":     ("47590", "34", "秋田"),
    "morioka":   ("47584", "33", "盛岡"),
    "yamagata":  ("47588", "35", "山形"),
    "fukushima": ("47595", "36", "福島"),
    "sendai":    ("47590", "34", "仙台"),
    "niigata":   ("47604", "54", "新潟"),
    "toyama":    ("47607", "55", "富山"),
    "kanazawa":  ("47605", "56", "金沢"),
    "fukui":     ("47616", "57", "福井"),
    "nagano":    ("47610", "48", "長野"),
    "tokyo":     ("47662", "44", "東京"),
    "osaka":     ("47772", "62", "大阪"),
}
# 仙台/青森は 対応表で block 重複の疑いがあったため etrn の正規値で上書き
CITY_TABLE["aomori"] = ("47575", "31", "青森")
CITY_TABLE["sendai"] = ("47590", "34", "仙台")

DEFAULT_CITIES = list(CITY_TABLE.keys())
MISSING_TOKENS = {"--", "×", "", "///", ")", "]"}
METRIC_LABEL = {"snowfall": "年降雪量合計", "maxsnow": "最深積雪"}


class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source, self.url, self.kind, self.original = source, url, kind, original


def _clean_cell(raw: str) -> str:
    txt = re.sub(r"<[^>]+>", "", raw).strip().rstrip(" ]")
    return txt.replace(",", "").strip()


def _to_float(txt: str) -> float | None:
    t = txt.replace("///", "").strip()
    if not t or t in MISSING_TOKENS:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def find_col(headers: list[str], keywords: list[str]) -> int | None:
    """<th> ヘッダ群からキーワードを全て含む列の index を返す（動的列検出）。"""
    for i, h in enumerate(headers):
        if all(k in h for k in keywords):
            return i
    return None


def parse_city_page(html: str) -> dict:
    """annually_s.php の HTML から {year: {snowfall, maxsnow}} を抽出。

    ハマり所: 列位置は地点で揺れるため <th> を動的検出する。
    検出失敗時のみ固定 index(降雪量合計=21, 最深積雪=22)にフォールバック。
    """
    th_blocks = re.findall(r"<th[^>]*>(.*?)</th>", html, re.DOTALL | re.IGNORECASE)
    headers = [re.sub(r"<[^>]+>", "", h).replace("　", " ").strip() for h in th_blocks]
    col_snow = find_col(headers, ["降雪量", "合計"])
    col_maxsnow = find_col(headers, ["最深積雪"])
    if col_snow is None:
        col_snow = 21
    if col_maxsnow is None:
        col_maxsnow = 22

    out: dict[int, dict] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
        cells = [_clean_cell(c) for c in tds]
        if cells and re.match(r"^\d{4}$", cells[0]):
            yr = int(cells[0])
            snow = _to_float(cells[col_snow]) if col_snow < len(cells) else None
            mx = _to_float(cells[col_maxsnow]) if col_maxsnow < len(cells) else None
            out[yr] = {"snowfall": snow, "maxsnow": mx}
    return out


def fetch_city(key: str, cache_dir: Path, retries: int = 3) -> dict:
    """1都市分を取得（キャッシュ優先）。{year: {snowfall, maxsnow}} を返す。"""
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        return {int(k): v for k, v in json.loads(
            cache_path.read_text(encoding="utf-8")).items()}
    block_no, prec_no, _name = CITY_TABLE[key]
    url = f"{ETRN_URL}?prec_no={prec_no}&block_no={block_no}"
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as cl:
                r = cl.get(url, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
            parsed = parse_city_page(r.text)
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(parsed, ensure_ascii=False),
                                  encoding="utf-8", newline="\n")
            return parsed
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("%s retry %d/%d: %s", key, i + 1, retries, e)
    raise DataFetchError(source="JMA etrn", url=url, kind="FETCH_FAIL",
                         message=f"{key} failed after {retries} attempts",
                         original=last_err)


def save_csv(ranked: list[dict], out_path: Path, *, metric: str, year: int) -> None:
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Area", "CityKey", "Value", "Year", "Metric", "Unit"])
        for r in ranked:
            w.writerow([r["rank"], r["name"], r["key"], r["value"], year,
                        METRIC_LABEL[metric], "cm"])


def save_metadata(meta_path: Path, *, year: int, metric: str, top_n: int,
                  out_csv: Path, row_count: int, n_cities: int) -> dict:
    import hashlib
    meta = {
        "task_name": f"jma_snowfall_{metric}_{year}_top{top_n}",
        "source": {"name": "気象庁 etrn (annually_s.php)", "url": ETRN_URL,
                   "single_source": True},
        "query": {"year_kansetsu": year, "metric": metric, "top_n": top_n,
                  "cities_queried": n_cities},
        "units": "cm",
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "row_count": row_count,
        "notes": ("降雪量は寒候年（前年8月〜当年7月）集計。年は寒候年。"
                  "亜熱帯・温暖地点は降雪観測が無く除外される。値の単位は cm。"),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return meta


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="気象庁 主要都市 降雪量ランキング取得")
    ap.add_argument("--year", type=int, default=2024,
                    help="寒候年（前年8月〜当年7月）。default 2024")
    ap.add_argument("--metric", default="snowfall", choices=["snowfall", "maxsnow"],
                    help="snowfall=年降雪量合計 / maxsnow=最深積雪")
    ap.add_argument("--top-n", type=int, default=15, help="上位N (default 15)")
    ap.add_argument("--cities", default=None,
                    help="都市キーをカンマ区切り（省略時は既定20都市）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "jma_snow")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="都市間の待機秒（礼儀。default 0）")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    keys = ([c.strip().lower() for c in args.cities.split(",")]
            if args.cities else DEFAULT_CITIES)
    keys = [k for k in keys if k in CITY_TABLE]
    if not keys:
        logging.error("有効な都市キーがありません。対応: %s",
                      ", ".join(CITY_TABLE))
        return 1

    rows = []
    for key in keys:
        try:
            data = fetch_city(key, args.cache_dir)
        except DataFetchError as e:
            logging.warning("取得スキップ %s: %s", key, e)
            continue
        rec = data.get(args.year)
        if not rec:
            continue
        val = rec.get(args.metric)
        if val is None:
            continue  # その年に降雪観測なし／欠測の都市は除外
        rows.append({"key": key, "name": CITY_TABLE[key][2], "value": val})
        if args.sleep:
            time.sleep(args.sleep)

    if not rows:
        logging.error("%d 寒候年のデータが取得できませんでした", args.year)
        return 1

    rows.sort(key=lambda x: x["value"], reverse=True)
    ranked = [{**r, "rank": i} for i, r in enumerate(rows[:args.top_n], 1)]

    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_jma_snowfall_{args.metric}_{args.year}_top{args.top_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"
    save_csv(ranked, out_csv, metric=args.metric, year=args.year)
    meta = save_metadata(out_meta, year=args.year, metric=args.metric,
                         top_n=args.top_n, out_csv=out_csv,
                         row_count=len(ranked), n_cities=len(keys))
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(ranked), meta["csv_sha256"][:12])

    print(f"\n== 気象庁 {METRIC_LABEL[args.metric]} ランキング "
          f"{args.year}寒候年 Top {len(ranked)} ==")
    for r in ranked:
        print(f"  {r['rank']:>3}  {r['name']:<6}  {r['value']:>7.0f}cm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
