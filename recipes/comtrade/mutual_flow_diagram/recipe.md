---
id: comtrade/mutual_flow_diagram
api: comtrade
task: 3地域/3か国 相互フロー図（往復ネスト曲線・階級凡例）
tags: [comtrade, mutual-flow, flow-diagram, triangular, nested-arrows, kyotsu, exam-figure, migration, tourism, mincho, gothic-symbol, matplotlib, no-auth]
summary: 3地域/3か国の相互の量（貿易額・移民送出数・観光客移動など）を、共通テスト風の体裁＝往復とも外側へ膨らむ平行なネスト曲線＋4段階の階級凡例で描く確定レシピ。作図は lib/mutual_flow.py に集約、データ差し替えで再利用。
items: [png, pdf]
verified_at: 2026-08-04
complexity: medium
auth_required: false
gotcha_count: 8
pattern: parallel-nested-outward-arcs + measured-arc3-sign + width-aware-nesting + midpoint-paired-labels + gothic-symbol-mincho-text + class-arrow-legend + docx-embedded-verify
lib: ../../../scripts/lib/mutual_flow.py
reference_impl: (非公開)
reference_only: true
---

# comtrade / mutual_flow_diagram

## 何をする
**3地域/3か国の相互フロー図**を作る。どの向きが最大かで記号を判別させる共テの出題の器。
- 頂点＝記号（ナ/ニ/ヌ 等）、辺ごとに**往復2本の矢印**、太さ＝**4段階の階級**、右に枠囲みの階級凡例。
- **貿易額・移民の送出数・観光客の移動**など「相互の量」なら何でも。データを差し替えるだけ。

★体裁＝往復とも外側へ膨らむ平行なネスト曲線（近年の共通テストの相互フロー図の形）。貿易額・移民送出数の図でこの形を確認済。観光の相互矢印図は実例を確認していない。旧様式＝直線ブロック矢印。

## 再現の合言葉（形の語彙）
| 呼び方 | 形 | 正誤 |
|---|---|---|
| **平行ネスト（外向き）** | 往復2本を同じ側（三角の外）へ平行に重ね、向きだけ逆。外弧が図の外形を決め内弧をネスト | ✅ 共テの正解（既定） |
| 木の葉／レンズ | 往復2本が互いに反対へ膨らむ目玉形 | ❌ 誤り（作らない） |
| 直線ブロック | 太い直線矢印 | 旧様式（2012） |
→ 依頼は「**フロー図、平行ネストで**」で本レシピを即再現。「木の葉」は不可の合図。

## データ出典（貿易の場合）
- **貿易額**: UN Comtrade 2022年。cookbook `comtrade/region_trade_matrix` の出力の3地域分。
  ★見本に使った値（2026-06-13 の出力）は**旧い定義**（西アジア14・アフリカ20・ヨーロッパ20か国。metadata の `regions` で確認）で、
  地域全体の値ではない。いまの region_trade_matrix は M49 の全部の国で取る（範囲は metadata の `scope`）。
  図に実額を載せるなら、取り直した値を使い、図の注記に範囲を書く。
- **仕様（向きと額の分離）**: 矢印の**向き＝輸出方向**（隣の輸出品目図と統一）。**額＝相手国＝輸入国の輸入統計（原産国ベース）** を採用＝香港等の中継貿易を原産国で捕捉（日中の香港経由と同じ）。輸出側集計はインド欠落・500件上限で不完全（`../../docs/api_notes/inter_regional_trade.md`）。
- 移民は同図なら「移民の送出数（千人）」、観光は「観光客数」等に置換。

## 使い方（lib を呼ぶだけ）
```python
from lib.mutual_flow import load_fonts, triangle_nodes, klass, draw_flows, draw_symbols, flow_legend
GOTHIC, MINCHO = load_fonts()                       # 記号=ゴシック / 数字・凡例・注記=明朝
V = triangle_nodes(["ナ", "ニ", "ヌ"])              # 上・左下・右下
MS = [6, 11, 17, 24]                                # 4階級の太さ
CLASSES = [(0,"60未満"),(60,"60〜100"),(100,"100〜200"),(200,"200以上")]
flows = [(s, d, MS[klass(v, CLASSES)], f"{v}") for s, d, v in raw]   # 実数版=数字, 指数版=None
draw_flows(ax, V, flows, mincho=MINCHO)             # rad=0.19 既定（原図に最も近い）
draw_symbols(ax, V, GOTHIC)                         # box=True で原図の枠つきに
flow_legend(ax, 0.80,0.20,0.185,0.66, list(zip(MS,[c[1] for c in CLASSES])), MINCHO, "貿易額（十億ドル）")
```
実体を再実行: `python region_trade_flow_p000/scripts/make_flow.py`（指数版＋実数版）。膨らみ比較は `FLOW_RAD=0.14 FLOW_OUTDIR=/tmp/x python scripts/make_flow.py`。

## ★ハマり所（実測で確定＝二度取り違えた）
1. **平行ネスト≠木の葉**: 往復2本は「同じ側（外）へ平行」で向きだけ逆。互いに反対へ膨らませる（レンズ）は誤り。ここを2回間違え、180°取り違えた。
2. **arc3の符号は推測せず実測**: 外向き（`outward=mid−centroid`）に膨らませる符号は matplotlib の規約を推測で決めると逆になる。描画して外向きか確認し、確定値 `SIGN=-1` を掛ける。
3. **ネストは幅考慮**（`off=基準+ms*HW`）: 固定offだと太い矢印の**矢じり**が隣の細い弧に接触（指数版の下辺で発生）。太い弧ほど外へ逃がす。
4. **矢じりは控えめ**（head_width≈1.15）: 大きいと隣弧に被る。
5. **数字は各弧の中点・ペア配置**（外弧→外側/内弧→中央側）。先端寄せ・中央に浮かせると「散らかる」。外弧数字が下部注記と衝突しないよう三角をやや上げる（`triangle_nodes` 既定 y_bottom=0.36）。
6. **フォント＝共テ様式**: 記号（ナ/ニ/ヌ）だけゴシック、**数字・凡例・注記は明朝（BIZ UDMincho・.ttf/glyf＝完成ゲート適合）**。ゴシック一辺倒は共テ体裁から外れる。
7. **体裁はPDF縮小目視で決めない**: `.doc`→PDF変換の目視で「直線」と誤読した。**元 `.docx` の埋め込み画像（`unzip word/media/*.tif`→sipsでPNG）を直接見て**曲線・体裁を確定する。
8. **向きと額を分離**: 「向き＝輸出／額＝原産国ベースの輸入統計」（上記仕様）。混同しない。

## テーマ別の確認状況
- 貿易・移民＝この形の図を確認済。**観光＝相互矢印図の実例は未確認**（受入/送出の表・散布図はある）。
