---
id: who_gho/health_indicators
api: who_gho
task: WHO Global Health Observatory の保健指標を国別に取得（肥満・喫煙・飲酒・寿命ほか）
items: [肥満BMI30, 過体重BMI25, 喫煙率, 飲酒量, 平均寿命, 乳児死亡率, 医師数 ほか3,099指標]
tags: [who, gho, odata, health, obesity, ncd, country-level, rest-api, no-auth]
summary: WHO GHO の OData API から保健指標を取る。世界銀行WDIの保健指標は定義が違うことがあるので一次を取る
verified_at: 2026-09-15
complexity: easy
auth_required: false
gotcha_count: 5
---

# who_gho / health_indicators

## 何をする

WHO Global Health Observatory（GHO）の OData API から、国別・年別の保健指標を取る。
**3,099指標**。認証不要。2024年まで入っているものが多い。

## API情報

- ベース: `https://ghoapi.azureedge.net/api/`
- 指標一覧: `GET /api/Indicator` → `IndicatorCode` / `IndicatorName`
- データ: `GET /api/<IndicatorCode>?$filter=...`
- 形式: OData JSON（`{"value":[...]}`）
- 認証: 不要

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
`Dim1 eq 'BTSX'` → **0件。しかもHTTP 200で空配列が返る**。
正しくは **`Dim1 eq 'SEX_BTSX'`**（男女計）／`SEX_MLE`／`SEX_FMLE`。
2026-09-15 にこれで「WHOにデータが無い」と判断しかけた。**フィルタが違っても
エラーにならず空になる**のが厄介。件数0なら、まずフィルタを疑う。

### 2. 「肥満」と「過体重」は別物。WDIと混同しない
World Bank WDI の `SH.STA.OWAD.ZS` は **Prevalence of overweight（BMI≥25）**。
アメリカで **72.4%**。一方 WHO の肥満（BMI≥30）は **41.8%**。
共通テストの「肥満（BMIが30以上）」は後者。名前が似ていて、どちらも
「それらしい値」を返すので、定義を確認せずに使うと誤る。

### 3. 国コードは ISO3。地域集計も同じ次元に混ざる
`SpatialDimType` が `COUNTRY` 以外（`REGION`・`WORLDBANKINCOMEGROUP` 等）の行がある。
国だけ欲しいなら `SpatialDimType eq 'COUNTRY'` を足す。

### 4. $filter の or は括弧でくくる
`SpatialDim eq 'A' or SpatialDim eq 'B' and Dim1 eq 'X'` は優先順位で崩れる。
`(SpatialDim eq 'A' or SpatialDim eq 'B') and Dim1 eq 'X'` と書く。

### 5. 推計値なので改定される
2008年のアメリカの肥満率は、原問（2013年本試の表）で 33.7%、現在のWHO推計で 35.1%。
**過去の年の値も改定される**。原問と数値が合わなくても、それは取得の失敗ではない。
