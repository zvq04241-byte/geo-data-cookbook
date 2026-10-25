---
id: hydrosheds/world_basin_erosion_map
api: hydrosheds
task: ウィンケル世界主題図（主要河川流域＋内陸/無河流域＋比例円）
tags: [hydrosheds, hydrobasins, naturalearth, winkel-tripel, world-map, thematic-map, proportional-circle, drainage, endorheic, arheic, erosion, exam-figure, gis, no-auth]
summary: HydroSHEDS HydroBASINS と Natural Earth から、ウィンケル図法の世界主題図（河川流域＋内陸流域＋無河流域の網掛け＋侵食速度などの比例円）を作る確定レシピ。
items: [png, pdf, geojson_basins, geojson_drainage]
verified_at: 2026-06-15
complexity: hard
auth_required: false
gotcha_count: 11
pattern: hydrobasins-endo-classify + interior-point-basin-match + winkel-graticule-frame + proportional-circle-tangent-legend + zone-dict-color-sync
reference_impl: ../../../../river_erosion_p000   # 実体（再実行可能な確定レシピ）。data群直下の river_erosion_p000
---

# hydrosheds / world_basin_erosion_map

## 何をする
**ウィンケル・トリペル図法の世界主題図**を作る。中身:
- 主要河川の**流域ポリゴン（HydroBASINS）を網掛け**＋**流路（Natural Earth rivers の青線）**
- **内陸流域・無河流域の2区分網掛け**（貝塚1997の再現）
- 河口（または海洋上）に**比例円**（面積∝値・半径∝√値）＝侵食速度など任意の量
- **経緯線入りの地球図・国境なし（海岸線のみ）**、接線入り入れ子円の凡例
共通テスト/教科書地図風の体裁。

★ 地理空間系は「ローカルLLMがゼロ生成」でなく「**この確定レシピを再利用**」が原則。
   値・河川・配色を差し替えて再実行、が想定運用（[[local_llm_recipe_capability]]）。

## データ出典（単一でなく複合）
- **流域**: HydroSHEDS HydroBASINS v1c lev04（地域別zip, 自動DL）`https://data.hydrosheds.org/file/hydrobasins/standard/hybas_{r}_lev04_v1c.zip`（r= af/as/eu/na/sa/si/au …）
- **海岸線**: Natural Earth 50m admin0（countries を dissolve）／**流路**: NE 50m rivers_lake_centerlines／**湖**: NE 50m lakes
- **侵食速度の値**: Milliman & Farnsworth(2011), Milliman & Meade(1983)（比堆積量 t/km²・年）※任意の量に差替可
- 認証: 全て不要

## 使い方（reference_impl を再実行）
```bash
PY=python
$PY river_erosion_p000/scripts/fetch_basins.py     # 河川流域抽出 → geojson（17流域）
$PY river_erosion_p000/scripts/fetch_drainage.py   # 内陸/無河流域抽出 → geojson（2区分）
$PY river_erosion_p000/scripts/make_erosion_map.py            # 図（png/pdf, ラベルあり）
NOLABEL=1 $PY river_erosion_p000/scripts/make_erosion_map.py  # ラベルなし版（作問で記号を後付け）
$PY river_erosion_p000/scripts/make_excel.py       # Excel＋metadata＋検証ログ
```
差替ポイント: `data/processed/*_river_erosion.csv`（河川名・座標・値）、`RIVERS`（fetch_basins の流域シード内部点）、`CFG`（ラベル配置）、`ZONE`（配色）。

## ★ハマり所（ローカルLLMが独力では当てられない＝レシピの価値）
1. **ウィンケル枠が閉じない＝「北極が切れる」**: 経線は緯度±88まで `range(-88,89,2)`、**緯線に両端±88を必ず入れる** `(-88,-80,…,80,88)`。これが楕円の上下枠の閉じ線。内容クリップではなく閉じ線欠落が原因。
2. **HydroBASINSのカスピ海罠**: カスピ海岸は `COAST=1` 扱いで **ヴォルガ/カスピ海流域が `ENDO=0`**＝カスピ海流域（大きな内陸流域）が ENDO フィルタから漏れる。注ぐ河川をシード点で別途抽出して内陸流域に追加する。
   ★**シード点は、その点を含む地域ファイルで引く。** カスピ海の南岸・西岸・東岸（クラ川・イラン側・東岸）は `as` でなく **`eu`** のファイルに入る。
   地域を誤ると `contains` が0件になり、**黙って落ちる**。実体の `fetch_drainage.py` は6点中3点（`("as",46,41)` `("as",50,37)` `("as",54,40)`）がこれで落ち、
   ヴォルガ・ウラル・テレク側の3水系だけで作られている（2026-10-26 実測: 3点で約155万km²、6点を `eu` で引くと約182万km²。HydroBASINS lev04 の MAIN_BAS 単位・モルワイデ図法で面積計算。点(46,41)＝クラ川流域は内陸流域に入っていない）。
   **当たった点の数＝シード点の数を assert する**（外れた点の座標を出して止める）。
3. **流域マッチは河口でなく内部点**: 河口座標で `contains` すると微小な沿岸サブ流域にマッチ（アマゾンが3.7万km²等）。**本流の中流域の内部点**で引き、MAIN_BAS で `unary_union`。（アマゾンの値は 2026-10-26 に実測: lev04 `sa` で点(-50,0)を含むサブ流域＝約3.7万km²。モルワイデ図法で面積計算）
4. **内陸/無河の2分**: HydroBASINS `ENDO>0` を MAIN_BAS で束ね→**終端湖の有無**で内陸（湖あり: カスピ/アラル/バルハシ/タリム/チャド/エア/アルティプラノ）/無河（湖なし: サハラ/アラビア/豪州内陸）。湖=NE50m lakes(>800km²)＋**カスピ海は手動ポリゴン補完**（NEは海洋扱いで欠落）。★800km²未満の終端湖しか持たない内陸流域は「無河」に入る。該当する流域があるかは確かめていない。
5. **dissolve/unary_union後は `make_valid` 必須**: is_valid=False が河川流域・ゾーンで発生（描画は通るがデータ不正）。
6. **濃淡は `ZONE` 辞書1箇所**に定義し地図plotと凡例swatchの両方で参照。別々にハードコードすると凡例だけ直して地図が古いままになる。配色は薄→濃で 無河<内陸<**河川流域(最濃)**、全レイヤー不透明・黒縁。
7. **比例円は河口でなく引出線の先（海洋上）**に置き河口は小●、引出線は円の縁で止める（流域・流路を隠さない）。凡例は**接線入り入れ子円**（下端そろえ・上端から水平接線→値）。`prop_radius(v, vmax)` の `vmax` は**図に描く値の最大**を渡す（実体は `max(値)`）。凡例と地図で同じ `vmax` を使う。
8. **ラベル衝突**: 河口に円を置く型は `dist = rr + 半幅|ux| + 半高|uy| + 0.42e6`（実体の図＝ラベル8〜9.5pt・この図幅で決めた余白。フォントや図幅を変えたら測り直す）。凡例は**地図枠の外でなくオーバル内の空き海域**＝南太平洋 `xy(-172,-50)` 起点（南米南端と被らせない）。
9. **データ整理**: ガンジス・ブラマプトラは合流前で同一流域＝統合。マッケンジーはHydroBASINS地域区分にまたがり除外（低侵食の例はシベリア河川で代替）。**総流域 vs 有効流域**（ニジェール総2.1M/有効1.27M, 黄河総0.97M/有効0.75M）の面積差は注記。
11. **範囲を図に書く**: 河川は手で選んだ**主要17河川**（`data/processed/*_river_erosion.csv` の17行。全河川ではない）。
   図の注記と metadata のキー `scope` に「主要17河川（選定）。マッケンジーは除外、ガンジス・ブラマプトラは1流域に統合」と書く。
   「無河流域」は**HydroBASINS の ENDO（外洋に流出しない）で終端湖の無いもの**で、乾燥度で定めた無河地域より狭い。凡例か注記にそう書く。
   ★実体（river_erosion_p000）の図の注記・metadata には、2026-10-26 時点でこの範囲が書かれていない。
10. **和文フォント**: `²` が豆腐化する Hiragino CFF を避け、**IPAexGothic（font_setup.py）**を使う。検証は LibreOffice/PyMuPDF で PDF を領域クロップ→目視（上端・凡例・各大陸を別々に）。

## この図で読めること・読めないこと
- 読める: 流域の広さと侵食速度の大小が一致しないこと／高地を源流にもつ河川で値が大きいこと／ヴォルガがカスピ海に注ぐ内陸河川であること（実体はヴォルガ流域を内陸流域の色で塗る。ハマり所2のシード漏れを直さないと、カスピ海流域の南側・東側は欠ける）。
- 弱い: 乾燥地を流れ抜ける河川（外来河川）の描写。本図の無河流域は**厳密な内陸性(ENDO)**で、乾燥度で定めた無河地域より狭い。
  乾燥度で揃えたいときは、無河を**乾燥度マスク(BW/乾燥指数)**で再定義する（拡張候補）。

関連: [[wintri_map_cartography]]（メモリ） / naturalearth/japan_prefectures / docx/kyotsu_exam_layout
