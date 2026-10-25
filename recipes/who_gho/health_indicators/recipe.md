---
id: who_gho/health_indicators
api: who_gho
task: WHO Global Health Observatory の保健指標を国別に取得（肥満・喫煙・飲酒・寿命ほか）
items: [肥満BMI30, 過体重BMI25, 喫煙率, 飲酒量, 平均寿命, 乳児死亡率, 医師数 ほか約3,100指標]
tags: [who, gho, odata, health, obesity, ncd, country-level, rest-api, no-auth]
summary: WHO GHO の OData API から保健指標を取る。世界銀行WDIの保健指標は定義が違うことがあるので一次を取る
verified_at: 2026-10-26
complexity: easy
auth_required: false
gotcha_count: 5
---

# who_gho / health_indicators

## 何をする

WHO Global Health Observatory（GHO）の OData API から、国別・年別の保健指標を取る。
指標は `GET /api/Indicator` の件数で 2026-09-15 に 3,099、2026-10-26 に 3,102（増減する）。認証不要。
最終年は指標ごとに違う（例: 肥満 `NCD_BMI_30C` は2024年まで）。年は取得した値で確かめる。

## API情報

- ベース: `https://ghoapi.azureedge.net/api/`
- 指標一覧: `GET /api/Indicator` → `IndicatorCode` / `IndicatorName`
- データ: `GET /api/<IndicatorCode>?$filter=...`
- 形式: OData JSON（`{"value":[...]}`）
- 認証: 不要

## 範囲（何が入って何が落ちるか）
- fetch.py は常に `SpatialDimType eq 'COUNTRY'` を付ける。`--countries` を空にしても**地域・所得グループ・世界の行は入らない**
  （肥満2022年 男女計では COUNTRY 199 / REGION 6 / WORLDBANKINCOMEGROUP 4 / GLOBAL 1）。metadata の `scope` と `filter` に書く。
- 同じ国・年に複数行（性別・年齢群などの次元が残っている）なら止まる（旧版は後勝ちで1つに潰していた）。`--sex ''` で性別を絞らないと、性別のある指標では止まる。
- `NumericValue` が空の行は落とし、件数を metadata の `skipped_null_rows` に書く。値が返らなかった `--countries` の国は `missing_countries` に書く。
- `@odata.nextLink`（ページ送り）が返れば追う。2026-10-26 には 14,112 行の `WHOSIS_000001` でも返らなかった。
- `--list` は一致を40件まで表示し、超えると「ほかN件」と出す。

## 使い方

```bash
python fetch.py --list obes                                   # 指標をキーワードで探す
python fetch.py --indicator NCD_BMI_30C --countries USA,ARE,DNK,PHL
python fetch.py --indicator NCD_BMI_30C --countries JPN --sex SEX_MLE
```

## よく使う指標コード

| 用途 | コード | 備考 |
|---|---|---|
| **肥満（BMI≥30・粗率）** | `NCD_BMI_30C` | ★教材の「肥満」はこれ |
| 肥満（BMI≥30・年齢調整） | `NCD_BMI_30A` | 国際比較で年齢構成を揃えたいとき |
| 過体重（BMI≥25） | `NCD_BMI_25C` | 肥満より大幅に高い値になる |
| 平均寿命 | `WHOSIS_000001` | |
| 喫煙率 | `M_Est_smk_curr_std` | |

## ハマり所

### 1. 性別の次元コードに接頭辞が付く（最重要）
`Dim1 eq 'BTSX'` → **0件。しかもHTTP 200で空配列が返る**（`NCD_BMI_30C`・`NCD_BMI_30A` で 2026-10-26 に再確認。性別の次元が別のコードの指標もあり得るので、0件ならまずここを疑う）。
正しくは **`Dim1 eq 'SEX_BTSX'`**（男女計）／`SEX_MLE`／`SEX_FMLE`。
2026-09-15 にこれで「WHOにデータが無い」と判断しかけた。**フィルタが違っても
エラーにならず空になる**のが厄介。件数0なら、まずフィルタを疑う。

### 2. 「肥満」と「過体重」は別物。WDIと混同しない
World Bank WDI の `SH.STA.OWAD.ZS` は **Prevalence of overweight (% of adults)**（過体重＝BMI≥25）。
アメリカで **72.4%（2022年。World Bank API で 2026-10-26 取得）**。一方 WHO の肥満 `NCD_BMI_30C`（BMI≥30・粗率・18歳以上・男女計）は **41.8%（2024年）**
（年齢調整 `NCD_BMI_30A` は 41.0%）。年も違うので、並べるときは年をそろえる。
「肥満（BMIが30以上）」と書かれた図は後者。名前が似ていて、どちらも
「それらしい値」を返すので、定義を確認せずに使うと誤る。

### 3. 国コードは ISO3。地域集計も同じ次元に混ざる
`SpatialDimType` が `COUNTRY` 以外（`REGION`・`WORLDBANKINCOMEGROUP`・`GLOBAL`）の行がある。
fetch.py は国だけを取る（`SpatialDimType eq 'COUNTRY'` を常に付ける）。地域集計が要るなら別に取る。

### 4. $filter の or は括弧でくくる
`SpatialDim eq 'A' or SpatialDim eq 'B' and Dim1 eq 'X'` は優先順位で崩れる。
`(SpatialDim eq 'A' or SpatialDim eq 'B') and Dim1 eq 'X'` と書く。

### 5. 推計値なので改定される
2008年のアメリカの肥満率（`NCD_BMI_30C`・男女計）は、2026-10-26 取得の WHO 推計で 35.1%。
古い資料に載っている値とは合わないことがある。**過去の年の値も改定される**。
古い資料と数値が合わなくても、それは取得の失敗ではない。照合するなら資料の側の版・取得時期を先に確かめる。
