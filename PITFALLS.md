# 出所を問わず効く罠

43本のレシピに **278件**のハマり所が書いてある。だがそれは、そのレシピを
開かないと出てこない。**新しい出所に当たる前に読むもの**がここにある。

選んだ基準は「**3つ以上の別々の出所で、同じ形で踏んだもの**」。
1つの出所にしか無い癖は、そのレシピの `## ハマり所` に置いてある。

各族の最後に、実際に踏んだレシピを挙げてある。詳しい経緯はそちらを見ること。
整合は `check_pitfalls.py` が機械で見ている（引いたレシピが消えたら落ちる）。

---

## 1. 合計行が明細と同居している ★最多

**いちばん多い。19本のレシピで踏んでいる。** 明細の行と、その合計の行が、
同じ列・同じ形で返ってくる。素朴に全部足すと**倍前後に膨らむ**。

膨らみ方が「2倍ちょうど」なら気づくが、**一部の行だけ合計が在る**ことが多いので、
1.3倍とか1.7倍とか、もっともらしい値になる。これが危ない。

| 形 | 出所 |
|---|---|
| 品目別の行と `PRODUCT=TOTAL` が同居 | [eurostat/trade_by_transport_mode](recipes/eurostat/trade_by_transport_mode/recipe.md) |
| `tra_cov` 未指定で Total／国内／国際／域内／域外が同時に返る | [aviation/airport_passengers](recipes/aviation/airport_passengers/recipe.md) |
| `partnerCode=0` は World（相手国ではない） | [comtrade/trade_ranking](recipes/comtrade/trade_ranking/recipe.md) [comtrade/region_trade_matrix](recipes/comtrade/region_trade_matrix/recipe.md) |
| `China` = 中国本土＋台湾＋香港＋マカオの**合計**。`China, mainland` と重複 | [faostat/crops_ranking](recipes/faostat/crops_ranking/recipe.md) |
| `LocTypeID` で国(4)・地域(2)・サブ地域(3)が同じ表に | [un_wpp/population_ranking](recipes/un_wpp/population_ranking/recipe.md) |
| `WLD` `EUU` も国コードとして返る | [world_bank/country_indicator](recipes/world_bank/country_indicator/recipe.md) [aquastat/water_resources](recipes/aquastat/water_resources/recipe.md) |
| 政令市の「市計」と「区」が併存 | [estat/manufacturing_shipment_prefecture](recipes/estat/manufacturing_shipment_prefecture/recipe.md) |
| 年齢階級に再掲（15歳未満等）が混じる | [estat/census_age_sex_municipality](recipes/estat/census_age_sex_municipality/recipe.md) |
| `Direction` に `Both Directions` がある | [transport/roro_and_road_freight](recipes/transport/roro_and_road_freight/recipe.md) |
| 報告国「内」は sum・報告国「間」は max（両方 sum で二重計上） | [eurostat/air_flow](recipes/eurostat/air_flow/recipe.md) |
| `European Union (15)` 行は UK を含む | [worldsteel/crude_steel](recipes/worldsteel/crude_steel/recipe.md) [oica/vehicle_production](recipes/oica/vehicle_production/recipe.md) |
| 「総額」「旅行のみ」「旅客輸送のみ」が同じ表に | [unwto/tourism_statistics](recipes/unwto/tourism_statistics/recipe.md) |

**気づき方。** 合計が分かっている値（世界計・全国計）と突き合わせる。
それが無いときは、**桁で殴られる実例**を1件用意する。ポルトガルの航空貨物が
重量の9.9%（235万トン）になったとき、リスボン空港の実績が15万トン程度だと
知っていたから気づけた。

## 2. 「200 が返った」も「行が在る」も、データが在る証拠ではない

**6本で踏んでいる。** エラーにならないので、**黙って0や欠落のまま先へ進む**。
404 より危ない。

| 形 | 出所 |
|---|---|
| HTTP 200 で `[]`。グラフ表示用のビューで、実体は別ID | [aviation/airport_passengers](recipes/aviation/airport_passengers/recipe.md)（BTS `tqbz-sck3`→`r495-tyji`） |
| 空港の行は在るのに数字が全部 0（別事業者が運営し報告が上がらない） | [aviation/airport_passengers](recipes/aviation/airport_passengers/recipe.md)（CAAP の NAIA） |
| `value=[]` を返す指標がある | [aquastat/water_resources](recipes/aquastat/water_resources/recipe.md) |
| `page=0 / total=0` を返す国がある | [world_bank/country_indicator](recipes/world_bank/country_indicator/recipe.md)（TWN） |
| 新しい分類だけ見ていると古い年が0件 | [ilo/employment_by_activity](recipes/ilo/employment_by_activity/recipe.md)（ISIC Rev.4 のみ見る） |
| コードが違うと全年0件 | [comtrade/region_trade_matrix](recipes/comtrade/region_trade_matrix/recipe.md)（India=699, France=251） |

**気づき方。** 0件・空配列を見たら、**結論を出す前に一巡する**。
別コード・別系統・別版・言い換え。0件は「無い」ではなく「この引き方では出ない」。

## 3. 404・403 は「無い」の証拠にならない

**5本。** ステータスコードだけで経路を捨てると、在るものを落とす。

- **404** — 当てずっぽうのIDを叩いただけかもしれない。まず**一覧を引く**。
  [aviation/airport_passengers](recipes/aviation/airport_passengers/recipe.md) で「BTSのAPIは落ちている」と書いたが誤りだった。
  `data.bts.gov/api/views.json` で一覧が引ける。
- **404** — API系とバルク系は別。API が404でもバルクに在る。
  [eurostat/trade_by_transport_mode](recipes/eurostat/trade_by_transport_mode/recipe.md)（`DS-059331`）
- **403 / 406** — User-Agent が無いだけ。`urllib` は既定UAを送らない。
  [aquastat/water_resources](recipes/aquastat/water_resources/recipe.md) [unwto/tourism_statistics](recipes/unwto/tourism_statistics/recipe.md)（Cloudflare）
  [gsi_dem/route_section](recipes/gsi_dem/route_section/recipe.md)（Overpass は406）

## 4. 単位と桁は列名の外に書いてある

**7本。** 値そのものは正しく、**桁だけ違う**。図にすると気づかないことがある。

| 形 | 出所 |
|---|---|
| `UNIT_MULT` 列（×10^9 / ×10^3）を掛け忘れる | [aquastat/water_resources](recipes/aquastat/water_resources/recipe.md) |
| 千人単位 | [un_wpp/population_ranking](recipes/un_wpp/population_ranking/recipe.md) [eurostat/air_flow](recipes/eurostat/air_flow/recipe.md) |
| 万円（同じ統計でも都道府県表は百万円） | [estat/manufacturing_shipment_prefecture](recipes/estat/manufacturing_shipment_prefecture/recipe.md) |
| カラム名の末尾が単位（`_consumption`=TWh / `_share_*`=%） | [owid/energy_data](recipes/owid/energy_data/recipe.md) |
| 数量の単位が品目で変わる（kg / 台 / バレル） | [comtrade/trade_ranking](recipes/comtrade/trade_ranking/recipe.md) |
| 図ごとに濃淡の桁が違う（平年 0.35 / 事例 1.1） | [cams/dust_aod_map](recipes/cams/dust_aod_map/recipe.md) |

## 5. 数値が文字列で返る

**3本だが、静かに壊れるので挙げる。** 型キャストを忘れると、比較とソートが
辞書順になる。`"9" > "10"` が真になる。

- `OBS_VALUE` が `"57.5"` … [aquastat/water_resources](recipes/aquastat/water_resources/recipe.md)
- `LocTypeID` が `"4"`、`Time` も文字列 … [un_wpp/population_ranking](recipes/un_wpp/population_ranking/recipe.md)
- `date` が `"2024"` … [world_bank/country_indicator](recipes/world_bank/country_indicator/recipe.md)

## 6. 同じ名前の指標に、複数の定義がある

**8本。** どちらも正しい値なので、検算では捕まらない。**混ぜたときだけ**段差が出る。

| 取り違え | 出所 |
|---|---|
| 産出額（中間投入込み）と 付加価値 | [unido/industry_output](recipes/unido/industry_output/recipe.md) ※ベトナムの工業生産額>GDP は正常 |
| 生産 と 見かけ消費 | [worldsteel/crude_steel](recipes/worldsteel/crude_steel/recipe.md) |
| CIF（運賃保険込み）と FOB | [comtrade/trade_ranking](recipes/comtrade/trade_ranking/recipe.md) |
| 一次エネルギー と 電力。「再エネ」に bio を含むか | [owid/energy_data](recipes/owid/energy_data/recipe.md) |
| gross発電 と 分散型太陽光推計込み | [iea/electricity_generation](recipes/iea/electricity_generation/recipe.md) |
| 出発便のみ と 到着＋出発 | [aviation/airport_passengers](recipes/aviation/airport_passengers/recipe.md)（BTS と Eurostat を並べると米国だけ半分） |
| 「その国から運ばれた量」と「その国籍が運んだ量」 | [transport/roro_and_road_freight](recipes/transport/roro_and_road_freight/recipe.md)（Eurostat `road_go_ia_lgtt` の `geo`） |
| 総流域面積 と 有効流域面積 | [hydrosheds/world_basin_erosion_map](recipes/hydrosheds/world_basin_erosion_map/recipe.md) |

**原則。** 出所をまたいで並べるなら、**どちらかに統一する**。
統一できないなら、図の注記に定義差を書く。

## 7. コード体系は年で変わる

**6本。** 去年動いたコードが今年は別のものを指す。あるいは空を返す。

- 調査年で分類の番号が入れ替わる … [estat/census_age_sex_municipality](recipes/estat/census_age_sex_municipality/recipe.md)（2015と2020で男女/年齢の cat が逆）
- 新旧の分類が同居し、古い年は旧版しかない … [ilo/employment_by_activity](recipes/ilo/employment_by_activity/recipe.md)（ISIC Rev.3 / Rev.4）
- 独自コードがある … [comtrade/region_trade_matrix](recipes/comtrade/region_trade_matrix/recipe.md)（India=699, France=251）
- **その年の定義で集計されている** … [eurostat/trade_by_transport_mode](recipes/eurostat/trade_by_transport_mode/recipe.md)（英国は2019年のファイルに1行も無い＝当時は域内）
- ファイル名（＝対象範囲）が版で変わる … [faostat/crops_ranking](recipes/faostat/crops_ranking/recipe.md)（Crops → Crops_Livestock）
- 解体・統合した国のコード … [world_bank/country_indicator](recipes/world_bank/country_indicator/recipe.md)（USSR / Yugoslavia / 東西ドイツ）

**原則。** 「古い年が引けない」ではなく「**古い年はその年の定義で引く**」。
過去問に合わせるときだけ、新しい年を旧定義に寄せる。

## 8. PDF と Excel は、列が見た目どおりに並んでいない

**7本。** パースが通っても中身が別物になる。

- **数字が空白区切りの千位**（`4 663 749`）で列間も単一空白 → 語彙的に切れない。
  **`pdftotext -layout` で列を多スペース化し `\s{2,}` で割る**。
  [oica/vehicle_production](recipes/oica/vehicle_production/recipe.md) [worldsteel/crude_steel](recipes/worldsteel/crude_steel/recipe.md)
- **推定値記号 `e` が付くと数値が次の行に折り返す** … [usgs/mineral_production](recipes/usgs/mineral_production/recipe.md)
- **表が交互配置で列がずれる**（アルミナ→ボーキサイト→埋蔵量）… [usgs/mineral_production](recipes/usgs/mineral_production/recipe.md)
- **1枚目のシートは説明文**。`sheet_name=0` だと断片が返る … [unwto/tourism_statistics](recipes/unwto/tourism_statistics/recipe.md)
- **`skiprows` が要る**。そのままだと列名が `Unnamed: 1` … [transport/roro_and_road_freight](recipes/transport/roro_and_road_freight/recipe.md)
- **似た表番号を取り違える**。Cover シートで表番号を確かめる … [transport/roro_and_road_freight](recipes/transport/roro_and_road_freight/recipe.md)（PORT0205 / PORT0302）
- **カンマの有無で列を判定する**（伸び率にはカンマが無い）… [jnto/inbound_outbound](recipes/jnto/inbound_outbound/recipe.md)
- **目次(TOC)行を本文と間違える**（末尾がページ番号）… [worldsteel/crude_steel](recipes/worldsteel/crude_steel/recipe.md)

## 9. 図は目で読まない

**3本＋教本。** 作った図を確かめるとき、目分量は当てにならない。

- **円グラフを目分量で読まない。** 凡例の見本で閾値を較正し、画素を数える。
  [eurostat/trade_by_transport_mode](recipes/eurostat/trade_by_transport_mode/recipe.md)（目分量で「合わない」と誤判断した）
- **縮小PDFの目視で体裁を決めない。** 元 docx の埋め込み画像を直接見る。
  [comtrade/mutual_flow_diagram](recipes/comtrade/mutual_flow_diagram/recipe.md)（曲線を「直線」と誤読）
- **名前のある地点に生データを使わない。** 公式値で固定する。
  [gsi_dem/relief_map](recipes/gsi_dem/relief_map/recipe.md)（DEM生値をずれた画素で拾い 3067m を 3046m と誤記）

→ 画像モデルに「判断」させず「転記」させ、答え合わせはコードでやる。
`_workspace/scripts/check_figure.py` を使う。

## 10. 最新年は速報か、まだ無い

**4本。** 空欄を「0」や「減少」と読むと図が嘘になる。

- 当年データはほぼ無い（前年ぶんが6〜12か月遅れ）… [owid/energy_data](recipes/owid/energy_data/recipe.md)
- 当年 −2 年が確定 … [iea/electricity_generation](recipes/iea/electricity_generation/recipe.md)
- 主要国の未報告が多い。1〜2年前の確定年を使う … [comtrade/region_trade_matrix](recipes/comtrade/region_trade_matrix/recipe.md)
- 非報告国は輸入側に出てこない → 相手国の輸出で**鏡像補完** … [comtrade/region_trade_matrix](recipes/comtrade/region_trade_matrix/recipe.md)

---

## 新しい出所に当たるときの手順

1. **一覧を引く。** いきなりIDを当てない（族3）
2. **1行取って列を見る。** 型・単位・`UNIT_MULT`・合計行の有無（族1・4・5）
3. **合計の分かっている値と1件照合する。** 世界計・全国計・公表値（族1）
4. **0件・空配列が出たら、結論の前に一巡する。** 別コード・別系統・別版（族2）
5. **古い年を1つ引いてみる。** 分類コードが変わっていないか（族7）
6. **他の出所と並べるなら、定義を突き合わせる。**（族6）
7. **踏んだ罠は、そのレシピの `## ハマり所` に書く。** 3つめの出所で
   同じ形を踏んだら、この文書に族として上げる。
