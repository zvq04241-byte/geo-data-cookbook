---
id: un_wup/urbanization_ranking
api: un_wup
task: 都市化度（Degree of Urbanization）国別ランキング
tags: [un_wup, urbanization, degree-of-urbanization, ranking, country-level, bulk-download, xlsx, single-year]
summary: UN WUP 2025 の Degree of Urbanization バルクxlsxから、指定年・カテゴリの国別%で上位N国を取得
items: [Cities and Towns, Cities, Towns, Rural]
verified_at: 2026-06-08
complexity: easy
auth_required: false
data_size_mb: 1
gotcha_count: 8
pattern: bulk-xlsx-download + openpyxl + type-code-country-filter
---

# un_wup / urbanization_ranking

## 何をする
UN World Urbanization Prospects 2025 の "Degree of Urbanization" バルク xlsx（F02=%, F01=人口）から、
指定年・カテゴリ（Cities and Towns 等）の**国別 %** を取得し、上位N国を CSV + metadata.json に出力する。

## API情報
- **出典**: UN WUP 2025 — Degree of Urbanization（Countries and Aggregates）
- **URL**: `https://population.un.org/wup/assets/Download/Countries%20and%20Aggregates/WUP2025-F02-Degree-of-Urbanization_percPop_by_category.xlsx`（F01=絶対人口）
- **認証**: 不要
- **データ規模**: xlsx 約1MB
- **形式**: xlsx（複数シート: Cities and Towns / Cities / Towns / Rural）

## 使い方
```bash
# 2025年 都市人口割合（Cities and Towns）上位20
python fetch.py --year 2025 --top-n 20 --output-dir ./output

# 既存キャッシュ xlsx を使う（テスト時・再DL回避）
python fetch.py --year 2025 --top-n 20 --cache <path-to.xlsx> --output-dir ./output
```
出力: `output/YYYYMMDD_wup_urbanization_2025_urban_top20.csv`（Rank,Area,ISO3,Category,Indicator,Year,Value,Unit）
＋ `..._metadata.json`（出典URL/SHA256/取得時刻/行数）

## ハマり所（重要）

### 1. 「Cities and Towns %」は従来の都市人口率とは別物（最重要）
DEGURBA（人口密度グリッド分類）の「Cities and Towns %」= **非Rural人口の割合**で、
従来の UN「urban/rural」定義の都市化率とは数値が大きく異なる。
実例（2025）: **Bangladesh 98.0% / Egypt 97.5%** — 従来定義ではバングラ約40%。
教材で「都市化率」と説明するとき、どちらの定義かを必ず明示する。混同は致命的。

### 2. 集計地域の除外は種別コード row[7]==4 で行う
Area 列には国だけでなく World / 地域（Asia 等）/ 所得グループが混在する。
**`row[7]（種別コード）== 4` の行だけ**が「国・地域」。これを外すと集計値がランキングに混入する。
（FAOSTAT の AGG_AREAS 除外、WPP の LocTypeID と同じ構造の罠。）

### 3. type==4 は非主権地域も含む
コード4は「country or area」で、**Gibraltar / China, Macao SAR / China, Hong Kong SAR / Bermuda /
Sint Maarten / Aruba / Holy See** 等の非主権地域も含む。これらは都市化度ほぼ100%で上位を占める。
「主権国家だけ」のランキングが欲しい場合は、別途 ISO3 ホワイトリスト等で絞る必要がある（本レシピは未絞り）。

### 4. 年列は index 10 以降・ヘッダ値を直接スキャンして引く
メタ列が 0〜9、年データは **header[10:]**。年→列の対応は
`build_year_columns()` でヘッダ値を直接走査して作る。
`all_years.index(year)+10` のような**連番前提は、ヘッダに None 欠落があると破綻**するため使わない。

### 5. openpyxl は read_only=True, data_only=True
`load_workbook(..., read_only=True, data_only=True)`。
**data_only を付けないと数式セルが数式オブジェクトで返る**ことがある。read_only は複数シート大ブックのメモリ対策。

### 6. シート選択を間違えると別定義の値が黙って返る
`urban→"Cities and Towns"` / `cities→"Cities"` / `towns→"Towns"` / `rural→"Rural"`。
シート名を取り違えても例外は出ず、別カテゴリの数値が返るだけ。`--category` の対応を固定する。

### 7. F02=percent / F01=population の取り違え
F02 が割合(%)、F01 が絶対人口(千人)。ファイルを取り違えると単位が狂う。`--indicator` と FILE_MAP を一致させる。

### 8. 2025 超の年は推計値
WUP は将来推計を含む。`--year > 2025` は観測でなく projection。metadata の `is_projection` で明示する。

## 効くケース
- 単一年 × カテゴリ（Cities and Towns 等）× 国別 % の上位N
- `--indicator population` で絶対人口（千人, F01）ランキングにも切替可
- `--min-percent` でしきい値フィルタ

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 1か国の時系列推移 | `un_wup/urbanization_timeseries` | 未作成 |
| 従来定義の都市人口率 | UN WUP の旧 urban/rural 系列（別ファイル） | 未作成 |
| 地域・大陸の集計値 | type!=4 を対象にする別レシピ | 未作成 |
| 主権国家のみ | ISO3 ホワイトリストでの絞り込み拡張 | 未実装 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数・キャッシュは Path.home()/.cache）
- ✅ ファイルI/O は `encoding="utf-8"`、CSV書き込みは `newline="\n"`
- ✅ 構造化例外 `DataFetchError`（source/url/kind）
- ✅ ダウンロード3回リトライ
- ✅ metadata.json に source URL / SHA256 / fetched_at / row_count / is_projection
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）
- ✅ APIキー不要（漏洩リスクなし）

## このレシピを使うLLMへのヒント
1. **集計除外は「禁止リスト」でなく「種別コード許可（==4）」で行う** — WUP/WPP/FAOSTAT で形は違うが思想は同じ
2. **xlsx は openpyxl read_only+data_only**、年列は固定オフセット＋ヘッダ走査で引く
3. **指標の定義を疑う** — 「urbanization」でも DEGURBA と従来定義で別物。reference 値で実データと突き合わせて確認する
4. **reference YAML の must_not_include_anywhere に集計名を列挙**して、混入を機械検出させる
