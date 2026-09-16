---
id: eurostat/air_flow
api: eurostat
task: 国際航空 旅客／貨物 国ペアフロー（欧州・西アジア・アフリカ間）
items: [pax, cargo]
tags: [eurostat, aviation, flow, od, passengers, cargo, europe, west-asia, africa, geojson, choropleth-base, no-auth]
summary: Eurostat avia_par(旅客)/avia_gor(貨物) を空港ペア→国ペアに集約し、欧州・西アジア・アフリカ間の航空フローを得る
verified_at: 2026-06-09
complexity: medium
auth_required: false
data_size_mb: 0   # ライブAPI(JSON-stat)
gotcha_count: 8
pattern: eurostat-jsonstat-api + airport-pair-to-country + great-circle-flowmap
---

# eurostat / air_flow

## 何をする
Eurostat の空港ペア統計から、**報告国（欧州諸国＋トルコ）↔相手国** の国際航空 旅客／貨物を
**国ペア**に集約し、欧州・西アジア・アフリカ間の流動を CSV / GeoJSON 化する。
出題範囲が「ヨーロッパ・西アジア・アフリカ」の教材の図に最適（全件 Eurostat 公式・最新年）。

## API情報
- **出典**: Eurostat（欧州委員会）。無料・無認証・JSON-stat。
- **旅客**: `avia_par_<cc>`（tra_meas=`PAS_CRD`, unit=`PAS`）
- **貨物**: `avia_gor_<cc>`（tra_meas=`FRM_LD_NLD`, unit=`T`）
- **URL例**: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_par_de?format=JSON&lang=EN&freq=A&unit=PAS&tra_meas=PAS_CRD&time=2024`
- **報告国**: EU27＋EFTA＋候補国（**トルコ含む**）。相手国は域外（西アジア・アフリカ等）を網羅。
- **最新年**: 2024（更新は年1回程度。無ければ前年にフォールバック）。

## 使い方
```bash
python fetch.py --measure pax   --year 2024 --output-dir ./output
python fetch.py --measure cargo --year 2024 --output-dir ./output
```
出力: `YYYYMMDD_eurostat_airflow_{pax|cargo}.csv`（route,a_iso,b_iso,region_pair,値）＋ metadata.json。
地図化する場合は各国の代表点（Natural Earth admin_0 の `representative_point()`、Eurostat `UK→GB`/`EL→GR`）を使い、
線幅∝値、`pyproj.Geod.npts` で測地線弧にする。

## ハマり所
1. **value のキーは「位置インデックス(数値)」**。`"DE_EDDF_TR_LTBA"` のコード文字列ではない。
   `dimension.airp_pr.category.index = {コード:位置}` を **逆引き(`pos2code={位置:コード}`)** して
   コードを得てから `split("_")` する。これを怠ると **features=0(空)** になる（最頻バグ）。
2. **報告国"内"は同一国ペアの空港ペアを sum**。空港ペアごとに max を取ると**多空港国を大幅に過小計上**
   （例 DE–EG が Frankfurt–Cairo だけになり 0.47M、真値 3.69M）。
3. **報告国"間"は max**。同一国ペアが2つの報告国に出る（DE→TR と TR→DE）。sum すると**二重計上**。
   ＝「**報告国内 sum・報告国間 max**」を厳守。
4. **region_pair は地域順（Europe<West Asia<Africa）で正規化**。ISOアルファベット順で組むと
   `Europe-West Asia` と `West Asia-Europe` が混在する。
5. **旅客は /1000 して「千人」**。生の passengers をそのまま千人扱いすると **×1000 の単位誤り**。
6. **国内線(報告国==相手国)を除外**。`avia_par_tr` にはトルコ国内線が大量に入る（〜9000万人規模）。
7. **地政学的に成立しない路線は0扱い**（流線データ全般の検証項目）。
   例: カタール封鎖2017–2021 → カタール⇔{サウジ,UAE,バーレーン,エジプト}は2019年0。
   アブラハム合意(2020/8)前 → イスラエル⇔UAE/サウジ/バーレーンの直行便は0。
   サウジ⇔イラン(2016–2023断交)直行便0。**封鎖・国交なしのペアが非0なら誤り**。
8. **月次(freq=M)の time コードは `2024-01` 形式（YYYY-MM）**。年次の感覚で `2024M01` を渡すと
   **HTTP 400 "Invalid value for 'time' parameter"**。12か月まとめて取るなら
   `sinceTimePeriod=2024-01&untilTimePeriod=2024-12` が確実（2026-06-10 実証,
   `eurafrica_quiz_p000/scripts/fetch_monthly.py`）。月次は季節性教材（観光×気候の判別図）に使える。

## 図版生成の検証ゲート（validate項目の補助）
- features 件数 ≥ 想定（空でないか）／単位スケール（旅客 max < 100,000 千人＝×1000誤り検出）／
  region_pair 正規化（逆順ペアが無いか）／多空港合算（既知ペアの値が参照と一致するか）／
  日本語フォント埋込（`FontProperties(fname=ipaexg.ttf)`＋`pdf.fonttype=42`、文字化け警告0）。

## 実験知見
2026-06-09。ローカルモデル(qwen3-coder-next)単発生成はハマり所1で features=0、ハマり所2で過小計上、
ハマり所4/5を誤った。**客観ゲート＋具体フィードバック1回で参照値に一致**（DE–EG 3691.8 vs 3691.9）。
＝モデル非依存に効く「勝ちパターン＋検証ゲート」をレシピ化したもの。

## 限界
報告国＝欧州＋トルコのため、**欧州・トルコが絡まない湾岸⇔アフリカ直行**（例 サウジ⇔エジプト、UAE⇔ケニア）は
非収録。網羅したい場合は各空港年次報告で補完する。
