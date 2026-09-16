---
id: mlit/n03_municipal_boundary
api: mlit
task: 市区町村境界（国土数値情報 N03, 都道府県単位）
tags: [mlit, n03, ksj, boundary, geopackage, japan, municipality, choropleth-base, gis, cp932, no-auth]
summary: 国土数値情報 N03 から指定都道府県の市区町村ポリゴンを取得し muni_code で dissolve した GPKG を出力
items: [gpkg, manifest_csv]
verified_at: 2026-06-08
complexity: medium
auth_required: false
gotcha_count: 8
pattern: bulk-zip-shapefile + cp932 + dissolve-by-code + equal-area-measure
---

# mlit / n03_municipal_boundary

## 何をする
国土数値情報 行政区域データ N03 から、指定**都道府県（pref_code 単位）**の市区町村ポリゴンを取得し、
行政コード(`N03_007`)で dissolve した GeoPackage を出力する。検証用に面積降順マニフェスト CSV も併産。

## API情報
- **出典**: 国土数値情報 行政区域 N03（国土交通省）
- **URL**: `https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-<year>/N03-<date>_<pref>_GML.zip`
- **認証**: 不要
- **形式**: zip 内 ESRI shapefile（**属性は cp932**）
- **CRS**: EPSG:4326（出力で固定）
- **依存**: geopandas / shapely / pyogrio

## 使い方
```bash
# 新潟県(15) 2020年版
python fetch.py --pref-code 15 --year 2020 --output-dir ./output
# 東京都
python fetch.py --pref-code 13 --year 2020 --output-dir ./output
```
出力: `output/n03_municipal_<pref>_<year>.gpkg`（muni_code/PREF_NAME/CITY_NAME/geometry）
＋ `..._manifest.csv`（面積km²降順）＋ metadata.json。GPKG は `~/.cache/n03/` にキャッシュ。

## ハマり所（重要）

### 1. 属性のエンコーディングは cp932（最重要）
N03 shapefile の dbf 属性は **cp932（Shift-JIS系）**。`gpd.read_file(..., encoding="cp932")` で読む。
utf-8 で読むと市区町村名が文字化けし、`CITY_NAME` が全滅する。

### 2. URL の日付は年により異なる
`N03-<year>/N03-<date>_<pref>_GML.zip` の `<date>` は公開年で変わる（多くは `<year>0101`）。
`MLIT_DATES` で対応。年を変えるときは MLIT 配布ページで実 URL を確認する。

### 3. 1市区町村が複数ポリゴン行に分割されている → dissolve 必須
N03 は島嶼・飛び地で 1 行政区が複数行に分かれる。**`N03_007`(行政コード)で dissolve** して 1市区町村=1フィーチャに集約する。dissolve しないと同一市が重複する。

### 4. 行政コードは5桁・不正行を除外
`muni_code` は5桁。`zfill(5)` で桁合わせし、**`^\d{5}$` に合致しない行（所属未定地など）を除外**する。

### 5. 政令指定都市は区ごとに別コード
政令市は**区ごとに muni_code**（例: 新潟市は8区=8件、コード 151xx）。
「市の数」と「N03 のフィーチャ数」は一致しない（新潟県は30市区町村だが N03 は37件＝区を含む）。
市単位で集計したい場合は別途 N03_003(市名)で再集約する。

### 6. 不正ジオメトリは make_valid で修復
原データに自己交差・不正リングが混じることがある。dissolve 前に **`shapely.make_valid`** を全ジオメトリに適用しないと、dissolve/面積計算で落ちる。

### 7. 面積は地理座標のままでは測れない
EPSG:4326（度）の `.area` は無意味。**equal-area 投影（本レシピは EPSG:6933）に変換してから km²** を算出する。

### 8. 取得は都道府県単位（全国は重い）
1リクエスト=1都道府県。全国はこのレシピを47回ループ（北海道の zip は特に大きい）。GPKG キャッシュで再取得を避ける。

## 効くケース
- 都道府県コロプレス（市区町村粒度）のベース境界
- 市区町村面積ランキング・bbox メタ
- e-Stat 等の市区町村統計を `muni_code` で結合する土台

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 都道府県境界（47面） | `naturalearth/japan_prefectures` | 実装済 |
| 政令市を市単位に集約 | N03_003 で再 dissolve する拡張 | 未実装 |
| 全国一括 GPKG | 47県ループの上位ラッパー | 未作成 |
| 統計値結合済みの地図 | 各プロジェクトで GPKG + データ結合 | 範囲外 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数・キャッシュは Path.home()/.cache）
- ✅ 出力 CSV/JSON は `encoding="utf-8"`、CSVは `newline="\n"`（**入力 shapefile は cp932**）
- ✅ 構造化例外 `DataFetchError`（source/url/kind）＋ 0件/コード不一致の自己検証
- ✅ ダウンロード3回リトライ、GPKG キャッシュ
- ✅ metadata.json に source URL / GPKG・CSV SHA256 / 市区町村数
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）
- ✅ APIキー不要

## このレシピを使うLLMへのヒント
1. **日本の公的 GIS shapefile は cp932** が基本。`encoding="cp932"` を忘れると文字化けで静かに壊れる
2. **行政コードで dissolve**（島嶼分割を集約）、**5桁でない行を除外**
3. **面積は equal-area 投影**してから測る。4326 の度数面積は使わない
4. **政令市は区単位**でフィーチャ化される（市数≠フィーチャ数）。境界は muni_code が真の鍵
