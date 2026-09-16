---
id: estat/calc_social
api: estat
task: 都道府県別 社会増加率（人口増加率 − 自然増加率）
tags: [estat, prefecture, population, social-increase, migration, ranking, japan, rest-api, auth-required, composite-calc]
summary: e-Stat 社会人口統計体系から人口増加率(A192003)と自然増加率(A4401)を取得し差＝社会増加率を計算・ランキング
items: [社会増加率]
verified_at: 2026-06-08
complexity: medium
auth_required: true
auth_env_var: ESTAT_APP_ID
gotcha_count: 8
pattern: live-rest-api + auth + two-indicator-difference
---

# estat / calc_social

## 何をする
e-Stat 社会・人口統計体系(statsDataId=0000010101)から都道府県別の
**人口増加率(A192003)** と **自然増加率(A4401)** を取得し、その差
**社会増加率 = 人口増加率 − 自然増加率** を計算して降順ランキングを CSV + metadata.json に出力する。

社会増加率は転入超過の度合い（正＝人口流入、負＝流出）。教材の「人口移動」単元で頻出。

## API情報
- **出典**: e-Stat 政府統計の総合窓口（社会・人口統計体系）
- **エンドポイント**: `https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData`
- **認証**: **必要**（環境変数 `ESTAT_APP_ID`、または `~/.env`）
- **statsDataId**: `0000010101`、**cdCat01**: 人口増加率=`A192003` / 自然増加率=`A4401`

## 使い方
```bash
export ESTAT_APP_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
python fetch.py --time 2024100000 --output-dir ./output
```
出力: `output/YYYYMMDD_estat_social_increase_2024.csv`
（Rank,Area,Value(社会増加率),PopIncrease,NaturalIncrease,Year,Unit）＋ metadata.json。

## ハマり所（重要）

### 1. 社会増加率は「人口増加率 − 自然増加率」（最重要・概念）
人口増加率＝総人口の増減、自然増加率＝出生−死亡。その差が**社会増加率＝転入−転出**。
3者を混同しない。社会増加率が正なら転入超過（人口流入）。
例(2024): 東京都は人口+6.6‰・自然-3.7‰ → 社会**+10.3‰**（自然減を移流入が上回る）。

### 2. 同一統計表の2つの cdCat01 を別々に取得して差を取る
人口増加率と自然増加率は**同じ statsDataId(0000010101) の別 cdCat01**。
1回のクエリでは両方取れないので、`cdCat01=A192003` と `cdCat01=A4401` で2回取得し、
都道府県名で突き合わせて引き算する。

### 3. appId をログ・出力に出さない（漏洩防止）
httpx は INFO で appId 入りの完全 URL を出力する。**`logging.getLogger("httpx").setLevel(WARNING)`** で抑止。
metadata・safe_url にも appId を載せない（`appId=***` でマスク）。

### 4. area code 5桁・末尾000＝都道府県、00000＝全国は除外
e-Stat の area code は5桁。**末尾000が都道府県**、`00000` は全国合計なので除外。
市区町村（末尾000以外）も混ざるので都道府県だけ抽出する。

### 5. CLASS_INF の名前に【番号】が付く
area の表示名は `CLASS_INF.CLASS_OBJ` から引くが、先頭に `【13】` のような番号が付く。
`re.sub(r"^【\d+】", "", name)` で除去する。

### 6. VALUE が単一行のとき dict で返る
`DATA_INF.VALUE` は通常 list だが、1件のとき **dict** で返る。`isinstance(v, dict)` で list 化してから回す
（e-Stat 全般の罠。CLASS_OBJ / CLASS も同様）。

### 7. cdTime は YYYYMMDDHH 形式
`2024100000` は2024年度を表す（社会人口統計体系の年度コード）。
年により利用可否が異なるので、データなしなら年を変えて確認する。

### 8. 両指標が揃う都道府県のみ計算
片方の指標が欠損する都道府県は社会増加率を出せないので除外する（推測補完しない）。

## 効くケース
- 都道府県別 社会増加率ランキング（人口移動の教材データ）
- 人口増加率・自然増加率・社会増加率の3点セット出力（CSVに併記）

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 単一指標の取得・階級分類 | `estat/prefecture_classify` | 実装済 |
| 統計表ID の検索 | `estat/search`（getStatsList） | 未作成 |
| 市区町村レベルの社会増加 | 本レシピを市区町村対応に拡張 | 未対応 |
| 時系列推移 | 多年取得の別レシピ | 未作成 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数）
- ✅ ファイルI/O は `encoding="utf-8"`、CSVは `newline="\n"`
- ✅ 構造化例外 `DataFetchError`（source/url/kind）
- ✅ 取得3回リトライ、RESULT.STATUS チェック
- ✅ **認証APIの appId 漏洩防止**（httpx ログ抑止・URLマスク）
- ✅ metadata.json に statsDataId / cdCat01 / formula / SHA256 / row_count（appId は載せない）
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）

## このレシピを使うLLMへのヒント
1. **複合指標は素の指標を別々に取得して計算**（人口増加率−自然増加率＝社会増加率）。定義を明示する
2. **認証APIは appId をログ・出力に絶対出さない**（httpx INFO抑止・URLマスクが定石）
3. **e-Stat の dict-or-list 揺れ**（VALUE/CLASS/CLASS_OBJ）を必ず list 化
4. **area code の粒度**（5桁末尾000=都道府県 / 00000=全国）で集計レベルを制御
