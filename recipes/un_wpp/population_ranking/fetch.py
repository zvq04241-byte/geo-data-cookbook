"""fetch.py — UN World Population Prospects 国別人口ランキング取得

UN WPP 2024 から指定年・variant の国別人口を取得し、上位N国のランキングを
CSV + metadata.json に保存する。

使い方:
    # 2024年 中位推計 上位20
    python fetch.py --year 2024 --top-n 20 --output-dir ./output

    # 既存キャッシュを使う場合（テスト時）
    python fetch.py --year 2024 --top-n 20 \\
        --cache ./cache/.wpp_cache/WPP2024_TotalPopulationBySex.csv.gz \\
        --output-dir ./output

このレシピが扱う範囲:
- 単一年 × Variant × 国別人口ランキング上位N
- 認証不要（UN 公開バルクデータ）

このレシピが扱わない範囲:
- 多年時系列 → 別レシピ `un_wpp/population_timeseries`（未作成）
- 地域・大陸別の集計 → `LocTypeID` 切替が必要（別レシピ）
- 年齢別・性別 → 別ファイルを使う（WPP2024_PopulationBySingleAgeSex 等）
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


# ─── 定数 ───
WPP_URL = (
    "https://population.un.org/wpp/assets/Excel%20Files/"
    "1_Indicator%20(Standard)/CSV_FILES/WPP2024_TotalPopulationBySex.csv.gz"
)
WPP_FILENAME = "WPP2024_TotalPopulationBySex.csv.gz"

# LocTypeID（UN WPP 仕様）
LOC_TYPE_COUNTRY = "4"     # 国
LOC_TYPE_REGION = "2"      # 地域
LOC_TYPE_WORLD = "1"       # 世界


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


def download_gz(url: str, dest: Path, retries: int = 3, timeout: int = 300) -> None:
    """gz CSV をストリーミングダウンロード。"""
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
        source="UN WPP", url=url, kind="DOWNLOAD_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def load_wpp_csv(gz_path: Path) -> list[dict]:
    """gz CSV を DictReader で全行読み込み。

    重要: encoding="utf-8-sig" — UN WPP は BOM 付き UTF-8。
    通常の "utf-8" で読むと最初の列名に BOM が混ざる。
    """
    with gzip.open(gz_path, "rb") as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8-sig")
        reader = csv.DictReader(text)
        return list(reader)


def filter_country_year(
    rows: list[dict], year: int, variant: str,
) -> list[dict]:
    """国レベル・指定年・variant でフィルタ。"""
    year_str = str(year)
    return [
        r for r in rows
        if r.get("Variant") == variant
        and r.get("LocTypeID") == LOC_TYPE_COUNTRY
        and r.get("Time") == year_str
        and r.get("PopTotal", "").strip()
    ]


def rank_top_n(rows: list[dict], top_n: int) -> list[dict]:
    """PopTotal (千人単位) で降順ソート → 上位N。"""
    def _to_float(r):
        try:
            return float(r["PopTotal"])
        except (ValueError, TypeError):
            return 0.0
    sorted_rows = sorted(rows, key=_to_float, reverse=True)
    result = []
    for rank, r in enumerate(sorted_rows[:top_n], 1):
        pop_thousand = float(r["PopTotal"])
        result.append({
            "rank": rank,
            "iso3": r.get("ISO3_code", ""),
            "iso2": r.get("ISO2_code", ""),
            "location": r.get("Location", ""),
            "year": int(r["Time"]),
            "variant": r["Variant"],
            "population_thousand": pop_thousand,
            "population_million": round(pop_thousand / 1000, 3),
            "pop_density": r.get("PopDensity", "").strip() or None,
        })
    return result


def save_csv(rows: list[dict], out_path: Path) -> None:
    if not rows:
        return
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def save_metadata(
    meta_path: Path, *, year: int, variant: str, top_n: int,
    out_csv: Path, raw_gz: Path, row_count: int,
) -> dict:
    meta = {
        "task_name": f"wpp_population_ranking_{year}_{variant.lower()}_top{top_n}",
        "source": {
            "name": "UN World Population Prospects 2024",
            "url": WPP_URL,
            "single_source": True,
        },
        "query": {
            "year": year,
            "variant": variant,
            "loc_type": "country",
            "loc_type_id": LOC_TYPE_COUNTRY,
            "top_n": top_n,
        },
        "units": "thousand persons (PopTotal); million persons (population_million)",
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "raw_gz_sha256": sha256_of(raw_gz),
        "missing_value_treatment": "PopTotal 空欄行は除外（推測補完なし）",
        "notes": (
            "Variant=Medium は中位推計（最頻使用）。Low/High も同じファイルに含む。"
            "LocTypeID=4 が国レベル、=2 が地域、=1 が世界。"
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
        description="UN WPP 2024 国別人口ランキング取得",
    )
    ap.add_argument("--year", type=int, required=True, help="対象年 (例: 2024)")
    ap.add_argument("--variant", default="Medium",
                    choices=["Medium", "Low", "High", "Constant fertility",
                             "Instant replacement", "Zero migration", "No change"],
                    help="WPP variant (default: Medium)")
    ap.add_argument("--top-n", type=int, default=20, help="上位N (default: 20)")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"),
                    help="出力ディレクトリ")
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "wpp",
                    help="ダウンロードキャッシュ")
    ap.add_argument("--cache", type=Path, default=None,
                    help="既存 gz ファイルを直接指定（ダウンロード省略）")
    args = ap.parse_args()

    # Win cmd.exe (CP932) 対策
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ─── キャッシュ・ダウンロード ───
    if args.cache:
        gz_path = args.cache
        if not gz_path.exists():
            logging.error("指定 cache が存在しません: %s", gz_path)
            return 1
        logging.info("既存 gz 使用: %s", gz_path)
    else:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        gz_path = args.cache_dir / WPP_FILENAME
        if not gz_path.exists():
            logging.info("gz ダウンロード: %s", WPP_URL)
            try:
                download_gz(WPP_URL, gz_path)
            except DataFetchError as e:
                logging.error("ダウンロード失敗: %s", e)
                return 1
            logging.info("保存完了: %s (%d MB)", gz_path,
                         gz_path.stat().st_size // (1024 * 1024))

    # ─── ロード・フィルタ・ランキング ───
    logging.info("CSV読み込み中（大ファイル、数秒かかる）")
    all_rows = load_wpp_csv(gz_path)
    logging.info("全レコード: %d", len(all_rows))

    filtered = filter_country_year(all_rows, args.year, args.variant)
    logging.info("フィルタ後 (year=%d, variant=%s, country): %d",
                 args.year, args.variant, len(filtered))
    if not filtered:
        logging.error("該当データなし")
        return 1

    ranked = rank_top_n(filtered, args.top_n)

    # ─── 出力 ───
    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_wpp_population_{args.year}_{args.variant.lower()}_top{args.top_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    save_csv(ranked, out_csv)
    meta = save_metadata(
        out_meta, year=args.year, variant=args.variant, top_n=args.top_n,
        out_csv=out_csv, raw_gz=gz_path, row_count=len(ranked),
    )
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(ranked), meta["csv_sha256"][:12])
    logging.info("metadata: %s", out_meta)

    # ─── サマリ表示 ───
    print(f"\n== UN WPP 2024 国別人口 Top {args.top_n} ({args.year}, {args.variant}) ==")
    for r in ranked:
        print(f"  {r['rank']:>3}  {r['location']:<30}  "
              f"{r['population_million']:>10.1f} M  ISO3={r['iso3']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
