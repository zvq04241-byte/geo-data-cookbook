"""fetch.py — FAOSTAT 作物生産量 国別ランキング取得

FAOSTAT Production_Crops_Livestock データセットから、指定作物の生産量で
世界上位N国を抽出してCSV+metadata.jsonに保存する。

使い方:
    # 既存CSVを使用（テスト用、再ダウンロード不要）
    python fetch.py --item Wheat --year 2023 --top-n 10 \\
        --csv ./cache/fao_data/Production_Crops_Livestock_E_All_Data_\\(Normalized\\).csv \\
        --output-dir ./out

    # フルダウンロード
    python fetch.py --item Wheat --year 2023 --top-n 10 --output-dir ./out

このレシピが扱う範囲:
- 単一作物 × 単一年 × 国別ランキング上位N
- Element="Production" 固定（"Area harvested" や "Yield" は別途）
- 集計地域（World, EU27 等）は除外

このレシピが扱わない範囲:
- 多年時系列 → faostat/crops_timeseries（未作成）
- 貿易データ → faostat/trade_matrix（未作成）
- 食料バランス → faostat/food_balance（未作成）
"""
import argparse
import hashlib
import json
import logging
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd


# ─── 定数 ───
FAO_BULK_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
CSV_NAME = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"

# 国別ランキングから除外する集計地域
# FAOSTAT 表記揺れ（LLDC/LLDCs等）への対応のため、両形を含める。
AGG_AREAS = {
    # 世界・大陸
    "World", "Africa", "Asia", "Europe", "Americas", "Oceania",
    # 中陸・小地域
    "Northern Africa", "Eastern Africa", "Western Africa", "Southern Africa", "Middle Africa", "Sub-Saharan Africa",
    "Northern America", "South America", "Central America", "Caribbean",
    "Eastern Asia", "Southern Asia", "South-eastern Asia", "Western Asia", "Central Asia",
    "Northern Europe", "Southern Europe", "Western Europe", "Eastern Europe",
    "Australia and New Zealand", "Melanesia", "Micronesia", "Polynesia",
    # 政治・経済グループ
    "European Union (27)", "European Union (28)",
    "Least Developed Countries",
    "Least Developed Countries (LDCs)",   # 2026-08-20 追記: FAO側で(LDCs)付きに改称され完全一致から漏れていた
    "Low Income Food Deficit Countries (LIFDCs)",
    "Net Food Importing Developing Countries (NFIDCs)",
    "Land Locked Developing Countries (LLDC)",
    "Land Locked Developing Countries (LLDCs)",
    "Small Island Developing States (SIDS)",
    # 中国の集計（mainland + Taiwan + HK + Macao の合計）
    # 通常の教材用途では "China, mainland" を採用するため、集計値は除外する
    "China",
    # 歴史的アグリゲート（古い年データで出る可能性）
    "Belgium-Luxembourg", "USSR", "Yugoslav SFR", "Czechoslovakia",
    "Serbia and Montenegro", "Sudan (former)", "Ethiopia PDR",
}

# 品目名の別名展開（FAOSTAT の表記揺れ対応）
ITEM_ALIASES = {
    "Wheat":     ["Wheat"],
    "Rice":      ["Rice, paddy", "Rice"],
    "Maize":     ["Maize (corn)"],
    "Corn":      ["Maize (corn)"],
    "Soybeans":  ["Soya beans"],
    "Soya":      ["Soya beans"],
    "Barley":    ["Barley"],
    "Potatoes":  ["Potatoes"],
    "Cassava":   ["Cassava, fresh"],
    "Sugarcane": ["Sugar cane"],
    "Cotton":    ["Cotton lint", "Seed cotton, unginned"],
    "Coffee":    ["Coffee, green"],
    "Tea":       ["Tea leaves"],
    "Cocoa":     ["Cocoa beans"],
    "Palm oil":  ["Oil, palm"],
}


class DataFetchError(Exception):
    """データ取得失敗時の構造化例外。"""

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


def download_zip(url: str, dest: Path, retries: int = 3, timeout: int = 300) -> None:
    """大容量ZIPをストリーミングダウンロード（リトライ付き）。"""
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as cl:
                with cl.stream("GET", url) as r:
                    r.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
            return
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("download retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError(
        source="FAOSTAT", url=url, kind="DOWNLOAD_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def extract_csv(zip_path: Path, csv_name: str, out_path: Path) -> None:
    """ZIPから本体CSVのみ抽出（Flag/AreaCode等のメタCSVは無視）。"""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        target = next((n for n in names if n == csv_name), None)
        if target is None:
            target = next(
                (n for n in names if n.endswith(".csv")
                 and "Flag" not in n and "AreaCode" not in n
                 and "ItemCode" not in n and "Element" not in n),
                None,
            )
        if target is None:
            raise DataFetchError(
                source="FAOSTAT", url="(zip)", kind="EXTRACT_FAIL",
                message=f"target CSV not found. names: {names[:5]}",
            )
        with zf.open(target) as src, open(out_path, "wb") as dst:
            dst.write(src.read())


def query_ranking(
    csv_path: Path, item: str, year: int,
    element: str = "Production", top_n: int = 10,
) -> pd.DataFrame:
    """国別ランキングを抽出。

    - FAOSTAT CSV は UTF-8。`encoding="latin-1"` で読むと `TÃ¼rkiye` 化けする。
    - 200_000行単位の chunk 読み込みでメモリを抑える（フルロードは300MB級）。
    - Item は ITEM_ALIASES で表記揺れ展開後、同一国内で合算。
    """
    aliases = ITEM_ALIASES.get(item, [item])
    use_cols = ["Area", "Item", "Element", "Year", "Unit", "Value"]

    chunks = []
    for chunk in pd.read_csv(
        csv_path, encoding="utf-8", usecols=use_cols,
        chunksize=200_000, low_memory=False,
    ):
        sel = chunk[
            (chunk["Element"] == element)
            & (chunk["Year"] == year)
            & (chunk["Item"].isin(aliases))
            & (~chunk["Area"].isin(AGG_AREAS))
        ]
        if not sel.empty:
            chunks.append(sel)

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)
    # 同一国内で複数 Item エイリアスがヒットした場合は合算
    df = df.groupby(["Area"], as_index=False).agg({
        "Value": "sum", "Item": "first", "Year": "first",
        "Element": "first", "Unit": "first",
    })
    df = df.sort_values("Value", ascending=False).head(top_n).reset_index(drop=True)
    df.insert(0, "Rank", df.index + 1)
    return df[["Rank", "Area", "Item", "Element", "Year", "Value", "Unit"]]


def save_metadata(
    meta_path: Path, *, item: str, year: int, element: str, top_n: int,
    raw_csv: Path, out_csv: Path, row_count: int,
) -> dict:
    meta = {
        "task_name": f"faostat_crops_ranking_{item.lower()}_{year}_top{top_n}",
        "source": {
            "name": "FAOSTAT Production_Crops_Livestock",
            "url": FAO_BULK_URL,
            "single_source": True,
        },
        "query": {
            "dataset": "Production_Crops_Livestock",
            "item": item,
            "item_aliases_searched": ITEM_ALIASES.get(item, [item]),
            "element": element,
            "year": year,
            "top_n": top_n,
            "exclude_aggregate_areas": True,
        },
        "units": "tonnes",
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "raw_csv_sha256": sha256_of(raw_csv),
        "missing_value_treatment": "公表値なしは空欄維持（推測補完なし）",
        "notes": (
            "国別ランキング。集計地域（World, EU27 等）は除外。"
            "Item は別名展開後に同一国で合算。"
        ),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(
        description="FAOSTAT 作物生産量 国別ランキング取得",
    )
    ap.add_argument("--item", required=True,
                    help="作物名 (例: Wheat, Rice, Maize)")
    ap.add_argument("--year", type=int, required=True,
                    help="対象年 (例: 2023)")
    ap.add_argument("--top-n", type=int, default=10,
                    help="上位N (default: 10)")
    ap.add_argument("--element", default="Production",
                    help="FAOSTAT Element (default: Production)")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"),
                    help="出力ディレクトリ")
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "faostat",
                    help="ZIP/CSV キャッシュ置き場")
    ap.add_argument("--csv", type=Path, default=None,
                    help="既存CSVを直接指定する場合のパス（ダウンロードをスキップ）")
    ap.add_argument("--force-download", action="store_true",
                    help="既存ZIPがあっても再ダウンロード")
    args = ap.parse_args()

    # Win cmd.exe (CP932) 対策
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # ─── CSV パス決定（既存指定 or キャッシュ） ───
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = args.cache_dir / "Production_Crops_Livestock.zip"
    csv_path = args.csv if args.csv else (args.cache_dir / CSV_NAME)

    if not csv_path.exists():
        if not zip_path.exists() or args.force_download:
            logging.info("ZIPダウンロード開始: %s", FAO_BULK_URL)
            try:
                download_zip(FAO_BULK_URL, zip_path)
            except DataFetchError as e:
                logging.error("ダウンロード失敗: %s", e)
                return 1
            logging.info("保存完了: %s (%d MB)", zip_path,
                         zip_path.stat().st_size // (1024 * 1024))
        try:
            extract_csv(zip_path, CSV_NAME, csv_path)
        except DataFetchError as e:
            logging.error("ZIP展開失敗: %s", e)
            return 1
        logging.info("CSV抽出完了: %s (%d MB)", csv_path,
                     csv_path.stat().st_size // (1024 * 1024))
    else:
        logging.info("既存CSV使用: %s", csv_path)

    # ─── クエリ実行 ───
    logging.info("クエリ: item=%s year=%d element=%s top_n=%d",
                 args.item, args.year, args.element, args.top_n)
    df = query_ranking(csv_path, args.item, args.year,
                       element=args.element, top_n=args.top_n)
    if df.empty:
        logging.error(
            "該当データなし (item=%s, aliases=%s, year=%d, element=%s)",
            args.item, ITEM_ALIASES.get(args.item, [args.item]),
            args.year, args.element,
        )
        return 1

    # ─── 出力 ───
    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_faostat_{args.item.lower()}_{args.year}_top{args.top_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    df.to_csv(out_csv, index=False, encoding="utf-8")
    meta = save_metadata(
        out_meta,
        item=args.item, year=args.year, element=args.element, top_n=args.top_n,
        raw_csv=csv_path, out_csv=out_csv, row_count=len(df),
    )
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(df), meta["csv_sha256"][:12])
    logging.info("metadata: %s", out_meta)

    # ─── 結果サマリ ───
    print(f"\n== FAOSTAT {args.item} {args.element} Top {args.top_n} ({args.year}) ==")
    for _, row in df.iterrows():
        print(f"  {row['Rank']:>2}  {row['Area']:<35}  "
              f"{row['Value']:>15,.0f}  {row['Unit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
