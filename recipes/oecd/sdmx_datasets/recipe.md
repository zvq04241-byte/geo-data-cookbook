---
id: oecd/sdmx_datasets
api: oecd
task: OECD Data Explorer（SDMX）から任意のデータフローを取得
items: [税収Revenue Statistics, 国籍取得Acquisition of nationality, 国民経済計算, 教育, 雇用 ほか1,548データフロー]
tags: [oecd, sdmx, rest-api, no-auth, sdmx-csv, revenue-statistics, migration, tax]
summary: OECD の新しい SDMX エンドポイントから CSV で取る。データフロー名にバージョン指定が必須という罠がある
verified_at: 2026-09-15
complexity: medium
auth_required: false
gotcha_count: 6
---

# oecd / sdmx_datasets

## 何をする

OECD Data Explorer の SDMX REST から、任意のデータフローを SDMX-CSV で取る。
**1,548データフロー**。認証不要。旧 stats.oecd.org は廃止済みで、こちらが現行。

## API情報

- データ: `https://sdmx.oecd.org/public/rest/data/<agency>,<dataflow>,<version>/<key>`
- 構造: `https://sdmx.oecd.org/public/rest/dataflow/<agency>/<dataflow>/latest?references=all`
- 一覧: `https://sdmx.oecd.org/public/rest/dataflow/all/all/latest`（8.9MB・XML）
- 形式: SDMX-CSV（`Accept: application/vnd.sdmx.data+csv;version=1.0.0`）

## 使い方

```bash
python fetch.py --list tax                        # データフローを探す
python fetch.py --dims OECD.CTP.TPS DSD_REV_COMP_OECD@DF_RSOECD   # 次元を見る
python fetch.py --agency OECD.CTP.TPS --flow DSD_REV_COMP_OECD@DF_RSOECD \
       --key "JPN+USA+DNK+FRA......." --start 2018
```

## 確認済みのデータフロー

### 税収（Revenue Statistics）— `OECD.CTP.TPS / DSD_REV_COMP_OECD@DF_RSOECD`
8次元 `REF_AREA.MEASURE.SECTOR.STANDARD_REVENUE.CTRY_SPECIFIC_REVENUE.UNIT_MEASURE.FREQ.TIME_PERIOD`

- `UNIT_MEASURE=PT_B1GQ` … **対GDP％**（`XDC`=自国通貨, `USD`, `PT_OTR_SECTOR`もある）
- `SECTOR=S13` … 一般政府（S1311中央・S1313地方・S1314社会保障基金）
- `STANDARD_REVENUE` … `T_2000`=社会保障負担 / `T_1000`=所得課税 / `T_5000`=消費課税 ほか75種

社会保障負担率・租税負担率（対GDP）はこれで出る。
**財務省の「国民負担率」は対国民所得**なので分母が違う。揃えるなら
`OECD.SDD.NAD / DSD_NAMAIN10@DF_TABLE1_INCOME` の国民所得と組む。

### 国籍取得 — `OECD.ELS.IMD / DSD_MIG@DF_MIG`
8次元 `REF_AREA.CITIZENSHIP.FREQ.MEASURE.SEX.BIRTH_PLACE.EDUCATION_LEV.UNIT_MEASURE`

- `MEASURE=B16` … **取得前の国籍別 国籍取得者数**
- `CITIZENSHIP` … 取得前の国籍（ISO3）。`_T` は合計なので上位N国を出すとき除く

## ハマり所

### 1. データのURLに `latest` は書けない（最重要）
```
.../data/OECD.ELS.IMD,DSD_MIG@DF_MIG/ITA..A.B16....         → 200（カンマ無しでよい）
.../data/OECD.ELS.IMD,DSD_MIG@DF_MIG,/ITA..A.B16....        → 200
.../data/OECD.ELS.IMD,DSD_MIG@DF_MIG,1.0/ITA..A.B16....     → 200
.../data/OECD.ELS.IMD,DSD_MIG@DF_MIG,latest/ITA..A.B16....  → 400 "Invalid version string provided"
```
`latest` は **構造**（`/dataflow/.../latest`）では使えるが、**データでは 400**。
バージョンを書かないか、`1.0` のように具体的な版を書く。

★2026-09-15、この 400 を「バージョン指定が必須」と読み違えた。実際は逆で、
`latest` を書いたことが原因。**エラー文面だけで原因を決めず、最小差分で切り分ける**こと。
最初の失敗時はキーのドット数も同時に違っていたため、`,1.0` を足して直ったように見えた。

### 2. 次元数はデータフローごとに違う。ドットの数を合わせる
`?references=all` で `<Dimension id= position=>` を読む。
TIME_PERIOD は最後の次元だがキーには含めない（`startPeriod` で指定）。

### 3. 単位は次元。URLでなく UNIT_MEASURE で絞る
対GDPが欲しいのに `XDC`（自国通貨）や `USD` の行が混ざる。後フィルタが要る。

### 4. 報告年が国ごとに違う
2026-09-15 時点で 日本は2021年、アメリカ・デンマーク・フランスは2022年。
「最新年」で表を作ると年が混在する。揃えるなら明示的に年を選ぶ。

### 5. 合計コードを上位N国に混ぜない
`CITIZENSHIP=_T`（合計）が同じ列に入っている。上位3か国を出すと1位が合計になる。

### 6. 一覧XMLは8.9MB
`dataflow/all/all/latest` は大きい。毎回取らず、必要なデータフロー名が分かったら
直接叩く。`--list` は一覧をキャッシュせずに毎回落とす作りなので多用しない。
