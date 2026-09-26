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
- 1人当たり（4174）は Data360 では空。
- `OBS_VALUE` は文字列
- TRWR/IRWR は長期平均で年変化しない。
- `OBS_STATUS` は E（推計）/ I（補完）が大半。
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


## cams


## comtrade

**`recipes/comtrade/region_trade_matrix`**

- ★インドは Comtrade 独自コード 699（M49 の 356 ではない）
- `partnerCode` の結果に集計値が混じる
- 500件上限
- 最新年は速報で欠損
- `primaryValue` が None の行
- 地域定義は主要貿易国で代表
- ★フランスは Comtrade の reporter/partner コードが 251（M49 250 ではない）
- ★一部の国（France 等）は応答が partner2Code(再輸出元)×motCode(輸送モード)に分解され、500行で打切り
- ★非報告国は輸入側に出てこない

**`recipes/comtrade/trade_ranking`**

- 500件打ち切り → 逆引き集計で解消（最重要）
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

**`recipes/estat/census_age_sex_municipality`**

- ★2015と2020で男女・年齢の cat 番号が入れ替わる
- 2015は全域/人口集中地区の区分(cat01)がある
- 市区町村コードは5桁・末尾000
- 年齢コードに再掲（R1〜R6=15歳未満等）や不詳(22/1490)が混じる

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

**`recipes/estat/manufacturing_shipment_prefecture`**

- 指標は cat01。**cdTab でなく cdCat01 で絞る**（最重要）
- 都道府県は複合 cat02 に埋没＋政令市が混在
- 調査年 ≠ 実績年／複数年同居
- limit のサイレント打切り
- 検算: 47都道府県合計 == 全国計
- 中分類名の表記ゆれ
- 市区町村レベル特有（--level municipality）

**`recipes/estat/prefecture_classify`**

- appId はログに残るので注意（最重要）
- 時間軸コード（cd_time）の桁数
- area コードの体系
- classify_n の分割ルール
- CLASS_INF からの名前マッピング必須
- 表示用名称の文字種
- データ取得失敗時の RESULT.STATUS
- limit の上限


## eurostat

**`recipes/eurostat/air_flow`**

- value のキーは「位置インデックス(数値)」
- 報告国"内"は同一国ペアの空港ペアを sum
- 報告国"間"は max
- region_pair は地域順（Europe<West Asia<Africa）で正規化
- 旅客は /1000 して「千人」
- 国内線(報告国==相手国)を除外
- 地政学的に成立しない路線は0扱い
- 月次(freq=M)の time コードは `2024-01` 形式（YYYY-MM）

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


## faostat

**`recipes/faostat/crops_ranking`**

- CSV のエンコーディング
- 集計地域の混入（最重要）
- Item 名の表記揺れ
- メモリ使用量
- ZIP内の付帯CSV
- データセット名の歴史的変更


## gsi_dem


## hydrosheds


## iea

**`recipes/iea/electricity_generation`**

- 国コードは「大文字フルネーム」（最重要・LLMが幻覚しやすい）
- b. 正確性ガード（fetch.py 実装済）
- product="ELECTR" でフィルタ（電力 ≠ 熱）
- flow コードを知らないと使えない（電源別の肝）
- 単位は GWh（→TWh換算必須）
- null は欠損（0埋めしない）
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
- ISIC4 の U（治外法権機関）と X（分類不能）は小さいが 0 ではない

**`recipes/ilo/wages_ranking`**

- SDMX-CSV は Accept ヘッダで要求する（最重要）
- データフローごとに次元数が違う＝キーのドット数が違う
- 国コードの連結は「+」
- 通貨は URL でなく CUR 列で後フィルタ
- 最新年は国ごとに異なる（全行同年ではない）
- 時間給は直接報告が約4割・残りは換算
- 空データの判定は本文先頭の "No data"
- LCU は国際比較に不向き


## jma

**`recipes/jma/amedas_normals`**

- 月別値は「6列目以降の1列おき」・要素コードは3列目（最重要）
- 要素コードと単位（0.1 単位に注意）
- 観測所座標は別ファイル・[度,分]配列
- ZIP内CSV名 → block_no、座標表に無い局はスキップ
- 欠測・未観測は 0 で来る → None 化
- User-Agent 必須
- 全観測所を出す（間引きは地図側の責務）
- 平年値は固定（1991-2020）

**`recipes/jma/snowfall_ranking`**

- 列位置は地点で揺れる → <th> を動的検出（最重要）
- 「年」は暦年でなく寒候年
- 欠測トークンの正規化
- User-Agent 必須
- 無雪地点は自動除外される
- 1都市=1リクエスト → ランキングはN都市ループ
- block_no / prec_no は地点固有ID
- HTML構造変更で壊れうる


## jnto

**`recipes/jnto/inbound_outbound`**

- 二次資料（世界国勢図会等）は近年だけ
- PDFパース
- 年次更新でPDFファイル名（URL）が変わる
- コロナ後の回復は非対称


## mlit

**`recipes/mlit/n03_municipal_boundary`**

- 属性のエンコーディングは cp932（最重要）
- URL の日付は年により異なる
- 1市区町村が複数ポリゴン行に分割されている → dissolve 必須
- 行政コードは5桁・不正行を除外
- 政令指定都市は区ごとに別コード
- 不正ジオメトリは make_valid で修復
- 面積は地理座標のままでは測れない
- 取得は都道府県単位（全国は重い）


## mof

**`recipes/mof/direct_investment`**

- 地域と国が別列。合計するときは重複に注意
- 地域区分が教材の言い方と違う
- ヘッダーが4行＋業種が2段
- 値が「.」や「-」のことがある
- 単位は百万円


## naturalearth

**`recipes/naturalearth/japan_prefectures`**

- 北方4島はロシア(サハリン州)ポリゴンに含まれる（最重要）
- bbox 北限は 45.6°N（得撫島を除外）
- NE の name はマクロン付き
- ジオメトリ更新は list→再構築（.at[] 直代入は破壊的）
- 自己検証で北方領土欠落を機械検出
- 東京都の最東端は南鳥島 153.99°E
- CRS は明示的に EPSG:4326 へ
- 出力は GPKG（境界本体）＋検証用 CSV の二本立て

**`recipes/naturalearth/world_choropleth`**

- 図法は正方形図法（PlateCarree＝投影なし matplotlib 直描き）
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
- 報告年が国ごとに違う
- 合計コードを上位N国に混ぜない
- 一覧XMLは8.9MB


## oica

**`recipes/oica/vehicle_production`**

- 現行サイトはJS描画・DLは6年窓のみ
- 数値が空白区切り千位で列間も単一スペース
- 独(GERMANY)の直近値は cars only
- EU27の単一公式行があるのは直近PDFだけ
- 脚注参照と相手先名の混入


## owid

**`recipes/owid/energy_data`**

- country 列に集計値が混在（**最重要**）
- 国名の表記揺れ
- 100% にならない構成比
- share と consumption の単位の違い
- 集計値 World の扱い
- データ遅延（IEA/BP の更新サイクル）
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


## un_wup

**`recipes/un_wup/urbanization_ranking`**

- 「Cities and Towns %」は従来の都市人口率とは別物（最重要）
- 集計地域の除外は種別コード row[7]==4 で行う
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
- 国は1回あたり3か国まで
- 値は自国通貨。ドルではない
- Rev.3 と Rev.4 で収録国・年がまるで違う
- Output と Value added を混同しない


## unwto

**`recipes/unwto/tourism_statistics`**

- シートは "Data"。1枚目は "Overview"（説明文だけ）。
- 「観光収入」は3指標が同じ表に混在する。
- `partner_area_label` の扱いはドメインで変わる。
- 1995年から。1990年は無い。
- 単位は million US dollars。
- 中国は `China`。香港・マカオ・台湾は別行
- 世界計の行は無い。
- ダウンロードに User-Agent が要る。


## usgs

**`recipes/usgs/mineral_production`**

- ★`e`（推定値）付きの国は、数値が次の行に折り返す
- ボーキサイト表はアルミナ生産と交互配置で列がズレる
- `W`（企業秘匿）・`—`（該当なし）


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
- TWN（台湾）を含むと多国一括クエリが 4xx になる（2026-05-23 検証）


## worldsteel

**`recipes/worldsteel/crude_steel`**

- "生産"と"消費(見かけ消費)"を混同しない
- 同名の別テーブルを拾わない（SSY2002）
- 列は空白区切り・`pdftotext -layout` 必須
- EU27(2000)は EU15−UK＋新規加盟国

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
