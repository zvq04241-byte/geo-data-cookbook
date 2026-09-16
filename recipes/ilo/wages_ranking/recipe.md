---
id: ilo/wages_ranking
api: ilo
task: 製造業 時間当たり賃金 国別ランキング（ILOSTAT, SDMX）
tags: [ilo, ilostat, sdmx, wages, earnings, manufacturing, ranking, country-level, rest-api, sdmx-csv]
summary: ILO ILOSTAT の SDMX REST から製造業の時間賃金を取得し、通貨(USD/PPP/LCU)別に国別上位N国を取得
items: [USD, PPP, LCU]
verified_at: 2026-06-08
complexity: medium
auth_required: false
gotcha_count: 8
pattern: live-rest-api + sdmx-csv + accept-negotiation + derived-computation
---

# ilo / wages_ranking

## 何をする
ILO ILOSTAT の SDMX REST から製造業（ECO_AGGREGATE_MAN）の**時間当たり賃金**を取得し、
通貨（USD/PPP/LCU）別に国別ランキング上位N国を CSV + metadata.json に出力する。
時間給を直接報告していない国は「月給 ÷ (週実働時間 × 52/12)」で換算（週時間も無ければ月給/173h）。

## API情報
- **出典**: ILO ILOSTAT — SDMX REST
- **ベース**: `https://sdmx.ilo.org/rest/data/ILO`
- **形式**: SDMX-CSV（`Accept: application/vnd.sdmx.data+csv;version=1.0.0`）
- **認証**: 不要
- **使用データフロー**:
  - `DF_EAR_EHRA_SEX_ECO_CUR_NB`（時間給）/ `DF_EAR_EMTA_SEX_ECO_CUR_NB`（月給）/ `DF_HOW_TEMP_SEX_ECO_NB`（週労働時間）

## 使い方
```bash
# USD・上位20・2018年以降の最新値
python fetch.py --currency USD --top-n 20 --output-dir ./output

# PPP 調整・対象国を限定
python fetch.py --currency PPP --countries LUX,CHE,USA,JPN --output-dir ./output
```
出力: `output/YYYYMMDD_ilostat_wages_manufacturing_usd_top20.csv`
（Rank,Area(ISO3),Currency,Value,Year,Source,Unit）＋ metadata.json

## ハマり所（重要）

### 1. SDMX-CSV は Accept ヘッダで要求する（最重要）
`Accept: application/vnd.sdmx.data+csv;version=1.0.0` を付けないと **SDMX-ML(XML) が返り**、
CSV パースが全滅する。URL に format パラメータは無く、コンテンツネゴシエーションで決まる。

### 2. データフローごとに次元数が違う＝キーのドット数が違う
時間給/月給は **CUR 次元あり**でキー末尾が `...ECO_AGGREGATE_MAN.?`（ドット有り）、
週労働時間は **CUR 次元なし**で `...ECO_AGGREGATE_MAN?`（ドット無し）。
ドット数=次元数。間違えると 404 か空応答になる。`build_urls()` の通り使い分ける。

### 3. 国コードの連結は「+」
SDMX キーでは対象国を **`+` 連結**（`LUX+CHE+USA+...`）。
World Bank の `;`、Comtrade の `,` とは違う。API ごとに区切り文字が異なる典型。

### 4. 通貨は URL でなく CUR 列で後フィルタ
データフローは全通貨を返す。`CUR == CUR_TYPE_USD/PPP/LCU` で**行を絞る**（URL パラメータではない）。
`latest_by_country(rows, cur_filter)` 参照。

### 5. 最新年は国ごとに異なる（全行同年ではない）
`TIME_PERIOD` の最新年は USA 2024 / ISL 2020 / DEU 2022 …とバラバラ。
出力は単一年ではないので、検証で `year_value`（全行同年）を使ってはいけない。

### 6. 時間給は直接報告が約4割・残りは換算
50主要国中、時間給を直接報告するのは約21か国。残りは
**月給 ÷ (週時間 × 52/12)**、週時間も無ければ **月給/173h** で換算する。
値は手法依存になるため `Source` 列に種別（direct / monthly_div_hours / monthly_div_173）を残す。

### 7. 空データの判定は本文先頭の "No data"
該当データが無いとき ILO は HTTP 200 で本文先頭に "No data" を返すことがある。
`"No data" in r.text[:100]` で空判定する（ステータスコードだけ見ると見逃す）。

### 8. LCU は国際比較に不向き
LCU（現地通貨）は通貨単位がバラバラで横比較できない。教材の国際比較では USD か PPP を使う。

## 効くケース
- 製造業 時間賃金 × 通貨 × 国別ランキング上位N
- `--countries` で対象国を限定（既定は主要50か国）
- `--currency PPP` で購買力平価調整

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 全産業平均 | ECO_AGGREGATE_TOTAL に変更した別レシピ | 未作成 |
| 1か国の年次推移 | `ilo/wages_timeseries` | 未作成 |
| 性別内訳 | SEX_T 以外を使う別レシピ | 未作成 |
| 失業率・労働力率 | 別データフロー（DF_UNE_* 等） | 未作成 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数）
- ✅ ファイルI/O は `encoding="utf-8"`、CSV書き込みは `newline="\n"`
- ✅ 構造化例外 `DataFetchError`（source/url/kind）
- ✅ SDMX 取得3回リトライ、`httpx.Timeout(read=120)`（SDMXは応答が重い）
- ✅ metadata.json に 3 ソースURL / SHA256 / fetched_at / row_count / derivation 内訳
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）
- ✅ APIキー不要（漏洩リスクなし）

## このレシピを使うLLMへのヒント
1. **SDMX は Accept ヘッダで CSV を要求**し、URL の「ドット数＝次元数」を厳密に合わせる
2. **区切り文字は API ごとに違う**（ILO=`+` / WB=`;` / Comtrade=`,`）— 既存レシピで確認してから書く
3. **派生値は手法を必ず記録**（直接/換算）— 値が方法依存なら出典列を残す
4. **reference は厳密順位でなく不変条件**（高賃金国の topN 包含・低賃金国の非混入・降順）で採点する
