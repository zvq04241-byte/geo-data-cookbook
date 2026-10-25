"""fetch.py ― 市区町村境界（国土数値情報 N03, 都道府県単位）

国土数値情報 行政区域データ N03 から指定都道府県の市区町村ポリゴンを取得し、
muni_code で dissolve した GeoPackage を出力する。検証用に「面積ランキング CSV」も併産。

使い方:
    # 新潟県(15) 2020年版
    python fetch.py --pref-code 15 --year 2020 --output-dir ./output

出力:
    output/n03_municipal_<pref>_<year>.gpkg         … 市区町村ポリゴン(EPSG:4326)
    output/YYYYMMDD_n03_municipal_<pref>_<year>_manifest.csv … 面積降順マニフェスト
    output/..._metadata.json

このレシピが扱う範囲:
- 都道府県単位の市区町村境界（N03, dissolve済み）＋面積マニフェスト（認証不要）

このレシピが扱わない範囲:
- 全国一括 → 都道府県ごとにループ（本レシピを pref_code 単位で呼ぶ）
- 都道府県境界（47面）→ 別レシピ `naturalearth/japan_prefectures`
- 統計値の結合・地図描画 → 各プロジェクト側
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

N03_BASE = "https://nlftp.mlit.go.jp/ksj/gml/data/N03"
# N03 のファイル名の日付（年→基準日の表記）。国土数値情報の配布ページ
# https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2024.html に載るファイル名から写した（2026-10-26）。
# 2020年以降は YYYYMMDD、2019年以前は YYMMDD。2025 は同じ形の URL が 200 を返すことを確認。
# 1年に複数版ある年（2007・2010 等）は、ここでは片方だけを入れている。表に無い年は止める（推測しない）。
MLIT_DATES = {2000: "001001", 2010: "101001", 2015: "150101", 2016: "160101",
              2017: "170101", 2018: "180101", 2019: "190101",
              2020: "20200101", 2021: "20210101", 2022: "20220101",
              2023: "20230101", 2024: "20240101", 2025: "20250101"}
EQUAL_AREA_CRS = "EPSG:6933"  # World Cylindrical Equal Area（面積算出用, m²）


class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source, self.url, self.kind, self.original = source, url, kind, original


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_n03(pref_code: str, year: int, date_str: str | None = None,
                 retries: int = 3, timeout: int = 120):
    """N03 zip を取得し、(bytes, url) を返す。日付は MLIT_DATES か --date。推測はしない。"""
    date_str = date_str or MLIT_DATES.get(year)
    if not date_str:
        raise DataFetchError(source="MLIT N03", url=N03_BASE, kind="UNKNOWN_DATE",
                             message=(f"{year}年のファイル名の日付が表に無い。配布ページで確かめて "
                                      "--date で渡す（推測で URL を作らない）"))
    url = f"{N03_BASE}/N03-{year}/N03-{date_str}_{pref_code}_GML.zip"
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as cl:
                r = cl.get(url)
                r.raise_for_status()
            return r.content, url
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("N03 retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError(source="MLIT N03", url=url, kind="DOWNLOAD_FAIL",
                         message=f"failed after {retries} attempts", original=last_err)


def load_municipalities(zip_bytes: bytes, url: str):
    """zip 内 shapefile を cp932 で読み、muni_code で dissolve した GeoDataFrame を返す。"""
    import geopandas as gpd
    import pandas as pd
    from shapely import make_valid

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        shp_files = [n for n in zf.namelist() if n.endswith(".shp")]
        if not shp_files:
            raise DataFetchError(source="MLIT N03", url=url, kind="NO_SHP",
                                 message="ZIP に .shp がありません")
        with tempfile.TemporaryDirectory() as tmp:
            zf.extractall(tmp)
            # ハマり所: N03 shapefile の属性は cp932（Shift-JIS系）。utf-8 で読むと文字化け
            gdf = gpd.read_file(f"{tmp}/{shp_files[0]}", encoding="cp932")

    gdf = gdf.rename(columns={"N03_007": "muni_code", "N03_001": "PREF_NAME",
                              "N03_004": "CITY_NAME"})
    if "muni_code" not in gdf.columns:
        raise DataFetchError(source="MLIT N03", url=url, kind="NO_MUNI_CODE",
                             message=f"N03_007 列がありません: {list(gdf.columns)}")
    gdf["muni_code_raw"] = gdf["muni_code"]
    gdf["muni_code"] = (gdf["muni_code"].astype(str).str.strip()
                        .str.replace(r"\.0$", "", regex=True).str.zfill(5))
    # 行政コードが5桁数字でない行（所属未定地など）を除外し、外した行を記録する
    ok = gdf["muni_code"].str.match(r"^\d{5}$")
    dropped = (pd.DataFrame({"N03_007": gdf.loc[~ok, "muni_code_raw"].fillna("(空)").astype(str).values,
                             "CITY_NAME": gdf.loc[~ok, "CITY_NAME"].fillna("(空)").astype(str).values})
               .value_counts(dropna=False).rename("rows").reset_index().to_dict("records"))
    dropped = [{k: (int(v) if k == "rows" else v) for k, v in d.items()} for d in dropped]
    gdf = gdf[ok].drop(columns=["muni_code_raw"]).copy()
    # 同じ行政コードに別の名前が付いていないか（dissolve の first で黙って片方を選ばない）
    names = gdf.groupby("muni_code")["CITY_NAME"].nunique(dropna=False)
    if (names > 1).any():
        raise DataFetchError(source="MLIT N03", url=url, kind="NAME_CONFLICT",
                             message=f"同じ行政コードに複数の名前: {names[names > 1].index.tolist()}")
    gdf["geometry"] = gdf.geometry.apply(make_valid)
    muni = gdf.dissolve(by="muni_code", aggfunc="first").reset_index()
    return muni.to_crs("EPSG:4326"), {"n_rows_raw": int(len(ok)), "dropped_invalid_code_rows": dropped}


def write_manifest(muni, csv_path: Path) -> int:
    """市区町村を面積(平方km)降順に並べたマニフェスト CSV を書く。"""
    import csv as _csv
    area_km2 = muni.to_crs(EQUAL_AREA_CRS).geometry.area / 1e6
    recs = []
    for (_, row), a in zip(muni.iterrows(), area_km2):
        name = row.get("CITY_NAME") or row["muni_code"]
        recs.append({"area": name, "value": round(float(a), 2),
                     "muni_code": row["muni_code"],
                     "pref": row.get("PREF_NAME", "")})
    recs.sort(key=lambda r: r["value"], reverse=True)
    with open(csv_path, "w", encoding="utf-8", newline="\n") as f:
        w = _csv.writer(f)
        w.writerow(["Rank", "Area", "Value", "MuniCode", "PrefName", "Unit"])
        for i, r in enumerate(recs, 1):
            w.writerow([i, r["area"], r["value"], r["muni_code"], r["pref"], "km2"])
    return len(recs)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="国土数値情報 N03 市区町村境界取得")
    ap.add_argument("--pref-code", default="15",
                    help="都道府県コード2桁 (例 13=東京, 15=新潟)。default 15")
    ap.add_argument("--year", type=int, default=2020,
                    help="N03 の版の年 (default 2020)")
    ap.add_argument("--date", default=None,
                    help="ファイル名の日付（MLIT_DATES に無い年・複数版ある年に使う。例 110331）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "n03")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    pref = str(args.pref_code).zfill(2)

    import geopandas as gpd
    gpkg = args.output_dir / f"n03_municipal_{pref}_{args.year}.gpkg"
    cache_gpkg = args.cache_dir / f"muni_{pref}_{args.year}.gpkg"

    cache_meta = cache_gpkg.with_suffix(".json")
    if cache_gpkg.exists() and cache_meta.exists():
        logging.info("キャッシュ使用: %s", cache_gpkg)
        muni = gpd.read_file(cache_gpkg)
        cinfo = json.loads(cache_meta.read_text(encoding="utf-8"))
        cinfo["from_cache"] = True
    else:
        try:
            zip_bytes, src_url = download_n03(pref, args.year, args.date)
            muni, load_info = load_municipalities(zip_bytes, src_url)
        except DataFetchError as e:
            logging.error("%s", e)
            return 1
        cinfo = {"url": src_url, "zip_sha256": hashlib.sha256(zip_bytes).hexdigest(),
                 "zip_bytes": len(zip_bytes),
                 "downloaded_at": datetime.now(timezone.utc).astimezone().isoformat(),
                 **load_info}
        muni[["muni_code", "PREF_NAME", "CITY_NAME", "geometry"]].to_file(
            cache_gpkg, driver="GPKG")
        cache_meta.write_text(json.dumps(cinfo, ensure_ascii=False, indent=1), encoding="utf-8")
        cinfo["from_cache"] = False

    # 自己検証: 市区町村が取れて、コードが県プレフィックスと一致（混入したら止める）
    if len(muni) == 0:
        logging.error("市区町村が0件です")
        return 1
    bad = muni[~muni["muni_code"].astype(str).str.startswith(pref)]
    if len(bad) > 0:
        logging.error("県コード %s 以外の muni_code が %d 件: %s", pref, len(bad),
                      bad["muni_code"].tolist()[:10])
        return 1

    muni[["muni_code", "PREF_NAME", "CITY_NAME", "geometry"]].to_file(
        gpkg, driver="GPKG")
    today = datetime.now().strftime("%Y%m%d")
    csv_path = args.output_dir / f"{today}_n03_municipal_{pref}_{args.year}_manifest.csv"
    meta_path = args.output_dir / f"{today}_n03_municipal_{pref}_{args.year}_metadata.json"
    n = write_manifest(muni, csv_path)

    is_ku = muni["CITY_NAME"].astype(str).str.endswith("区")
    tokubetsu = muni["muni_code"].astype(str).str.match(r"^131\d\d$")  # 東京23区は区そのものが市町村
    n_ward = int((is_ku & ~tokubetsu).sum())
    n_drop = sum(d["rows"] for d in cinfo.get("dropped_invalid_code_rows", []))
    scope = (f"都道府県コード {pref} の行政コード（muni_code）{n}件すべて。"
             f"政令市は区ごとに1件（政令市の区 {n_ward}件）で、市そのものの行は無い。"
             f"行政コードが5桁数字でない行 {n_drop}行（所属未定地など）は除外")
    meta = {
        "task_name": f"n03_municipal_{pref}_{args.year}",
        "source": {"name": "国土数値情報 行政区域 N03", "url": cinfo["url"],
                   "zip_sha256": cinfo["zip_sha256"], "downloaded_at": cinfo["downloaded_at"],
                   "from_cache": cinfo["from_cache"], "single_source": True},
        "crs": "EPSG:4326",
        "query": {"pref_code": pref, "year": args.year,
                  "file_date": cinfo["url"].rsplit("N03-", 1)[-1].split("_")[0]},
        "scope": scope,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "municipality_count": n,
        "municipality_count_definition": "muni_code のユニーク数（政令市は区を1件と数え、市本体は含まない）",
        "n_rows_raw": cinfo.get("n_rows_raw"),
        "dropped_invalid_code_rows": cinfo.get("dropped_invalid_code_rows"),
        "gpkg_sha256": sha256_of(gpkg),
        "csv_sha256": sha256_of(csv_path),
        "notes": ("N03 属性は cp932。N03_007=行政コードで dissolve（同じコードに別名があれば止める）。"
                  "面積は EPSG:6933(equal-area)で算出した 平方km。ファイル名の日付は基準日の表記。"),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    logging.info("出力: %s (muni_code %d件・区を含む)", gpkg.name, n)

    print(f"\n== N03 市区町村境界 {pref} ({args.year}) muni_code {n}件 ==")
    print(f"  範囲: {scope}")
    print(f"  GPKG: {gpkg}")
    print("  面積トップ5(平方km):")
    import csv as _csv
    with open(csv_path, encoding="utf-8") as f:
        for r in list(_csv.DictReader(f))[:5]:
            print(f"    {r['Rank']:>2}  {r['Area']:<10}  {r['Value']:>8} 平方km  {r['MuniCode']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
