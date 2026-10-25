---
id: ilo/employment_by_activity
api: ilo
task: 産業別就業者数・就業構造（ISIC大分類／3部門）を国別に取得
items: [ISIC4 A〜U 大分類, 3部門(農業/工業/サービス), 第3次産業の4区分(流通・消費・生産・社会)]
tags: [ilo, ilostat, sdmx, employment, industry, isic, tertiary, country-level, rest-api, sdmx-csv, no-auth]
summary: ILOSTAT の DF_EMP_TEMP_SEX_ECO_NB から産業別就業者を取る。第3次産業の業種別構成比（Singelmann型4区分）も算出
verified_at: 2026-10-26
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

を出す。「第3次産業就業者割合と業種別構成比」「就業者に占める金融・保険業の割合」のような表が作れる。

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
python fetch.py --countries JPN --isic K                      # 金融・保険業だけ（Rev.4 の記号）
python fetch.py --countries ARE,PHL --mode tertiary --year 2008 # 古い年は Rev.3 で組む（自動）
```

出力の CSV には `denominator`（分母にした系列）と `isic_rev`（ISIC4 / ISIC3）が付く。metadata には
`scope`（指定した国のうち値のある国の数）・`dropped`（出せなかった国と理由）・`checks_by_country`
（欠けた大分類・大分類の積み上げと合計の差）が残る。`--year` を `--start` より前にすると `--start` を自動で下げる。

**分母はモードごとに1系統に固定する**（混ぜると合計が100%にならない。ハマり所4）:
| モード | 分母 | 無いとき |
|---|---|---|
| `tertiary` / `isic` / `--isic` | その国・年の ISIC の合計（Rev.4 なら `ECO_ISIC4_TOTAL`、Rev.3 なら `ECO_ISIC3_TOTAL`） | その国は出さず `dropped` に残す |
| `sector` | `ECO_SECTOR_TOTAL` | 同上 |

`tertiary` の列: 第3次産業就業者割合（第3次の合計÷分母）、4区分とその他（それぞれ第3次の合計に対する割合。足すと100%）、
`分類不能X_pct`（X÷分母。第3次には入れない）。「その他」は4区分に入らない第3次で、Rev.4 は U、Rev.3 は O・Q。

## 第3次産業の4区分（ISIC Rev.4 の束ね方）

教材で使われる Singelmann 型の区分に合わせる。**この対応は本レシピの取り決め**であり、
ILOSTAT 側にこの集計は無い。他の資料の値と突き合わせるときは注記すること。

| 区分 | ISIC Rev.4 |
|---|---|
| 流通関連サービス（卸小売・運輸・通信など） | G 卸売小売 / H 運輸保管 / J 情報通信 |
| 消費関連サービス（飲食・宿泊・家事など） | I 宿泊飲食 / R 芸術娯楽 / S その他サービス / T 家事 |
| 生産関連サービス（金融・不動産など） | K 金融保険 / L 不動産 / M 専門技術 / N 管理支援 |
| 社会関連サービス（教育・保健・公務など） | O 公務 / P 教育 / Q 保健福祉 |

**★古い年は ISIC Rev.3 で入っている。同じデータフローに同居する。**
2008年ごろの統計で作られた資料は Rev.3 で組まれていることがある。区分名と括弧書きが
本レシピと同じでも、束ねている大分類が**違う**（下表）。どちらの版で組んだかは、その資料の出典で確かめる。

| 区分 | ISIC Rev.3 | ISIC Rev.4 |
|---|---|---|
| 流通関連 | G 卸売小売 / I 運輸・倉庫・通信 | G / H 運輸保管 / J 情報通信 |
| 消費関連 | H ホテル・レストラン / P 家事 | I 宿泊飲食 / R 芸術娯楽 / S その他 / T 家事 |
| 生産関連 | J 金融 / K 不動産・賃貸・事業サービス | K 金融保険 / L 不動産 / M 専門技術 / N 管理支援 |
| 社会関連 | L 公務 / M 教育 / N 保健社会事業 | O 公務 / P 教育 / Q 保健福祉 |
| その他 | O その他サービス / Q 治外法権 | U 治外法権 |

消費関連が Rev.3 では H+P の2つしかないため、Rev.4 より小さく出る。**同名の区分でも、版の違う数字を並べて比べない。**
fetch.py は国・年ごとに版を選ぶ（Rev.4 の合計があれば Rev.4、無ければ Rev.3）。どちらで組んだかは `isic_rev` 列に出る。

2026-10-26 に fetch.py で組んだ値（第3次産業就業者割合 / 流通・消費・生産・社会・その他）:
- UAE 2008年（Rev.3 のみ）: 71.2% / 32.9・23.5・15.7・23.0・4.8
- デンマーク 2008年（Rev.4 のみ。Rev.3 は無い）: 74.0% / 32.3・9.7・15.8・41.9・0.2
対応表が他の資料と合うかは、1例が近いだけでは言えない。使うときは突き合わせた資料と差を記録する。

## ハマり所

### 1. 次元数がデータフローで違う（賃金は4、就業構造は5）
`ilo/wages_ranking` は `REF_AREA.SEX.ECO.CUR` の4次元。こちらは **5次元**。
`JPN.SEX_T.` で投げると
`422 Not enough key values in query, expecting 5 got 3` が返る。
**次元は `/dataflow/ILO/<DF名>?references=all` の `<structure:Dimension id= position=>` で確認する。**

### 2. 構造の問い合わせは JSON だと 406。XML なら通る
`Accept: application/vnd.sdmx.structure+json;version=1.0.0` → **406 Not Acceptable**。
`Accept: application/xml` → 200（dataflow一覧は 2026-10-26 に 7.3MB・1,215本。数は ILO の更新で変わる）。
データは SDMX-CSV、構造は XML と使い分ける。

### 3. 最新年が国ごとに違う
ISIC4 の合計が取れる最新年は、2026-10-26 の取得で スイス・UAE・ハンガリーが 2025年、**日本は 2023年**
（3部門の `ECO_SECTOR_TOTAL` は日本も 2025年まである。モードで最新年が変わる）。
「同じ年で揃える」か「各国の最新年」かを決めてから表にする。揃えないと年の混在になる。

### 4. 分母は `ECO_ISIC4_TOTAL` と `ECO_SECTOR_TOTAL` の2つがある
ISIC4 の割合を出すなら `ECO_ISIC4_TOTAL`、3部門なら `ECO_SECTOR_TOTAL`。
混ぜると合計が100%にならない。`ECO_AGGREGATE_TOTAL` もあり計3系統。fetch.py はモードごとに1系統に固定している（上の表）。

### 5. 国コードの連結は「+」
SDMX の流儀。World Bank は `;`、Comtrade は `,`。

### 6. 「労働人口に占める割合」と「就業者に占める割合」は別物
このデータフローは **就業者（employment）**（応答の MEASURE 列は `EMP_TEMP_NB` だけ。metadata の `measure` に残す）。
失業者を含む労働力人口が分母の統計とは定義がわずかにずれる。他の資料の値と数％違っても、それだけでは誤りではない。

### 7. ISIC4 の U（治外法権機関）と X（分類不能）は 0 ではない
U は第3次に入れ、4区分に入らないので `その他` に出す（Rev.3 では O・Q）。X は第3次に入れず `分類不能X_pct` に出す
（分母には入っているので、X が大きい国は第3次産業就業者割合が低めに出る）。
2026-10-26 の取得では、日本の2023年は U が122万人（就業者の1.8%）・X が69万人（1.0%）、T は値が無い。
治外法権機関の規模としては大きいが、ILO 側の対応づけの理由は確かめていない。日本の「その他」はこのため2.5%になる。
8. **★同じデータフローに ISIC Rev.3 と Rev.4 が同居する。** 国によって古い年は Rev.3 しかない
   （2026-10-26 の取得で、UAE・フィリピンの2008年は Rev.3 のみ、デンマーク・日本の2008年は Rev.4 のみ）。
   `ECO_ISIC4_*` だけ見ていると古い年が**黙って0件**になる。fetch.py は Rev.4 が無ければ上の対応表で Rev.3 を組む。
   `--isic K` のような単一大分類の指定は Rev.4 の記号なので、Rev.3 しか無い国は出さずに `dropped` に理由を残す
   （Rev.3 の K は不動産・賃貸・事業サービスで、金融ではない）。
9. **★全数でない系列が混じる。** フィリピンの2008年 ISIC3 は `ECO_ISIC3_TOTAL`・`ECO_AGGREGATE_TOTAL`・`ECO_SECTOR_TOTAL` が
   どれも **286万人**（2026-10-26 に確認）。World Bank の同年の労働力人口 3,607万人・失業率 3.7%（`SL.TLF.TOTL.IN`・`SL.UEM.TOTL.ZS`）
   から見た就業者は約3,470万人で、**12分の1**ほどしかない。
   気づかずに構成比を出すと生産関連が44.3%という値になる（fetch.py の出力。これだけ見ても誤りとは分からない）。
   **合計を、その国のその年の就業者総数（別の統計）と必ず突き合わせる。** fetch.py はこの突き合わせをしない
   （同じ系列の中の積み上げと合計の差は `checks_by_country.sum_gap_pct` に出るが、この例では差0%）。
10. **国によって欠ける大分類がある。** フィリピンの2008年 Rev.3 には L（公務）・P（家事）・
   Q が無い（2026-10-26 に確認）。分母が足りないまま構成比にすると、残りの区分が一斉に膨らむ。
   fetch.py は欠けた大分類を `checks_by_country.missing_divisions` に残し、標準エラーにも出す。
