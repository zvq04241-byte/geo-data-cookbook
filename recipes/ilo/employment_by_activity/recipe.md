---
id: ilo/employment_by_activity
api: ilo
task: 産業別就業者数・就業構造（ISIC大分類／3部門）を国別に取得
items: [ISIC4 A〜U 大分類, 3部門(農業/工業/サービス), 第3次産業の4区分(流通・消費・生産・社会)]
tags: [ilo, ilostat, sdmx, employment, industry, isic, tertiary, country-level, rest-api, sdmx-csv, no-auth]
summary: ILOSTAT の DF_EMP_TEMP_SEX_ECO_NB から産業別就業者を取る。第3次産業の業種別構成比（Singelmann型4区分）も算出
verified_at: 2026-09-15
complexity: medium
auth_required: false
gotcha_count: 10
pattern: live-rest-api + sdmx-csv + accept-negotiation + derived-aggregation
---

# ilo / employment_by_activity

## 何をする

ILOSTAT の `DF_EMP_TEMP_SEX_ECO_NB`（Employment by sex and economic activity）から
国別・年別の産業別就業者数を取り、

- **第1〜3次産業の構成比**（`ECO_SECTOR_AGR/IND/SER`）
- **ISIC4 大分類 A〜U ごとの就業者数・割合**
- **第3次産業の業種別構成比**（流通関連／消費関連／生産関連／社会関連。下表の束ね方）

を出す。共通テストの「第3次産業就業者割合と業種別構成比」「労働人口に占める金融・保険業の
従業者割合」はこれで作れる。

## API情報

- ベース: `https://sdmx.ilo.org/rest`
- データフロー: `ILO,DF_EMP_TEMP_SEX_ECO_NB`
- 形式: SDMX-CSV（`Accept: application/vnd.sdmx.data+csv;version=1.0.0`）
- 認証: 不要

### キーは5次元

```
REF_AREA . FREQ . MEASURE . SEX . ECO
JPN+CHE+ARE+HUN . A . . SEX_T .        ← 全件は空で置く
```

## 使い方

```bash
python fetch.py --countries JPN,CHE,ARE,HUN --mode tertiary   # 第3次産業の4区分
python fetch.py --countries JPN --mode isic                   # ISIC4 大分類すべて
python fetch.py --countries JPN,CHE --mode sector             # 農業/工業/サービス
python fetch.py --countries JPN --isic K                      # 金融・保険業だけ
```

## 第3次産業の4区分（ISIC Rev.4 の束ね方）

教材で使われる Singelmann 型の区分に合わせる。**この対応は本レシピの取り決め**であり、
ILOSTAT 側にこの集計は無い。原問と突き合わせるときは注記すること。

| 区分 | ISIC Rev.4 |
|---|---|
| 流通関連サービス（卸小売・運輸・通信など） | G 卸売小売 / H 運輸保管 / J 情報通信 |
| 消費関連サービス（飲食・宿泊・家事など） | I 宿泊飲食 / R 芸術娯楽 / S その他サービス / T 家事 |
| 生産関連サービス（金融・不動産など） | K 金融保険 / L 不動産 / M 専門技術 / N 管理支援 |
| 社会関連サービス（教育・保健・公務など） | O 公務 / P 教育 / Q 保健福祉 |

**★古い年は ISIC Rev.3 で入っている。同じデータフローに同居する。**
2013年本試Ｂ第2問（統計年次2008年）の原問は Rev.3 で作られており、区分名と括弧書きは
本レシピと同じだが**中身が違う**。

| 区分 | ISIC Rev.3 | ISIC Rev.4 |
|---|---|---|
| 流通関連 | G 卸売小売 / I 運輸・倉庫・通信 | G / H 運輸保管 / J 情報通信 |
| 消費関連 | H ホテル・レストラン / P 家事 | I 宿泊飲食 / R 芸術娯楽 / S その他 / T 家事 |
| 生産関連 | J 金融 / K 不動産・賃貸・事業サービス | K 金融保険 / L 不動産 / M 専門技術 / N 管理支援 |
| 社会関連 | L 公務 / M 教育 / N 保健社会事業 | O 公務 / P 教育 / Q 保健福祉 |
| その他 | O その他サービス / Q 治外法権 | U 治外法権 |

消費関連が Rev.3 では H+P の2つしかないため小さく出る。
原問①（デンマーク）の消費関連が **3.9%** と極端に低いのはこれが理由で、
Rev.4 で作り直すと 11.2% になる。**同名の区分でも数字を並べて比べない。**

検証: UAE 2008年を Rev.3 で組み直すと 71.2% / 流通32.9 消費23.5 生産15.7 社会23.0 で、
原問③の 72.8 / 32.2 / 23.0 / 15.4 / 22.5 とよく合う。対応表は正しい。

## ハマり所

### 1. 次元数がデータフローで違う（賃金は4、就業構造は5）
`ilo/wages_ranking` は `REF_AREA.SEX.ECO.CUR` の4次元。こちらは **5次元**。
`JPN.SEX_T.` で投げると
`422 Not enough key values in query, expecting 5 got 3` が返る。
**次元は `/dataflow/ILO/<DF名>?references=all` の `<structure:Dimension id= position=>` で確認する。**

### 2. 構造の問い合わせは JSON だと 406。XML なら通る
`Accept: application/vnd.sdmx.structure+json;version=1.0.0` → **406 Not Acceptable**。
`Accept: application/xml` → 200（dataflow一覧は7.2MB・1,212本）。
データは SDMX-CSV、構造は XML と使い分ける。

### 3. 最新年が国ごとに違う
2026-09-15 時点で スイス・UAE・ハンガリーは 2025年、**日本は 2023年**。
「同じ年で揃える」か「各国の最新年」かを決めてから表にする。揃えないと年の混在になる。

### 4. 分母は `ECO_ISIC4_TOTAL` と `ECO_SECTOR_TOTAL` の2つがある
ISIC4 の割合を出すなら `ECO_ISIC4_TOTAL`、3部門なら `ECO_SECTOR_TOTAL`。
混ぜると合計が100%にならない。`ECO_AGGREGATE_TOTAL` もあり計3系統。

### 5. 国コードの連結は「+」
SDMX の流儀。World Bank は `;`、Comtrade は `,`。

### 6. 「労働人口に占める割合」と「就業者に占める割合」は別物
このデータフローは **就業者（employment）**。失業者を含む労働力人口が分母の設問
（2020年本試Ｂ第2問問6「労働人口に占める金融・保険業の従業者割合」）とは定義が
わずかにずれる。原問の値と数％違っても、それは誤りではない。

### 7. ISIC4 の U（治外法権機関）と X（分類不能）は小さいが 0 ではない
4区分に束ねるとき取りこぼすと合計が100%に届かない。`その他` として明示すること。
8. **★同じデータフローに ISIC Rev.3 と Rev.4 が同居する。** 古い年は Rev.3 しかない。
   `ECO_ISIC4_*` だけ見ていると古い年が**黙って0件**になる（`--year 2008` で「該当年なし」）。
   上の対応表で Rev.3 側も組む。
9. **★全数でない系列が混じる。** フィリピンの2008年 ISIC3 は `ECO_AGGREGATE_TOTAL` が
   **286万人**。実際の就業者は約3,400万人で、**12分の1**しかない。
   気づかずに構成比を出すと生産関連が44.3%（実際は1割未満）という値になる。
   **`ECO_AGGREGATE_TOTAL` を、その国のその年の就業者総数と必ず突き合わせる。**
10. **国によって欠ける大分類がある。** フィリピンの2008年 Rev.3 には L（公務）・P（家事）・
   Q が無い。デンマークの2008年は Rev.3 が1件も無く Rev.4 のみ。
   分母が足りないまま構成比にすると、残りの区分が一斉に膨らむ。
