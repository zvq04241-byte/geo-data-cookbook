# AGENTS.md — 公開統計の罠

**このファイルは AI エージェント向けです。**

公開統計は、取得に成功しても値が間違っていることがあります。リクエストは
200 を返し、数字はもっともらしく見え、図が刷られてから気づきます。

以下は、実際に踏んだ罠の索引です。**扱うデータ源が一致したら、必ず該当の
`recipe.md` を読んでから書いてください。**索引の1行だけでは足りません。

★このファイル自体は索引です。全文を読み込む必要はありません。
  該当する1本だけを開いてください（全文は概算 26,000 トークンあります）。

---


## aquastat

**`recipes/aquastat/water_resources`**

- 総IRWRは `4157`。`4187` ではない。
- urllib は User-Agent なしで `403 Forbidden`。
- 指標は Data360 から消えることがある。
- `OBS_VALUE` は文字列
- TRWR/IRWR は長期平均で年変化しない。
- `OBS_STATUS` は配信側で変わる。この列で推計かどうかを決めない。
- 国名は ISO3（REF_AREA）。


## aviation

**`recipes/aviation/airport_passengers`**

- Eurostat の空港次元は `rep_airp`。`geo` ではない。
- `tra_cov` を指定しないと5種類の行が同時に返る
- 一つの都市に複数の空港がある。
- e-Stat 第9表は国内線のみ。
- 「就航都市数」は旅客数とは別のデータ。
- ★前版の「BTSのAPIは落ちている」は誤りだった。
- BTSの「AFF - Passengers By Airport」(`tqbz-sck3`) は空の殻。
- BTSには国際線の列が無い。
- 日本の国際線と国内線は出所も定義も年もずれる。
- CAAP の xls には NAIA と Mactan の行があるのに数字は全部0。
- MIAA の PDF はファイル名に更新日が入る
- 国ごとの航空旅客に WDI（`IS.AIR.PSGR`）を使わない


## cams


## comtrade

**`recipes/comtrade/region_trade_matrix`**

- ★インドは Comtrade 独自コード 699（M49 の 356 ではない）
- `partnerCode` の結果に集計値が混じる
- 500件上限
- 最新年は速報で欠損
- `primaryValue` が None の行
- ★地域は、属する国を全部入れて定義する。主要国だけで代表させない
- ★フランスは Comtrade の reporter/partner コードが 251（M49 250 ではない）
- ★一部の国（France 等）は応答が partner2Code(再輸出元)×motCode(輸送モード)に分解され、500行で打切り
- ★非報告国は輸入側に出てこない

**`recipes/comtrade/trade_ranking`**

- 500件打ち切り → 逆引き集計で「既定28か国の中の順位」に切り替える（最重要。解消ではない）
- 輸出国側と輸入国側の値は非対称（逆引き時の注意）
- CIF / FOB の混在
- partnerCode=0 は "World"（合計）
- 自国レコードの混入
- qty の単位は HS によって異なる
- データ遅延
- customsCode / motCode の指定


## estat

**`recipes/estat/calc_social`**

- 社会増加率は「人口増加率 − 自然増加率」（最重要・概念）
- 同一統計表の2つの cdCat01 を別々に取得して差を取る
- appId をログ・出力に出さない（漏洩防止）
- area code 5桁・末尾000＝都道府県、00000＝全国は除外
- CLASS_INF の名前に【番号】が付く
- VALUE が単一行のとき dict で返る
- cdTime は YYYYMMDDHH 形式
- 両指標が揃う都道府県のみ計算
- limit の打ち切りを止める

**`recipes/estat/census_age_sex_municipality`**

- ★2015と2020で男女・年齢の cat 番号が入れ替わる
- 2015は全域/人口集中地区の区分(cat01)がある
- 市区町村コードは5桁
- 年齢コードに再掲（R1〜R6=15歳未満等）や不詳(22/1490)が混じる
- limit の打ち切り

**`recipes/estat/census_small_area`**

- 統計表の検索に出てこない
- 総数・男・女の3行
- レベル3はレベル4の合計
- 「X」と「-」
- 合算先が親のことがある
- 列は見出しで選ぶ
- 境界
- CRLF
- 外周の線に隙間が出る

**`recipes/estat/commerce_sales_prefecture`**

- 指標は **tab（表章項目）**。`cdTab` で絞る
- 産業は cat01（卸小売の細分類220種）
- 従業者規模は cat02 → **合計=0** を指定
- 都道府県は area（5桁・末尾000）＋政令市混在
- VALUE が単一だと dict（list でない）
- 調査年 ≠ 販売額の実績年
- 卸売は多段階で“水増し”（解釈の罠）

**`recipes/estat/keizai_census_industry`**

- 「農業関連サービス業」は産業中分類では分離不可
- tab（表章事項）に事業所数以外（従業者数等）が混在
- cat02（単独・本所・支所）は「総数」で絞る
- 2024 と 2021 は別の調査

**`recipes/estat/manufacturing_shipment_prefecture`**

- 指標は cat01。**cdTab でなく cdCat01 で絞る**（最重要）
- 都道府県は複合 cat02 に埋没＋政令市が混在
- 調査年 ≠ 実績年／複数年同居
- limit のサイレント打切り
- 検算: 47都道府県合計 == 全国計
- 中分類名の表記ゆれ
- 市区町村レベル特有（--level municipality）
- 前の年の実績は、前の調査の表を指定して取る（2026-10-24）
- 「電気機械」は中分類が3つに分かれている

**`recipes/estat/population_natural_change_prefecture`**

- 期間は暦年ではない（前年10月～当年9月）
- 人口動態統計（厚生労働省）とは別の数字
- 単位は‰（人口千人当たり）
- 表は国勢調査の基準ごとに別
- 検算は「そろっているか」だけ

**`recipes/estat/prefecture_classify`**

- appId はログに残るので注意（最重要）
- 時間軸コード（cd_time）の桁数
- area コードの体系
- classify_n の分割ルール
- CLASS_INF からの名前マッピング必須
- 表示用名称の文字種
- データ取得失敗時の RESULT.STATUS
- limit の上限
- ★`--classify-n` は順位で同じ数ずつに切る。地図の区切りには使わない（2026-10-24 追記）


## eu_budget

**`recipes/eu_budget/spending_revenue`**

- 支払額は「TOTAL own resources」。「TOTAL REVENUE」には国別の値が無い
- シートの作りが年で違う → 位置を決め打ちしない
- 加盟前の国にも列がある → その年の加盟国だけを残す
- NextGenerationEU（復興基金）は別ブロック
- ルクセンブルク・ベルギーは行政支出で受取額が膨らむ
- 支払額には関税が入る（港のある国は関税の部分が膨らむ）
- 国は ISO2。ギリシャは EL


## eurostat

**`recipes/eurostat/air_flow`**

- value のキーは「位置インデックス(数値)」
- 報告国"内"は同一国ペアの空港ペアを sum
- 報告国"間"は max
- region_pair は地域順（Europe<West Asia<Africa）で正規化
- 旅客は /1000 して「千人」
- 国内線(報告国==相手国)を除外
- 報告国が絡まない国ペアは、データに現れないだけ
- 月次(freq=M)の time コードは `2024-01` 形式（YYYY-MM）
- 地域の国集合を手で並べない

**`recipes/eurostat/trade_by_transport_mode`**

- dissemination API を引いて404を見ても「無い」ではない。
- ★品目別の行と `PRODUCT=TOTAL` の合計行が同居している。全部足すと二重計上。
- 相手国コード `QS` は「船舶・航空機への積込み」
- 域内／域外は列に無い。相手国が EU27 かどうかで自分で分ける。
- `.7z` である。
- `QUANTITY_KG` は空のことがある。
- `TRANSPORT_HS` は域外貿易のみ。
- Comext はその年のEU定義を使う。
- 円グラフを目分量で読まない。
- 国によって現れる輸送手段が違う。
- ★完全性の検査（`fetch.py` が自動で行う）。


## faostat

**`recipes/faostat/crops_ranking`**

- CSV のエンコーディング
- 集計地域の混入（最重要）
- Item 名の表記揺れ
- メモリ使用量
- ZIP内の付帯CSV
- データセット名の歴史的変更
- 推計・補完の値（Flag E / I）に印を付ける（2026-10-20）


## figure


## gsi_dem


## gsi_photo


## gsi_vector


## hydrosheds


## iea

**`recipes/iea/electricity_generation`**

- 国コードは「大文字フルネーム」（最重要・LLMが幻覚しやすい）
- b. 正確性ガード（fetch.py 実装済）
- product="ELECTR" でフィルタ（電力 ≠ 熱）
- flow コードを知らないと使えない（電源別の肝）
- 単位は GWh（→TWh換算必須）
- null は欠損（0埋めしない）。行が無い電源も空欄
- gross（総生産）であること / OWID との差
- 残差「その他」の作り方（積み上げ図）
- デンマーク等の早期年


## ilo

**`recipes/ilo/employment_by_activity`**

- 次元数がデータフローで違う（賃金は4、就業構造は5）
- 構造の問い合わせは JSON だと 406。XML なら通る
- 最新年が国ごとに違う
- 分母は `ECO_ISIC4_TOTAL` と `ECO_SECTOR_TOTAL` の2つがある
- 国コードの連結は「+」
- 「労働人口に占める割合」と「就業者に占める割合」は別物
- ISIC4 の U（治外法権機関）と X（分類不能）は 0 ではない

**`recipes/ilo/wages_ranking`**

- SDMX-CSV は Accept ヘッダで要求する（最重要）
- データフローごとに次元数が違う＝キーのドット数が違う
- 国コードの連結は「+」
- 通貨は URL でなく CUR 列で後フィルタ
- 最新年は国ごとに異なる（全行同年ではない）
- 時間給を直接報告しない国は換算する
- 空データは HTTP 404 ＋本文 "No data is found"
- LCU は国際比較に不向き


## jma

**`recipes/jma/amedas_normals`**

- 値とRMKが交互に並ぶ・要素番号は3列目（最重要）
- 要素番号と単位（0.1 単位に注意）・★降雪は 6300
- 観測所座標は別ファイル・[度,分]配列
- ZIP内CSV名 → block_no、座標表に無い局は外して記録
- 値なしは RMK で判定する（0 は値なしのこともある）
- User-Agent を付ける
- 値のある全観測所を出す（間引きは地図側の責務）・母数は指標で変わる
- 平年値の統計期間は局で違う・ZIP は差し替えがある

**`recipes/jma/snowfall_ranking`**

- 見出しは3段で colspan がある → 見出しを展開して名前で列を探す（最重要）
- 「年」は暦年でなく寒候年
- 値欄の記号は気象庁の定義どおりに扱う
- User-Agent を付ける
- 落とした都市は出力に残る
- 1都市=1リクエスト → ランキングはN都市ループ
- block_no / prec_no は地点固有ID
- HTML構造変更で壊れうる


## jnto

**`recipes/jnto/inbound_outbound`**

- 二次資料は収録期間が短いことがある。長期（1964〜）はJNTO原典PDFを直接
- PDFパース
- 年次更新でPDFファイル名（URL）が変わる
- コロナ後の回復は非対称


## mlit

**`recipes/mlit/n03_municipal_boundary`**

- 属性のエンコーディングは cp932（最重要）
- URL の日付は年により異なる（推測で作らない）
- 1市区町村が複数ポリゴン行に分割されている → dissolve 必須
- 行政コードは5桁・不正行を除外
- 政令指定都市は区ごとに別コード
- 不正ジオメトリは make_valid で修復
- 面積は地理座標のままでは測れない
- 取得は都道府県単位（全国は重い）


## mof

**`recipes/mof/direct_investment`**

- 地域と国が別列。合計するときは重複に注意
- 地域区分がよく使われる分け方と違う
- ヘッダーが4行＋業種が2段
- 値が「.」や「Ⅹ」のことがある
- 単位は億円


## naturalearth

**`recipes/naturalearth/japan_prefectures`**

- 北方4島はロシア(サハリン州)ポリゴンに含まれる（最重要）
- bbox で島を「切らない」（得撫島の切れ端が付く）
- NE の name はマクロン付き
- ジオメトリ更新は list→再構築（.at[] 直代入は破壊的）
- 自己検証で北方領土欠落を機械検出
- 東京都の最東端は南鳥島 153.986°E
- CRS は明示的に EPSG:4326 へ
- 出力は GPKG（境界本体）＋検証用 CSV の二本立て
- 範囲の検査は北方領土だけでは足りない（2026-10-19）

**`recipes/naturalearth/world_choropleth`**

- 図法の既定は正方形図法（PlateCarree＝投影なし matplotlib 直描き）
- PDFは matplotlib 直書きでなく SVG → Inkscape 変換
- 国の切り出しは centroid フィルタ禁止、xlim/ylim で
- Natural Earth は仏・諾で ISO_A2="-99"（欠番）
- 非ISO地理コードの補正（Eurostat等）
- 凡例は「空いた隅を探して置く」。固定位置も固定の凡例帯もどちらも駄目


## noaa_psl


## oecd

**`recipes/oecd/sdmx_datasets`**

- データのURLに `latest` は書けない（最重要）
- 次元数はデータフローごとに違う。ドットの数を合わせる
- 単位は次元。URLでなく UNIT_MEASURE で絞る
- 報告年が国・項目ごとに違う
- 合計コードを上位N国に混ぜない
- 一覧XMLは約9MB


## oica

**`recipes/oica/vehicle_production`**

- 現行サイトはJS描画・DLは6年窓のみ
- 数値が空白区切り千位で列間も単一スペース
- 直近の全車種PDFは国によって車種の範囲が違う
- EU27の単一公式行があるのは直近PDFだけ
- 脚注参照と相手先名の混入


## owid

**`recipes/owid/energy_data`**

- country 列に集計値が混在（**最重要**）
- 国名の表記揺れ
- 構成比の合計（5源がそろえば100%）
- share と consumption の単位の違い
- 集計値 World は国の単純和と一致しない
- 最新年は列で違う
- キャッシュ更新戦略
- 100+ カラムからの選択
- 単位プレフィックスの混在
- 「再エネ」の定義の揺れ


## transport

**`recipes/transport/roro_and_road_freight`**

- `PORT0302` と `PORT0205` を取り違えやすい。
- これは「港」の統計。ユーロトンネルは入っていない。
- 随伴と無随伴を足さないと道路貨物の全体にならない。
- 相手国名が独特。
- `.ods` は `odfpy` が要る
- `Data` シートは `skiprows=3`。
- Eurostat `road_go_ia_tc`（積地国×揚地国）は2013年止まり。
- 比率と金額を取り違えない。
- `Direction` に `Both Directions` がある。
- `--eu-road` の既定は車両国籍 PT,ES,FR の3か国。


## un_wpp

**`recipes/un_wpp/population_ranking`**

- BOM 付き UTF-8（**最重要・最初に踏む罠**）
- LocTypeID で集計地域を除外
- Time 列は文字列
- Variant の選択
- PopTotal は千人単位
- 中国とインドの逆転（2024年データ点）
- ISO 国コードフィールド
- ファイルサイズと読み込み速度
- PopDensity は空欄あり
- 過去・推計年の境界
- 5年平均を折れ線にするとき、点は期間の真ん中に置く
- 版が変わると、過去の年の値まで変わる


## un_wup

**`recipes/un_wup/urbanization_ranking`**

- 「Cities and Towns %」は従来の都市人口率とは別物（最重要）
- 集計地域の除外は種別コード row[7]==4 で行う（列の見出しも確かめる）
- type==4 は非主権地域も含む
- 年列は index 10 以降・ヘッダ値を直接スキャンして引く
- openpyxl は read_only=True, data_only=True
- シート選択を間違えると別定義の値が黙って返る
- F02=percent / F01=population の取り違え
- 2025 超の年は推計値


## unido

**`recipes/unido/industry_output`**

- サイト直下は Cloudflare で 403。`/portal/` 配下だけが通る（最重要）
- urllib 既定の User-Agent は弾かれる
- Accept ヘッダが必須。間違えると 400
- キーは4段。空の段は不可
- 国は1回あたり3か国まで → fetch.py が3か国ずつに分けて取る
- 値は自国通貨。ドルではない
- Rev.3 と Rev.4 で収録国・年がまるで違う
- Output と Value added を混同しない


## unwto

**`recipes/unwto/tourism_statistics`**

- シートは "Data"。1枚目は "Overview"（説明文だけ）。
- 「観光収入」は3指標が同じ表に混在する。
- `partner_area_label` の扱いはドメインで変わる。
- 1995年から。1990年は無い。
- 単位は分野で違う。必ず `unit` 列で確認する。
- 中国は `China`。香港・マカオ・台湾は別行
- 世界計の行は無い
- ダウンロードに User-Agent が要る。


## usgs

**`recipes/usgs/mineral_production`**

- ★`e`（推定値）付きの国は、数値が次の行に折り返す
- ボーキサイト表はアルミナ生産と並んでいる
- `W`（企業秘匿）と `—`（該当なし・ゼロ）は意味が違う。混ぜない。
- `Other countries` の行を分母から落とさない。
- 版をまたいで比べるときは、両方の版の World total で各国のシェアを出す


## who_gho

**`recipes/who_gho/health_indicators`**

- 性別の次元コードに接頭辞が付く（最重要）
- 「肥満」と「過体重」は別物。WDIと混同しない
- 国コードは ISO3。地域集計も同じ次元に混ざる
- $filter の or は括弧でくくる
- 推計値なので改定される


## world_bank

**`recipes/world_bank/country_indicator`**

- レスポンスは `[meta, data]` の2要素配列（**最重要**）
- null value が大量に混入
- 同一国に複数年のレコードが返る
- mrv と per_page の使い分け
- 国コードは ISO3
- country フィールドの構造
- date は文字列、value は数値（または null）
- インジケータ名のクエリは大文字小文字区別
- ヒストリカルな国境変更
- レート制限と並列化
- TWN（台湾）は値が返らない
- 航空旅客数・航空貨物は「航空会社の登録国」で数えた値（2026-10-21）


## worldsteel

**`recipes/worldsteel/crude_steel`**

- "生産"と"消費(見かけ消費)"を混同しない
- 同名の別テーブルを拾わない（SSY2002）
- 列は空白区切り・`pdftotext -layout` 必須
- EU27(2000)は EU15−UK＋新規加盟国
- EU の行は完全一致で取る

---

## 使い方（エージェント向け）

1. 扱うデータ源が上の一覧にあるか見る
2. あれば、その `recipe.md` を読む。**索引の1行で済ませない**
3. 取得したら、罠に書かれている検算を必ず通す
   （合計と全体値の突合、既知の1件との照合など）
4. 一覧に無いデータ源なら、**新しい罠を踏む可能性がある。**
   値がもっともらしくても、別の資料か公表値と1件照合してから使う

## 使い方（人向け）

このリポジトリを、作業しているプロジェクトの隣に置いてください。
多くの AI CLI は、ワークスペース直下の `AGENTS.md` を自動で読みます。

踏んだ罠がここに無ければ、issue でお知らせください
（[CONTRIBUTING.md](CONTRIBUTING.md)）。**コードは要りません。**
