"""fetch.py — Our World in Data エネルギーデータ取得

OWID energy-data (github raw CSV) から指定国の一次エネルギー構成比 or 絶対量を
取得して CSV + metadata.json に保存する。

使い方:
    # 日本の一次エネルギー構成比 2010-2023
    python fetch.py --country Japan --year-from 2010 --year-to 2023 \\
        --mode share --output-dir ./output

    # 中国の絶対量（TWh）
    python fetch.py --country China --mode abs --output-dir ./output

このレシピが扱う範囲:
- 単一国 × 任意年範囲 × エネルギー構成（share or abs）
- 認証不要（github raw 公開データ）
- TTL キャッシュ（7日 default）

このレシピが扱わない範囲:
- 多国比較 → 別レシピ `owid/energy_compare`（未作成）
- 発電量別カラム（solar/wind/hydro 等の電力指標） → 別 metrics 指定
- 排出量データ → owid/co2-data（別ファイル）
"""
from __future__ import annotations  # py3.9 で PEP604 `X | None` 注釈を使うため

import argparse
import csv
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd


# ─── 定数 ───
OWID_CSV_URL = (
    "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"
)
OWID_FILENAME = "owid-energy-data.csv"
DEFAULT_TTL_DAYS = 7

# 一次エネルギー源
PRIMARY_SOURCES = ["coal", "oil", "gas", "nuclear", "renewables"]
SOURCE_LABEL_JP = {
    "coal": "石炭", "oil": "石油", "gas": "天然ガス",
    "nuclear": "原子力", "renewables": "再エネ",
}

# 発電量列の参考（metrics 指定時）
GENERATION_COLS = [
    "solar_electricity", "wind_electricity", "hydro_electricity",
    "nuclear_electricity", "coal_electricity", "gas_electricity",
    "oil_electricity", "renewables_electricity", "electricity_generation",
]


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


def is_cache_fresh(cache_path: Path, ttl_days: int) -> bool:
    """TTL 内ならキャッシュ有効。"""
    if not cache_path.exists():
        return False
    age_days = (datetime.now().timestamp() - cache_path.stat().st_mtime) / 86400
    return age_days < ttl_days


def download_csv(url: str, dest: Path, retries: int = 3, timeout: int = 120) -> None:
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
        source="OWID", url=url, kind="DOWNLOAD_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def query_country(
    csv_path: Path, country: str, year_from: int, year_to: int, step: int | None,
) -> pd.DataFrame:
    """指定国・年範囲でデータ抽出。"""
    df = pd.read_csv(csv_path, low_memory=False)
    df = df[df["country"] == country].copy()
    df = df[(df["year"] >= year_from) & (df["year"] <= year_to)]
    df = df.sort_values("year")
    if step and step > 1:
        df = df[df["year"] % step == 0]
    return df


def find_candidates(csv_path: Path, query: str) -> list[str]:
    """国名候補を検索（タイプミス対策）。"""
    df = pd.read_csv(csv_path, usecols=["country"], low_memory=False)
    candidates = df["country"].unique()
    q_lower = query.lower()
    return [c for c in candidates if q_lower in str(c).lower()][:10]


def to_share_rows(df: pd.DataFrame) -> list[dict]:
    """構成比モード: 各エネルギー源の share_energy 列を抽出。"""
    rows = []
    for _, r in df.iterrows():
        row = {"year": int(r["year"])}
        for src in PRIMARY_SOURCES:
            col = f"{src}_share_energy"
            v = r.get(col)
            row[f"{src}_pct"] = round(float(v), 2) if pd.notna(v) else None
        total = sum(row[f"{s}_pct"] for s in PRIMARY_SOURCES
                    if row[f"{s}_pct"] is not None)
        row["total_pct"] = round(total, 2)
        rows.append(row)
    return rows


def to_abs_rows(df: pd.DataFrame) -> list[dict]:
    """絶対量モード: TWh 単位の consumption 列を抽出。"""
    rows = []
    for _, r in df.iterrows():
        row = {"year": int(r["year"])}
        total = r.get("primary_energy_consumption")
        row["total_twh"] = round(float(total), 1) if pd.notna(total) else None
        for src in PRIMARY_SOURCES:
            col = f"{src}_consumption"
            v = r.get(col)
            row[f"{src}_twh"] = round(float(v), 1) if pd.notna(v) else None
        rows.append(row)
    return rows


def to_metrics_rows(df: pd.DataFrame, metrics: list[str]) -> list[dict]:
    """任意 metrics 列を抽出。"""
    rows = []
    for _, r in df.iterrows():
        row = {"year": int(r["year"])}
        for m in metrics:
            v = r.get(m)
            row[m] = round(float(v), 3) if pd.notna(v) else None
        rows.append(row)
    return rows


def save_csv(rows: list[dict], out_path: Path) -> None:
    if not rows:
        return
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def save_metadata(
    meta_path: Path, *, country: str, year_from: int, year_to: int, mode: str,
    metrics: list[str], cache_path: Path, out_csv: Path, row_count: int,
    cache_age_days: float,
) -> dict:
    meta = {
        "task_name": f"owid_energy_{country.lower().replace(' ', '_')}_{year_from}_{year_to}_{mode}",
        "source": {
            "name": "Our World in Data — energy-data (GitHub master)",
            "url": OWID_CSV_URL,
            "single_source": True,
            "underlying_sources": ["IEA", "BP Statistical Review of World Energy", "Ember"],
        },
        "query": {
            "country": country,
            "year_from": year_from,
            "year_to": year_to,
            "mode": mode,
            "metrics": metrics or None,
        },
        "units": {
            "share": "% of primary energy",
            "abs": "TWh (terawatt-hours, primary energy)",
            "metrics": "varies by column (see OWID docs)",
        }.get(mode, "varies"),
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "raw_csv_sha256": sha256_of(cache_path),
        "cache_age_days_at_fetch": round(cache_age_days, 2),
        "missing_value_treatment": "null は null として保持（推測補完なし）",
        "notes": (
            "OWID は IEA / BP / Ember 統計を統合した派生データ。原典より少し遅れて更新。"
            "country 列に集計値 (World, OECD, EU 等) も含まれる。"
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
        description="OWID エネルギーデータ取得",
    )
    ap.add_argument("--country", required=True, help="国名 (例: Japan, China, World)")
    ap.add_argument("--year-from", type=int, default=1990, help="開始年 (default: 1990)")
    ap.add_argument("--year-to", type=int, default=2100, help="終了年 (default: 2100)")
    ap.add_argument("--mode", default="share", choices=["share", "abs", "metrics"],
                    help="share=構成比 / abs=絶対量 / metrics=任意列")
    ap.add_argument("--metrics", default="",
                    help="mode=metrics の場合の列名カンマ区切り (例: solar_electricity,wind_electricity)")
    ap.add_argument("--step", type=int, default=None,
                    help="年の間引きステップ (例: 5 で5年毎)")
    ap.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS,
                    help=f"キャッシュTTL日数 (default: {DEFAULT_TTL_DAYS})")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "owid",
                    help="ダウンロードキャッシュ")
    ap.add_argument("--cache", type=Path, default=None,
                    help="既存CSV を直接指定（ダウンロード省略）")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ─── キャッシュ管理（TTL + sha256 確認） ───
    if args.cache:
        cache_path = args.cache
        if not cache_path.exists():
            logging.error("指定 cache 存在せず: %s", cache_path)
            return 1
        logging.info("既存CSV使用: %s", cache_path)
    else:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = args.cache_dir / OWID_FILENAME
        if not is_cache_fresh(cache_path, args.ttl_days):
            logging.info("キャッシュ古い or 不在 → ダウンロード: %s", OWID_CSV_URL)
            try:
                download_csv(OWID_CSV_URL, cache_path)
            except DataFetchError as e:
                logging.error("ダウンロード失敗: %s", e)
                return 1
        else:
            age = (datetime.now().timestamp() - cache_path.stat().st_mtime) / 86400
            logging.info("キャッシュ使用 (age=%.1f days): %s", age, cache_path)

    cache_age_days = (datetime.now().timestamp() - cache_path.stat().st_mtime) / 86400

    # ─── クエリ ───
    df = query_country(cache_path, args.country, args.year_from, args.year_to,
                       args.step)
    if df.empty:
        candidates = find_candidates(cache_path, args.country)
        logging.error(
            "国 '%s' のデータなし。候補: %s",
            args.country, candidates,
        )
        return 1

    # ─── モード別出力 ───
    metrics_list = []
    if args.mode == "share":
        out_rows = to_share_rows(df)
    elif args.mode == "abs":
        out_rows = to_abs_rows(df)
    else:  # metrics
        metrics_list = [m.strip() for m in args.metrics.split(",") if m.strip()]
        if not metrics_list:
            logging.error("mode=metrics には --metrics 指定が必要")
            return 1
        unknown = [m for m in metrics_list if m not in df.columns]
        if unknown:
            logging.error("未知の列: %s\n利用可能な発電列例: %s",
                          unknown, GENERATION_COLS)
            return 1
        out_rows = to_metrics_rows(df, metrics_list)

    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_owid_energy_{args.country.lower().replace(' ', '_')}_{args.year_from}_{args.year_to}_{args.mode}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    save_csv(out_rows, out_csv)
    meta = save_metadata(
        out_meta, country=args.country, year_from=args.year_from,
        year_to=args.year_to, mode=args.mode, metrics=metrics_list,
        cache_path=cache_path, out_csv=out_csv, row_count=len(out_rows),
        cache_age_days=cache_age_days,
    )
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(out_rows), meta["csv_sha256"][:12])

    # ─── サマリ表示 ───
    print(f"\n== OWID Energy {args.country} {args.year_from}-{args.year_to} ({args.mode}) ==")
    if args.mode == "share":
        print(f"  {'年':>4}  " + "  ".join(f"{SOURCE_LABEL_JP[s]:>6}(%)" for s in PRIMARY_SOURCES) + "  合計")
        for r in out_rows[-15:]:
            vals = "  ".join(
                f"{r[f'{s}_pct']:>9.1f}" if r[f'{s}_pct'] is not None else f"{'—':>9}"
                for s in PRIMARY_SOURCES
            )
            print(f"  {r['year']:>4}  {vals}  {r['total_pct']:>5.1f}")
    elif args.mode == "abs":
        print(f"  {'年':>4}  {'合計(TWh)':>12}  " + "  ".join(f"{SOURCE_LABEL_JP[s]:>8}(TWh)" for s in PRIMARY_SOURCES))
        for r in out_rows[-15:]:
            total = f"{r['total_twh']:>12,.0f}" if r['total_twh'] else f"{'—':>12}"
            vals = "  ".join(
                f"{r[f'{s}_twh']:>12,.0f}" if r[f'{s}_twh'] is not None else f"{'—':>12}"
                for s in PRIMARY_SOURCES
            )
            print(f"  {r['year']:>4}  {total}  {vals}")
    else:
        print(f"  {'year':<6}  " + "  ".join(f"{m[:18]:>18}" for m in metrics_list))
        for r in out_rows[-15:]:
            vals = "  ".join(
                f"{r[m]:>18,.1f}" if r[m] is not None else f"{'—':>18}"
                for m in metrics_list
            )
            print(f"  {r['year']:<6}  {vals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
