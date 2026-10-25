---
id: eurostat/air_flow
api: eurostat
task: 国際航空 旅客／貨物 国ペアフロー（欧州・西アジア・アフリカ間）
items: [pax, cargo]
tags: [eurostat, aviation, flow, od, passengers, cargo, europe, west-asia, africa, geojson, choropleth-base, no-auth]
summary: Eurostat avia_par(旅客)/avia_gor(貨物) を空港ペア→国ペアに集約し、欧州・西アジア・アフリカ間の航空フローを得る
verified_at: 2026-10-26
complexity: medium
auth_required: false
data_size_mb: 0   # ライブAPI(JSON-stat)
gotcha_count: 9
pattern: eurostat-jsonstat-api + airport-pair-to-country + great-circle-flowmap
---

# eurostat / air_flow

## 何をする
Eurostat の空港ペア統計から、**報告国（既定34か国。下記）↔相手国** の国際航空 旅客／貨物を
**国ペア**に集約し、欧州・西アジア・アフリカ間の流動を CSV / GeoJSON 化する。
**少なくとも一方が報告国である国ペアだけ**が入る（全件 Eurostat 公式）。範囲は出力の `scope`（CSV の列と metadata）に書き出す。

## API情報
- **出典**: Eurostat（欧州委員会）。無料・無認証・JSON-stat。
- **旅客**: `avia_par_<cc>`（tra_meas=`PAS_CRD`, unit=`PAS`）
- **貨物**: `avia_gor_<cc>`（tra_meas=`FRM_LD_NLD`, unit=`T`）
- **URL例**: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_par_de?format=JSON&lang=EN&freq=A&unit=PAS&tra_meas=PAS_CRD&time=2024`
- **報告国（既定 `DEFAULT_REPORTERS` 34か国）**: EU27＋EFTA＋加盟候補国のうち、Eurostat に表があるもの。
  2026-10-26 に全候補を API で確かめた（`references/reporters_probe_20261026.csv`、再現は `probe_reporters.py`）。
  - 表が無い（HTTP 404 "not available for dissemination"）: チェコ・リヒテンシュタイン・アルバニア・ウクライナ・モルドバ・ジョージア・コソボ
  - 英国（`avia_par_uk`）: 表はあるが2020年以降は空（2019年まで値がある）。既定に入れない
  - ボスニア・ヘルツェゴビナ: 2024年が空で2023年はある → 前年値で代用（metadata の `reporters_used` に年が残る）
  - 取れなかった報告国は metadata の `reporters_missing` と `scope` に出る。**通信・サーバ側の失敗は部分集計を出さずに止める。**
- **相手国の地域**: 国連 M49（`references/m49_overview.csv`）。欧州＝Region Europe（ロシアを含む）、
  西アジア＝Sub-region Western Asia、アフリカ＝Region Africa。M49 から動かす国は `fetch.py` の `MOVED` に理由つき
  （キプロス→欧州、イラン→西アジア、コソボ→欧州）。3地域外の相手（米国・中国など）は落とし、落とした値を metadata の `dropped_partner_value` に出す。
- **最新年**: 2024（2026-10-26 に `time=2025` が空であることを確認。`references/spot_checks_20261026.csv`）。空なら前年にフォールバック。

## 使い方
```bash
python fetch.py --measure pax   --year 2024 --output-dir ./output
python fetch.py --measure cargo --year 2024 --output-dir ./output
```
出力: `YYYYMMDD_eurostat_airflow_{pax|cargo}.csv`（route,a_iso,b_iso,a_region,b_region,region_pair,値,scope）＋ metadata.json（`scope`・`reporters_requested`・`reporters_used`・`reporters_missing`・`dropped_partner_value`）。
地図化する場合は各国の代表点（Natural Earth admin_0 の `representative_point()`、Eurostat `UK→GB`/`EL→GR`）を使い、
線幅∝値、`pyproj.Geod.npts` で測地線弧にする。

## ハマり所
1. **value のキーは「位置インデックス(数値)」**。`"DE_EDDF_TR_LTBA"` のコード文字列ではない。
   `dimension.airp_pr.category.index = {コード:位置}` を **逆引き(`pos2code={位置:コード}`)** して
   コードを得てから `split("_")` する。これを怠ると **features=0(空)** になる（最頻バグ）。
2. **報告国"内"は同一国ペアの空港ペアを sum**。空港ペアごとに max を取ると**多空港国を大幅に過小計上**
   （2024年 DE–EG: 21空港ペアの合計 3,691,928人。最大の1ペア＝デュッセルドルフ–フルガダ 466,806人だけになる。
   記録 `references/spot_checks_20261026.csv`）。
3. **報告国"間"は max**。同一国ペアが2つの報告国に出る（DE→TR と TR→DE）。sum すると**二重計上**。
   ＝「**報告国内 sum・報告国間 max**」を厳守。
4. **region_pair は地域順（Europe<West Asia<Africa）で正規化**。ISOアルファベット順で組むと
   `Europe-West Asia` と `West Asia-Europe` が混在する。
5. **旅客は /1000 して「千人」**。生の passengers をそのまま千人扱いすると **×1000 の単位誤り**。
6. **国内線(報告国==相手国)を除外**。`avia_par_tr` にはトルコ国内線が大量に入る（2024年 TR–TR 空港ペア合計 93,513,819人）。
7. **報告国が絡まない国ペアは、データに現れないだけ**。湾岸諸国どうし・西アジア⇔アフリカ（例 サウジ⇔エジプト）は
   どちらも報告国でないので行が無い。行が無いことを「路線が無い」「0」と読まない。
   外交関係から「この組は0のはず」を検証規則にしない（直行便・乗継・空港ペアの定義で値は変わり、確かめていない）。
8. **月次(freq=M)の time コードは `2024-01` 形式（YYYY-MM）**。年次の感覚で `2024M01` を渡すと
   **HTTP 400 "Invalid value for 'time' parameter"**。12か月まとめて取るなら
   `sinceTimePeriod=2024-01&untilTimePeriod=2024-12` が確実（2026-06-10 実証）。
   月次は季節性を見るのに使える。
9. **地域の国集合を手で並べない**。旧版は欧州の集合にロシアが無く、2024年の RU–TR（11,839千人。トルコの報告で2番目の大きさ）が
   黙って落ちていた。M49 の表から引き、ナミビアの ISO2 "NA" が欠測扱いで空になる点も `fetch.py` で補っている。

## 図版生成の検証ゲート（validate項目の補助）
- features 件数 ≥ 想定（空でないか）／単位スケール（旅客 max < 100,000 千人＝×1000誤り検出。2024年の最大は DE–TR 20,073千人で、
  /1000 を忘れると 2,000万台になる）／
  region_pair 正規化（逆順ペアが無いか）／多空港合算（既知ペアの値が参照と一致するか）／
  日本語フォント埋込（`FontProperties(fname=ipaexg.ttf)`＋`pdf.fonttype=42`、文字化け警告0）。

## 実験知見
2026-06-09。ローカルモデル(qwen3-coder-next)1本の単発生成（n=1）はハマり所1で features=0、ハマり所2で過小計上、
ハマり所4/5を誤った。検証ゲート＋具体フィードバック1回で、参照値（DE–EG 3,691.9千人。2026-10-26 に API で再計算して一致）
に合った。モデル出力の値そのものは記録が残っていない。他モデルでは試していない。

## 限界
報告国は既定34か国（上記）。**報告国が絡まない組**（例 サウジ⇔エジプト、UAE⇔ケニア）と、
**表の無い国・英国だけが報告する組**は非収録。英国がからむ組は、相手側の報告国の値（例 UK–TR はトルコの報告）しか入らない。
欧州域内と3地域外の相手は意図して除く。図に使うときは `scope` を注記に写す。
