"""fetch.py — UN WUP 2025 都市化度（Degree of Urbanization）国別ランキング取得

UN World Urbanization Prospects 2025 の "Degree of Urbanization" バルク xlsx から、
指定年・カテゴリ（Cities and Towns 等）の国別 % を取得し、上位N国を CSV + metadata.json に保存。

使い方:
    # 2025年 都市人口割合（Cities and Towns）上位20
    python fetch.py --year 2025 --top-n 20 --output-dir ./output

    # 既存キャッシュ xlsx を使う（テスト時・再DL回避）
    python fetch.py --year 2025 --top-n 20 \\
        --cache ./cache/.wup_cache/WUP2025-F02-Degree-of-Urbanization_percPop_by_category.xlsx \\
        --output-dir ./output

このレシピが扱う範囲:
- 単一年 × カテゴリ × 国別「都市化度(%)」ランキング上位N（認証不要・UN公開バルク）

このレシピが扱わない範囲:
- 1か国の時系列推移 → 別レシピ（未作成）
- 絶対人口（千人）モード → --indicator population で対応（F01 ファイル）
- 地域・大陸の集計値 → 本レシピは row[7]==4（国）のみ。集計は別レシピ
"""
from __future__ import annotations  # py3.9 で PEP604 `X | None` 注釈を使うため

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ─── 定数 ───
BASE_URL = "https://population.un.org/wup/assets/Download/Countries%20and%20Aggregates/"
FILE_MAP = {
    "percent": "WUP2025-F02-Degree-of-Urbanization_percPop_by_category.xlsx",
    "population": "WUP2025-F01-Degree-of-Urbanization_Pop_by_category.xlsx",
}
SHEET_MAP = {"urban": "Cities and Towns", "cities": "Cities",
             "towns": "Towns", "rural": "Rural"}
UNIT_MAP = {"percent": "%", "population": "千人"}

# WUP xlsx レイアウト（実データで確認した固定オフセット）
META_COLS = 10          # 0..9 がメタ列、年列は index 10 以降
COL_NAME = 1            # 地域名
COL_ISO3 = 4            # ISO3
COL_TYPE = 7            # 種別コード（4=国）
COUNTRY_TYPE = 4
PROJECTION_FROM = 2025  # これより後を推計として警告する（WUP 2025 の info シートに推計の開始年の記載は無い）
# 固定オフセットが指す見出し（版で列がずれたら止める。2026-10-26 に F01・F02 とも一致を確認）
EXPECTED_HEADER = {COL_NAME: "Location", COL_ISO3: "ISO3_Code", COL_TYPE: "LocType",
                   8: "LocTypeName", META_COLS: "1950"}


class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source = source
        self.url = url
        self.kind = kind
        self.original = original


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_xlsx(url: str, dest: Path, retries: int = 3, timeout: int = 120) -> None:
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as cl:
                r = cl.get(url)
                r.raise_for_status()
                dest.write_bytes(r.content)
            return
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("download retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError(
        source="UN WUP", url=url, kind="DOWNLOAD_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def load_sheet(xlsx_path: Path, sheet_name: str) -> list[tuple]:
    """xlsx を read_only/data_only で開き、指定シートの全行を tuple で返す。"""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise DataFetchError(
            source="UN WUP", url=str(xlsx_path), kind="SHEET_NOT_FOUND",
            message=f"sheet '{sheet_name}' not in {wb.sheetnames}")
    ws = wb[sheet_name]
    return list(ws.iter_rows(values_only=True))


def check_header(header: tuple) -> None:
    """固定オフセットの列が想定の見出しか確かめる（列ずれで type 判定が黙って壊れるのを防ぐ）。"""
    bad = {i: (header[i] if i < len(header) else None, want)
           for i, want in EXPECTED_HEADER.items()
           if i >= len(header) or str(header[i]).strip() != want}
    if bad:
        raise DataFetchError(source="UN WUP", url="", kind="HEADER_MISMATCH",
                             message=f"列の見出しが想定と違う {{index: (実際, 想定)}}: {bad}")


def build_year_columns(header: tuple) -> dict:
    """ヘッダ行から {年(str): 列index} を作る。

    ハマり所: 年列は index 10 以降。ヘッダ値を直接スキャンして列を引く
    （`all_years.index(year)+10` のような連番前提は None 欠落で破綻するため避ける）。
    """
    cols = {}
    for i, h in enumerate(header):
        if i >= META_COLS and h is not None:
            cols[str(h).strip()] = i
    return cols


def rank_countries(rows: list[tuple], year_col: int, top_n: int,
                   min_value: float | None, stats: dict | None = None,
                   percent: bool = False) -> list[dict]:
    """row[7]==4（国・地域）かつ値ありを降順ソートして上位N。集計地域は type で除外。
    stats を渡すと、母集団の件数・値なしで落とした地域・しきい値で落とした件数を書き込む。"""
    countries = []
    n_type4, no_value, below = 0, [], 0
    for r in rows[1:]:
        if len(r) <= year_col:
            continue
        if r[COL_TYPE] != COUNTRY_TYPE:
            continue           # 4 以外は World/地域などの集計 → 除外
        n_type4 += 1
        val = r[year_col]
        try:
            val = float(val)
        except (ValueError, TypeError):
            no_value.append(r[COL_NAME])     # 値なし・非数値は落とすが、名前を残す
            continue
        if percent and not 0 <= val <= 100:
            raise DataFetchError(source="UN WUP", url="", kind="PERCENT_OUT_OF_RANGE",
                                 message=f"{r[COL_NAME]} の値 {val} が 0〜100 の外（ファイル取り違え？）")
        if min_value is not None and val < min_value:
            below += 1
            continue
        countries.append((r[COL_NAME], r[COL_ISO3], val))
    countries.sort(key=lambda x: x[2], reverse=True)
    if stats is not None:
        stats.update(n_type4=n_type4, dropped_no_value=no_value,
                     dropped_below_min=below, n_ranked_pool=len(countries))
    out = []
    for rank, (name, iso3, val) in enumerate(countries[:top_n], 1):
        out.append({"rank": rank, "area": name, "iso3": iso3, "value": round(val, 2)})
    return out


def save_csv(rows: list[dict], out_path: Path, *, category: str,
             indicator: str, year: int, unit: str) -> None:
    import csv
    fields = ["Rank", "Area", "ISO3", "Category", "Indicator", "Year", "Value", "Unit"]
    sheet = SHEET_MAP.get(category, category)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for r in rows:
            w.writerow([r["rank"], r["area"], r["iso3"], sheet,
                        indicator, year, r["value"], unit])


def save_metadata(meta_path: Path, *, year: int, category: str, indicator: str,
                  top_n: int, url: str, out_csv: Path, raw_xlsx: Path,
                  row_count: int, unit: str, extra: dict) -> dict:
    meta = {
        "task_name": f"wup_urbanization_{year}_{category}_top{top_n}",
        "source": {
            "name": "UN World Urbanization Prospects 2025 (Degree of Urbanization)",
            "url": url,
            "single_source": True,
        },
        "query": {
            "year": year, "category": category, "sheet": SHEET_MAP.get(category, category),
            "indicator": indicator, "top_n": top_n, "country_type_code": COUNTRY_TYPE,
        },
        "units": unit,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        **extra,
        "raw_xlsx_sha256": sha256_of(raw_xlsx),
        "is_projection": year > PROJECTION_FROM,
        "notes": (
            "都市化度=DEGURBA。'Cities and Towns' の % は Cities＋Towns and semi-dense areas（非 Rural）の割合で、"
            "従来の urban/rural 定義の都市人口率（WDI SP.URB.TOTL.IN.ZS 等）とは別物。"
            "国行は種別コード LocType==4（country or area）で抽出（World/地域などの集計を除外）。"
            "LocType==4 は非主権地域（Gibraltar・Holy See・香港・マカオ等）を含み、主権国家に絞っていない。"
            f"{year} > {PROJECTION_FROM} の年は推計値。"
        ),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return meta


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="UN WUP 2025 都市化度 国別ランキング取得")
    ap.add_argument("--year", type=int, default=2025, help="対象年 (default: 2025)")
    ap.add_argument("--category", default="urban",
                    choices=list(SHEET_MAP.keys()),
                    help="urban=Cities and Towns / cities / towns / rural")
    ap.add_argument("--indicator", default="percent", choices=list(FILE_MAP.keys()),
                    help="percent(パーセント) or population(千人)")
    ap.add_argument("--top-n", type=int, default=20, help="上位N (default: 20)")
    ap.add_argument("--min-value", "--min-percent", dest="min_percent", type=float, default=None,
                    help="この値未満を除外（任意）。--indicator の単位で比べる（percent は %%、population は千人）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "wup")
    ap.add_argument("--cache", type=Path, default=None,
                    help="既存 xlsx を直接指定（DL省略）")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    filename = FILE_MAP[args.indicator]
    url = BASE_URL + filename
    sheet_name = SHEET_MAP.get(args.category, "Cities and Towns")
    unit = UNIT_MAP[args.indicator]

    # ─── キャッシュ・ダウンロード ───
    if args.cache:
        xlsx_path = args.cache
        if not xlsx_path.exists():
            logging.error("指定 cache が存在しません: %s", xlsx_path)
            return 1
        logging.info("既存 xlsx 使用: %s", xlsx_path)
    else:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        xlsx_path = args.cache_dir / filename
        if not xlsx_path.exists():
            logging.info("xlsx ダウンロード: %s", url)
            try:
                download_xlsx(url, xlsx_path)
            except DataFetchError as e:
                logging.error("ダウンロード失敗: %s", e)
                return 1
            logging.info("保存完了: %s (%d KB)", xlsx_path,
                         xlsx_path.stat().st_size // 1024)

    # ─── ロード・年列特定・ランキング ───
    rows = load_sheet(xlsx_path, sheet_name)
    if not rows:
        logging.error("シートが空です: %s", sheet_name)
        return 1
    try:
        check_header(rows[0])
    except DataFetchError as e:
        logging.error("%s", e)
        return 1
    year_cols = build_year_columns(rows[0])
    ykey = str(args.year)
    if ykey not in year_cols:
        logging.error("年 %s が見つかりません。利用可能: %s",
                      ykey, ", ".join(sorted(year_cols)))
        return 1
    if args.year > PROJECTION_FROM:
        logging.warning("%d は推計値です（観測でなく projection）", args.year)

    stats: dict = {}
    try:
        ranked = rank_countries(rows, year_cols[ykey], args.top_n, args.min_percent,
                                stats=stats, percent=(args.indicator == "percent"))
    except DataFetchError as e:
        logging.error("%s", e)
        return 1
    logging.info("母集団 LocType==4: %d（値なしで除外 %d・しきい値で除外 %d）",
                 stats["n_type4"], len(stats["dropped_no_value"]), stats["dropped_below_min"])
    if stats["dropped_no_value"]:
        logging.warning("値なしで除外: %s", stats["dropped_no_value"])
    if not ranked:
        logging.error("該当データなし")
        return 1

    # ─── 出力 ───
    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_wup_urbanization_{args.year}_{args.category}_top{args.top_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"
    save_csv(ranked, out_csv, category=args.category, indicator=args.indicator,
             year=args.year, unit=unit)
    meta = save_metadata(out_meta, year=args.year, category=args.category,
                         indicator=args.indicator, top_n=args.top_n, url=url,
                         out_csv=out_csv, raw_xlsx=xlsx_path,
                         row_count=len(ranked), unit=unit,
                         extra={
                             "scope": (f"WUP 2025 の LocType==4（country or area）{stats['n_ranked_pool']}件の中での順位"
                                       "（非主権地域を含む。主権国家だけの順位ではない）"),
                             "n_candidates": stats["n_ranked_pool"],
                             "dropped_no_value": stats["dropped_no_value"],
                             "dropped_below_min": stats["dropped_below_min"],
                             "from_cache": bool(args.cache) or None,
                         })
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(ranked), meta["csv_sha256"][:12])

    print(f"\n== UN WUP 2025 都市化度 Top {args.top_n} "
          f"({args.year}, {sheet_name}, {args.indicator}) ==")
    for r in ranked:
        print(f"  {r['rank']:>3}  {str(r['area']):<32}  "
              f"{r['value']:>7.1f}{unit}  {r['iso3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
