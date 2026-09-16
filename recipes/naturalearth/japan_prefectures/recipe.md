---
id: naturalearth/japan_prefectures
api: naturalearth
task: 日本の都道府県境界（北方領土を北海道に統合）
tags: [naturalearth, boundary, geopackage, japan, prefecture, choropleth-base, gis, hoppou, no-auth]
summary: Natural Earth 10m admin-1 から47都道府県ポリゴンを取得し、北方4島をロシアから切り出して北海道に統合した GPKG を出力
items: [gpkg, manifest_csv]
verified_at: 2026-06-08
complexity: medium
auth_required: false
gotcha_count: 8
pattern: bulk-zip-shapefile + bbox-clip-territory-reassign + geopackage-output
---

# naturalearth / japan_prefectures

## 何をする
Natural Earth 10m admin-1 から日本の**47都道府県ポリゴン**を取得し、
**北方4島（択捉・国後・色丹・歯舞）をロシア(サハリン州)ポリゴンから切り出して北海道に統合**した
GeoPackage を出力する。検証用に「最東端経度マニフェスト CSV」も併産する。

★ 本レシピは保存ルール「**日本地図は北方領土を必ず含める**」の実装基準。
   北海道の最東端経度が 147.5°E 未満（=北方領土欠落）なら fetch.py が**例外で停止**する。

## API情報
- **出典**: Natural Earth 10m Cultural admin-1 states/provinces
- **URL**: `https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip`
- **認証**: 不要
- **形式**: zip 内 ESRI shapefile（geopandas/pyogrio で読む）
- **CRS**: EPSG:4326（出力で明示固定）
- **依存**: geopandas / shapely / pyproj / pyogrio

## 使い方
```bash
python fetch.py --output-dir ./output
```
出力:
- `output/japan_prefectures.gpkg` … 47都道府県ポリゴン（name 列＝日本語県名, EPSG:4326）
- `output/YYYYMMDD_japan_prefectures_manifest.csv` … 県別 最東端/最西端経度・緯度（max_lon 降順）
- `output/..._metadata.json` … 出典/SHA256/北方領土統合フラグ/北海道max_lon

## ハマり所（重要）

### 1. 北方4島はロシア(サハリン州)ポリゴンに含まれる（最重要）
Natural Earth では北方4島は **Japan でなく Russia の admin レコード**に入っている。
そのまま `admin=='Japan'` を取ると北方領土が欠落する。
**bbox `(145.0, 43.0, 149.5, 45.6)` で Russia ジオメトリから切り出し**、北海道に `unary_union` で統合する。

### 2. bbox 北限は 45.6°N（得撫島を除外）
得撫島（ウルップ島, 45.7°N〜）は日本領でない。北限を **45.6°N** にして択捉島まで（得撫以北を除く）。
東限 149.5°E は択捉島東端（≈148.8°E）を確実に含む余裕値。

### 3. NE の name はマクロン付き
join キーの NE `name` は **`Hokkaidō` / `Kyōto` / `Ōsaka` / `Hyōgo` / `Ōita` / `Kōchi`** など長音符付き。
ASCII で書くと一致しない。`NE_NAME_TO_JP` で完全一致 join、漏れは `name_local` フォールバック。

### 4. ジオメトリ更新は list→再構築（.at[] 直代入は破壊的）
GeoDataFrame のジオメトリ列に `gdf.at[i, 'geometry'] = ...` で直代入すると列が壊れることがある。
**`gdf.geometry.tolist()` で list 化 → 該当要素を差し替え → `GeoDataFrame(..., geometry=list)` で再構築**する。

### 5. 自己検証で北方領土欠落を機械検出
`assert_hoppou()` が北海道の `total_bounds[2]`（max_lon）を見て **147.5°E 未満なら例外**。
北方領土込みなら ≈148.8°E、根室どまりなら ≈145.8°E。これで「うっかり欠落」を CI 的に止める。

### 6. 東京都の最東端は南鳥島 153.99°E
NE 10m は南鳥島（東京都）を含むため、最東端マニフェストの 1位は東京都(153.99°E)、2位が北海道(北方領土)。
「日本最東端＝北方領土」と誤解しない（最東端は南鳥島）。

### 7. CRS は明示的に EPSG:4326 へ
元データは 4326 だが、統合後に `to_crs('EPSG:4326')` で明示固定する。
下流の描画・面積計算で CRS 不定を避ける。

### 8. 出力は GPKG（境界本体）＋検証用 CSV の二本立て
境界の実体は GeoPackage。CSV は採点・点検用のマニフェスト（県別の経度緯度レンジ）。
地図描画や統計結合は各プロジェクト側で GPKG を読んで行う（本レシピは境界供給に専念）。

## 効くケース
- 都道府県コロプレス地図のベース境界（北方領土込み）
- 県別の bbox/範囲メタの取得
- 統計値を県名 `name` で結合する土台

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 市区町村境界 | `mlit/n03_municipal_boundary`（MLIT N03） | 未作成 |
| 高精度な海岸線 | 国土地理院ベクトルタイル等 | 未作成 |
| 統計値結合済みの地図 | 各プロジェクトで GPKG + データ結合 | 範囲外 |
| 離島の精密形状 | より高解像度のソース | 範囲外 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数・キャッシュは Path.home()/.cache）
- ✅ 出力 CSV/JSON は `encoding="utf-8"`、CSVは `newline="\n"`
- ✅ 構造化例外 `DataFetchError`（source/url/kind）＋ **不可欠条件の self-assert**
- ✅ ダウンロード3回リトライ、zip 展開キャッシュ
- ✅ metadata.json に source URL / GPKG・CSV SHA256 / 北方領土統合フラグ / 北海道max_lon
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）
- ✅ APIキー不要

## このレシピを使うLLMへのヒント
1. **日本地図は北方領土を必ず含める**。NE/多くの世界データは北方領土を Russia 側に持つので bbox 切り出し統合が要る
2. **境界データは非ランキング**でも、`max_lon` 等のマニフェスト CSV を併産すれば validate_output に乗る
3. **不可欠条件は fetch.py に self-assert**（例外）で焼き込む → smoke_test の実行成功判定で自動的にゲートになる
4. **ジオメトリ列の更新は list 再構築**、join キーの**表記揺れ（マクロン）**に注意
