"""fetch.py — 日本の都道府県境界（Natural Earth 10m admin-1, 北方領土を北海道に統合）

Natural Earth 10m admin-1 から日本の47都道府県ポリゴンを取得し、
北方4島（択捉・国後・色丹・歯舞）をロシア(サハリン州)ポリゴンから切り出して
北海道に統合した GeoPackage を出力する。検証用に都道府県マニフェスト CSV も併産。

★ このレシピは「日本地図は北方領土を必ず含める」ルールの実装基準。
   北海道の最東端経度が 147.5°E 未満（=北方領土欠落）なら例外で停止する。

使い方:
    python fetch.py --output-dir ./output

出力:
    output/japan_prefectures.gpkg              … 47都道府県ポリゴン (EPSG:4326)
    output/YYYYMMDD_japan_prefectures_manifest.csv … 都道府県マニフェスト（最東端経度で降順）
    output/..._metadata.json

このレシピが扱う範囲:
- 都道府県レベルの境界（47面）＋北方領土統合（認証不要・Natural Earth）

このレシピが扱わない範囲:
- 市区町村境界 → 別レシピ `mlit/n03_municipal_boundary`（未作成・MLIT N03）
- 統計値の結合・地図描画 → 本レシピは境界のみ（描画は各プロジェクト側）
"""
import argparse
import hashlib
import io
import json
import logging
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

NE10_URL = ("https://naciscdn.org/naturalearth/10m/cultural/"
            "ne_10m_admin_1_states_provinces.zip")
NE10_SHP_NAME = "ne_10m_admin_1_states_provinces.shp"

# 北方4島の切り出し bbox（得撫島 45.7°N 以北を除くため北限 45.6°N）
NT_BBOX = (145.0, 43.0, 149.5, 45.6)
# 北方領土を含む北海道の最東端経度の下限（択捉島東端 ≈148.8°E、根室 ≈145.8°E）
HOKKAIDO_MAXLON_MIN = 147.5

# Natural Earth 10m admin-1 の name（長音符付き）→ 日本語都道府県名
NE_NAME_TO_JP = {
    "Hokkaidō": "北海道", "Aomori": "青森県", "Iwate": "岩手県",
    "Miyagi": "宮城県", "Akita": "秋田県", "Yamagata": "山形県",
    "Fukushima": "福島県", "Ibaraki": "茨城県", "Tochigi": "栃木県",
    "Gunma": "群馬県", "Saitama": "埼玉県", "Chiba": "千葉県",
    "Tokyo": "東京都", "Kanagawa": "神奈川県", "Niigata": "新潟県",
    "Toyama": "富山県", "Ishikawa": "石川県", "Fukui": "福井県",
    "Yamanashi": "山梨県", "Nagano": "長野県", "Gifu": "岐阜県",
    "Shizuoka": "静岡県", "Aichi": "愛知県", "Mie": "三重県",
    "Shiga": "滋賀県", "Kyōto": "京都府", "Ōsaka": "大阪府",
    "Hyōgo": "兵庫県", "Nara": "奈良県", "Wakayama": "和歌山県",
    "Tottori": "鳥取県", "Shimane": "島根県", "Okayama": "岡山県",
    "Hiroshima": "広島県", "Yamaguchi": "山口県", "Tokushima": "徳島県",
    "Kagawa": "香川県", "Ehime": "愛媛県", "Kōchi": "高知県",
    "Fukuoka": "福岡県", "Saga": "佐賀県", "Nagasaki": "長崎県",
    "Kumamoto": "熊本県", "Ōita": "大分県", "Miyazaki": "宮崎県",
    "Kagoshima": "鹿児島県", "Okinawa": "沖縄県",
}


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


def download_ne(cache_dir: Path, retries: int = 3, timeout: int = 180) -> Path:
    """NE 10m admin-1 zip を取得・展開し、shp パスを返す（キャッシュ優先）。"""
    shp = cache_dir / NE10_SHP_NAME
    if shp.exists():
        return shp
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as cl:
                r = cl.get(NE10_URL)
                r.raise_for_status()
            cache_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall(cache_dir)
            if not shp.exists():
                raise DataFetchError(
                    source="Natural Earth", url=NE10_URL, kind="SHP_MISSING",
                    message=f"{NE10_SHP_NAME} not found after extract")
            return shp
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("NE download retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError(source="Natural Earth", url=NE10_URL, kind="DOWNLOAD_FAIL",
                         message=f"failed after {retries} attempts", original=last_err)


def build_prefectures(shp: Path):
    """都道府県 GeoDataFrame を構築（北方領土を北海道へ統合）。"""
    import geopandas as gpd
    from shapely.geometry import box as sbox
    from shapely.ops import unary_union

    world = gpd.read_file(shp)
    japan = world[world["admin"] == "Japan"].copy()
    japan["pref_jp"] = japan["name"].map(NE_NAME_TO_JP)
    # 名称マッピング漏れは name_local でフォールバック
    mask = japan["pref_jp"].isna()
    if mask.any() and "name_local" in japan.columns:
        japan.loc[mask, "pref_jp"] = japan.loc[mask, "name_local"]

    # ── 北方4島をロシア(サハリン州)から切り出して北海道へ統合 ──
    nt_box = sbox(*NT_BBOX)
    russia = world[world["admin"] == "Russia"]
    nt_geoms = []
    for geom in russia.geometry:
        if geom.intersects(nt_box):
            clipped = geom.intersection(nt_box)
            if not clipped.is_empty and clipped.area > 0:
                nt_geoms.append(clipped)
    hoppou_added = False
    if nt_geoms:
        hk_mask = japan["pref_jp"] == "北海道"
        if hk_mask.any():
            # .at[] 直代入はジオメトリ列を破壊するため list→再構築する
            geom_list = japan.geometry.tolist()
            hk_pos = int(hk_mask.values.argmax())
            geom_list[hk_pos] = unary_union([geom_list[hk_pos]] + nt_geoms)
            japan = gpd.GeoDataFrame(japan.drop(columns="geometry"),
                                     geometry=geom_list, crs=japan.crs)
            hoppou_added = True

    japan = japan.to_crs("EPSG:4326")
    return japan, hoppou_added


def assert_hoppou(japan, *, gpd_mod) -> float:
    """北海道の最東端経度を返し、北方領土欠落なら例外。"""
    hk = japan[japan["pref_jp"] == "北海道"]
    if hk.empty:
        raise DataFetchError(source="Natural Earth", url=NE10_URL,
                             kind="HOKKAIDO_MISSING", message="北海道が抽出できません")
    maxlon = float(hk.total_bounds[2])  # [minx,miny,maxx,maxy] の maxx
    if maxlon < HOKKAIDO_MAXLON_MIN:
        raise DataFetchError(
            source="Natural Earth", url=NE10_URL, kind="HOPPOU_MISSING",
            message=(f"北海道の最東端 {maxlon:.2f}°E < {HOKKAIDO_MAXLON_MIN}°E。"
                     "北方領土が統合されていません（このレシピの不可欠条件）。"))
    return maxlon


def write_manifest(japan, csv_path: Path) -> int:
    """都道府県マニフェスト CSV（最東端経度で降順）を書く。"""
    import csv as _csv
    recs = []
    for _, row in japan.iterrows():
        minx, miny, maxx, maxy = row.geometry.bounds
        recs.append({
            "area": row["pref_jp"], "max_lon": round(maxx, 4),
            "min_lon": round(minx, 4), "max_lat": round(maxy, 4),
            "min_lat": round(miny, 4),
            "parts": len(getattr(row.geometry, "geoms", [row.geometry])),
        })
    recs.sort(key=lambda r: r["max_lon"], reverse=True)
    with open(csv_path, "w", encoding="utf-8", newline="\n") as f:
        w = _csv.writer(f)
        w.writerow(["Rank", "Area", "Value", "MinLon", "MaxLat", "MinLat",
                    "Parts", "Unit"])
        for i, r in enumerate(recs, 1):
            w.writerow([i, r["area"], r["max_lon"], r["min_lon"], r["max_lat"],
                        r["min_lat"], r["parts"], "°E"])
    return len(recs)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="日本の都道府県境界取得（北方領土統合）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "naturalearth" / "ne10m_admin1")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    import geopandas as gpd
    try:
        shp = download_ne(args.cache_dir)
    except DataFetchError as e:
        logging.error("ダウンロード失敗: %s", e)
        return 1

    japan, hoppou_added = build_prefectures(shp)
    logging.info("都道府県数: %d / 北方領土統合: %s", len(japan), hoppou_added)

    # ★ 不可欠条件: 北方領土が北海道に含まれているか
    try:
        hk_maxlon = assert_hoppou(japan, gpd_mod=gpd)
    except DataFetchError as e:
        logging.error("検証失敗: %s", e)
        return 1
    logging.info("北海道 最東端: %.3f°E（北方領土含む）", hk_maxlon)

    today = datetime.now().strftime("%Y%m%d")
    gpkg = args.output_dir / "japan_prefectures.gpkg"
    csv_path = args.output_dir / f"{today}_japan_prefectures_manifest.csv"
    meta_path = args.output_dir / f"{today}_japan_prefectures_metadata.json"

    japan_out = japan[["pref_jp", "geometry"]].rename(columns={"pref_jp": "name"})
    japan_out.to_file(gpkg, driver="GPKG")
    n = write_manifest(japan, csv_path)

    meta = {
        "task_name": "japan_prefectures_with_hoppou",
        "source": {"name": "Natural Earth 10m admin-1 states/provinces",
                   "url": NE10_URL, "single_source": True},
        "crs": "EPSG:4326",
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "prefecture_count": n,
        "hoppou_integrated": hoppou_added,
        "hokkaido_max_lon": round(hk_maxlon, 4),
        "nt_bbox": NT_BBOX,
        "gpkg_sha256": sha256_of(gpkg),
        "csv_sha256": sha256_of(csv_path),
        "notes": ("北方4島はロシア(サハリン州)ポリゴンに含まれるため bbox で切り出し北海道へ統合。"
                  "得撫島(45.7°N〜)を除くため北限45.6°N。NE名はマクロン付きで join。"),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    logging.info("出力: %s / %s", gpkg.name, csv_path.name)

    print(f"\n== 日本 都道府県境界（北方領土統合）{n}面 ==")
    print(f"  GPKG: {gpkg}")
    print(f"  北海道 最東端: {hk_maxlon:.3f}°E（北方領土含む）")
    print("  最東端経度トップ5:")
    import csv as _csv
    with open(csv_path, encoding="utf-8") as f:
        for r in list(_csv.DictReader(f))[:5]:
            print(f"    {r['Rank']:>2}  {r['Area']:<6}  {r['Value']}°E")
    return 0


if __name__ == "__main__":
    sys.exit(main())
