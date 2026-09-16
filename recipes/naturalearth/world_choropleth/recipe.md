---
id: naturalearth/world_choropleth
api: naturalearth
task: 国レベル階級区分図（コロプレス）の描画
items: [png, pdf, svg, metadata_json]
tags: [naturalearth, choropleth, render, map, classification, quantile, plate-carree, no-auth]
summary: Natural Earth 50m admin_0 を境界に CSV（国コード+値）を結合し、N分位で階級分類してPNG+PDF（日本語安全）を出力する描画レシピ
verified_at: 2026-06-24
complexity: medium
auth_required: false
gotcha_count: 5
pattern: ne50m-admin0 + csv-join + quantile-classify + platecarree-render + svg2pdf
---

# naturalearth / world_choropleth

## 何をする
国レベルの**階級区分図（コロプレス）を「描画」する**確定レシピ。
`estat/prefecture_classify`（分類→CSV）や `naturalearth/japan_prefectures`（境界供給）が
範囲外としていた「**描画部**」（投影・配色・凡例・PNG/PDF出力）を一手に引き受ける。

入力 CSV（国コード列＋値列）と切り出し bbox を渡すと、Natural Earth 50m admin_0 に結合し、
N分位で階級化して PNG + PDF + SVG + metadata.json を出力する。

★ この描画部を毎回ゼロから書くと、図法・PDF文字化け・国の欠落で必ず失敗する（EU難民地図・欧州外国人地図で実証）。
   本レシピはその**3つの確定パターンをコード化**したもの。

## API情報
- **出典**: Natural Earth 50m Cultural admin_0 countries
- **URL**: `https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip`
- **認証**: 不要
- **依存**: geopandas / shapely / matplotlib / pandas、PDF化に **Inkscape**（任意）

## 使い方
```bash
python render.py \
    --csv data.csv --code-col geo --value-col share_pct --code-kind iso_a2 \
    --classify-n 3 --bbox -30 50 34 75 \
    --title "ヨーロッパ：就業者に占める外国生まれ割合（2025年）" \
    --unit "%" --source "出典: Eurostat LFS 2025年" \
    --output-dir ./output --basename 20260624_europe_workshare
```

### 主要フラグ
| フラグ | 意味 |
|---|---|
| `--csv` | 国コード列＋値列を含むCSV（必須） |
| `--code-col` / `--value-col` | コード列名／値列名（必須） |
| `--code-kind` | `iso_a2`（2文字）／`name`（英語国名）／`auto`（既定: 長さで判定） |
| `--classify-n` | 階級数（既定3。3なら青→黄→赤、N>3は RdYlBu を等分） |
| `--bbox` | 切り出し範囲 `西 東 南 北`（経度・緯度） |
| `--title` / `--unit` / `--source` | タイトル／凡例単位／出典注記 |

出力: `<basename>.png`（300dpi）/ `.svg` / `.pdf`（Inkscapeがあれば）/ `_metadata.json`（境界・SHA256・未結合コード）

## ハマり所（重要）

### 1. 図法は正方形図法（PlateCarree＝投影なし matplotlib 直描き）
階級区分図には**正方形図法**で十分かつ最適。Albers/Lambert/EqualEarth を試すと、cartopy の
`transform` 適用で色が出ない・国土形状に色が合わない等で必ず迷走する（実証済み）。
`fig, ax = plt.subplots()` で投影なしに `gdf.plot()`、範囲は `set_xlim/set_ylim` で決める。
**面積比も保たれ、地図帳の標準座標と一致して直感的。**

### 2. PDFは matplotlib 直書きでなく SVG → Inkscape 変換
matplotlib の `savefig(pdf)` / `PdfPages` は**日本語が文字化けする**（フォント埋め込みが不確実）。
SVG は `fontproperties` を正しく保持するので、`savefig(svg)` → `inkscape svg -o pdf` が確実。
Inkscape 不在環境では PDF をスキップし SVG を配布（本スクリプトは自動フォールバック）。

### 3. 国の切り出しは centroid フィルタ禁止、xlim/ylim で
`gdf[gdf.centroid.x >= W & ...]` で絞ると、**重心が範囲外の国（北アフリカ等）が領土ごと消える**。
全ジオメトリを描画し、表示範囲は `set_xlim/set_ylim` だけで決めること。
（おまけ: geographic CRS の centroid は警告も出る＝そもそも非推奨操作）

### 4. Natural Earth は仏・諾で ISO_A2="-99"（欠番）
**France / Norway** などは `ISO_A2` が `-99`。正しい2文字コードは `ISO_A2_EH` 列にある。
`ISO_A2=='-99'` の行だけ `ISO_A2_EH` で補完してから結合する（本スクリプト実装済み）。
これを怠ると仏・諾が「データなし＝灰色」になり、**黙って欠落**する。

### 5. 非ISO地理コードの補正（Eurostat等）
Eurostat は **ギリシャ=EL / 英国=UK** と ISO とずれる。`GEO_FIXUP = {EL:GR, UK:GB}` で吸収。
結合後は「未結合コード」を必ず print＋metadata に記録し、**欠落を黙認しない**。

### 6. 凡例は「空いた隅を探して置く」。固定位置も固定の凡例帯もどちらも駄目
`ax.legend(loc="upper left")` と決め打ちすると、bbox やデータによって陸地に
かかり、**毎回手で直すことになる**（利用者の恒常的な不満だった）。

では gridspec で凡例帯を常時確保すればよいかというと、それも駄目だった。
2026-09-05 に実際にそうしてみたところ、**凡例が小さい図でも帯のぶん地図が縮み、
重なっていない図まで一律に劣化した**。重なりは時々しか起きないので、常時
コストを払う設計は割に合わない。

確定形は `lib.world_map.place_legend()`:
1. 四隅を順に試し、凡例の矩形を**データ座標に変換してシェープリーで当たり判定**
   （軸の矩形ではなく、塗ったポリゴンそのものと照合する）
2. 当たらない隅が見つかればそこに置く＝従来どおりの見た目
3. どの隅も当たるときだけ凡例軸へ逃がし、`fit_legend_axis()` で帯を実寸に詰める

検証: 欧州図（bbox -30 50 34 75）は `upper left`、隅まで陸で埋まる
bbox -5 25 35 55 では `outside` に自動で切り替わることを確認。

★教訓は「予防が検出に勝つ」ではない。**予防のコストが常時かかるなら、
  検出して自動で直す方がよい**。人が手で直さずに済むことが目的で、
  重なりを構造的に不可能にすること自体が目的ではない。

## 効くケース
- 世界/地域の国別統計コロプレス（Eurostat・World Bank・OWID・UN等の国コード付きCSV）
- 分位/等量階級の階級区分図（教材の「3階級に分けよ」系）

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 |
|---|---|
| 日本の都道府県コロプレス | `naturalearth/japan_prefectures`（境界）＋`estat/prefecture_classify`（分類） |
| 市区町村コロプレス | `mlit/n03_municipal_boundary` |
| 等値線/ラスタ気候図 | `noaa_psl/*`・`cams/*` |
| 比例円・流線図 | `hydrosheds/world_basin_erosion_map` 等の作図系 |

## 規約準拠状況
- ✅ パスは `Path(__file__)`／CLI引数基点、出力は `encoding="utf-8"`
- ✅ 構造化例外 `RenderError(kind=...)`、Natural Earth は3回リトライ
- ✅ metadata.json に source URL / PNG・SVG・PDF SHA256 / 分類境界 / **未結合コード**
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`
- ✅ 認証不要

## このレシピを使うLLMへのヒント
1. **図法で悩むな**＝正方形図法（PlateCarree）一択。複雑な投影は教材では逆効果。
2. **PDFは必ず SVG 経由**。matplotlib 直 PDF は日本語が化ける。
3. **国を消すな**＝centroid で絞らず xlim/ylim。結合の未一致は必ず報告。
4. データ取得（分類前のCSV）は各データ源レシピ（eurostat/world_bank/owid…）で。本レシピは描画専任。
