---
id: gsi_dem/relief_map
api: gsi_dem
task: 地理院DEMタイルから段彩陰影図（カラー/白黒）を作る
items: [DEMタイル取得, 段彩陰影, 道路/登山道重畳, 地点ラベル, 縮尺/方位]
tags: [gsi, dem, hillshade, relief, volcano, mono, exam]
summary: 地理院 標高タイル(dem_png)→numpy標高格子→色を保持する手動ブレンドの段彩陰影図。共テ図版用のカラー版/白黒印刷版を同一スクリプトで出力
pattern: dem_png-decode + hillshade-manual-blend + official-elevation-labels
auth_required: false
verified_at: 2026-07-03
complexity: medium
gotcha_count: 7
---

# gsi_dem / relief_map

## 何をする
地理院の標高タイル `dem_png`（z14≒10m相当）を取得して numpy 標高格子にし、
段彩＋陰影（hillshade）の地形図を描く。道路・登山道（OSM）や地点を重ね、
共テ体裁の図版（カラー版＋白黒印刷版）を出力する。

**参照実装**: (非公開)
- `_dem_fetch.py` … タイル取得→`data/raw/gsi_dem/` 保存
- `make_q2_relief.py` … 段彩陰影＋道路/登山道＋地点＋噴石範囲（御嶽山）

## ★ハマり所（全て実際に踏んだ）

1. **dem_png のデコード式**: `x = R*65536 + G*256 + B`。`x == 2**23` は**無効値(NaN)**、
   `x > 2**23` は `x - 2**24`（負値）。最後に **×0.01 でメートル**。この3点を外すと標高が壊れる。
2. **名前のある地点にDEM生値を使わない**: 山頂等の標高ラベルは**公式値で固定**する
   （御嶽山剣ヶ峰=3067m 一等三角点。DEM生値をずれた画素で拾い3046mと誤記した事故が起源）。
   `lib.verify.assert_official(dem値, 公式値, tol=30)` で照合ゲートを入れる。
3. **陰影で谷が白飛びする**: `LightSource.shade(blend_mode='soft')` は平坦部が白くなり
   「地図が切れて見える」。**手動ブレンド**にする:
   `rgb = cmap(norm)[...,:3] * (0.55 + 0.45*hillshade)[...,None]`（明るさ下限55%で色を保持）。
4. **キャンバスは地図の縦横比に合わせる**: 等アスペクトのまま横長 figsize に描くと上下が切れる。
   `aspect=(y1-y0)/(x1-x0)` から figsize を計算し `add_axes` で配置（参照実装参照）。
5. **表示範囲ぶんのDEMを取ってから描く**: 表示範囲がDEM範囲より広いと下端に空白帯が出て
   「図郭と合わない」。先に bbox を確定して取得する。
6. **ラベルは引き出し線で余白へ**: 地点名を地図上に直置きすると地形と重なる。
   `annotate(..., arrowprops=dict(arrowstyle='-'), bbox=白)` ＋ `annotation_clip=False`。
7. **スクラッチに置いた生データは本番化時に data/raw/ へ移す**: 完成ゲート
   （`lib/verify.py`）が scripts 内の `/tmp`・scratchpad 参照を落とす。

## 出典表記
「国土地理院 数値標高モデル(DEM10m)・道路データ(OpenStreetMap)により作成。」＋
公式標高の典拠（一等三角点等）。PNGには `lib.verify.embed_png_meta` で出典・生成時刻を埋め込む。

## このレシピを使うLLMへのヒント
- まず参照実装の `_dem_fetch.py` と `make_q2_relief.py` をコピーして bbox・地点だけ差し替える。
  デコード式・ブレンド式を自前で書き直さない（1.と3.を必ず外す）。
- 白黒版はカラーマップをグレー系に差し替えるだけで同一スクリプトから出す（`build(mono)` パターン）。
