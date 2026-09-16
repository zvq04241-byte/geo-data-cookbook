---
id: un_wpp/population_ranking
api: un_wpp
task: 国別人口 ランキング
items: [人口総数, ISO3, ISO2]
tags: [un_wpp, population, ranking, country-level, bulk-download, gz-csv, forecast]
summary: UN World Population Prospects 2024 から指定年・variant の国別人口ランキング上位N
verified_at: 2026-05-18
complexity: easy
auth_required: false
data_size_mb: 15  # gz 圧縮
expanded_size_mb: 220  # CSV 展開
---

# un_wpp / population_ranking

## 何をする
UN World Population Prospects (WPP) 2024 の TotalPopulationBySex データセットから、指定年・variant の国別人口を取得し、上位N国のランキングを CSV + metadata.json に出力する。

## API情報
- **出典**: United Nations DESA, Population Division — World Population Prospects 2024
- **URL**: `https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/WPP2024_TotalPopulationBySex.csv.gz`
- **認証**: 不要（UN 公開バルクデータ）
- **更新頻度**: 2年に1度（2022 → 2024 と更新）
- **データ規模**: gz 約15MB / 展開 CSV 約220MB / 全レコード約 720,000 行
- **単位**: PopTotal は **千人**（thousand persons）

## 使い方

### 既存キャッシュを使う（推奨・テスト時）
```bash
python fetch.py --year 2024 --top-n 20 \
    --cache ~/.cache/wpp/WPP2024_TotalPopulationBySex.csv.gz \
    --output-dir ./output
```

### フルダウンロード（初回）
```bash
python fetch.py --year 2024 --top-n 20 --output-dir ./output
# ~/.cache/wpp/ にキャッシュ
```

### 主要フラグ
| フラグ | 意味 |
|---|---|
| `--year` | 対象年（必須）。1950〜2100 まで取得可（推計含む） |
| `--variant` | Medium/Low/High/Constant fertility/Instant replacement/Zero migration/No change |
| `--top-n` | 上位件数（default: 20） |
| `--cache` | 既存 gz ファイルパス（再ダウンロード省略） |

## ハマり所（重要）

### 1. BOM 付き UTF-8（**最重要・最初に踏む罠**）
UN WPP の gz CSV は **BOM 付き UTF-8** で配信されている。
通常の `encoding="utf-8"` で読むと、**最初の列名（"Variant"）の先頭にBOMが混入**して列名検索が失敗する。

```python
# ❌ NG: 最初の列名検索が空振りする
csv.DictReader(io.TextIOWrapper(gz, encoding="utf-8"))
# row["Variant"] が KeyError、row["﻿Variant"] でしか取れない

# ✅ OK: BOM を自動除去する utf-8-sig
csv.DictReader(io.TextIOWrapper(gz, encoding="utf-8-sig"))
```

`utf-8-sig` は読み込み時に BOM があれば削除する。FAOSTAT は普通の utf-8 で良いが、UN WPP は sig が必要。**他の UN データセットも sig 推奨**（UN は BOM 付きで配信することが多い）。

### 2. LocTypeID で集計地域を除外
LocType フィールドではなく、`LocTypeID` で判定する：
- `"1"` = 世界（World）
- `"2"` = 地域（Africa, Asia, Europe 等）
- `"3"` = サブ地域
- `"4"` = **国（country、ランキング対象）**
- `"5"`〜 = その他のサブ集計

```python
# ✅ 国だけ抽出
rows = [r for r in all_rows if r["LocTypeID"] == "4"]
```

`LocTypeID` は **文字列**（`"4"` であって `4` ではない）。整数比較すると失敗する。

### 3. Time 列は文字列
年は `Time` 列にあり、**文字列**として格納されている：

```python
# ❌ NG
[r for r in rows if r["Time"] == 2024]   # 常に False

# ✅ OK
[r for r in rows if r["Time"] == "2024"]
```

### 4. Variant の選択
- `"Medium"` = 中位推計（**最頻使用、教材デフォルト**）
- `"Low"` / `"High"` = 低位/高位推計
- `"Constant fertility"` = 出生率不変
- `"Instant replacement"` = 即時人口置換
- `"Zero migration"` = 移民なし
- `"No change"` = 全要素不変

**過去年（1950〜2023）も Variant=Medium で取得可能**（実績値だが Medium ラベル）。
2024年〜は実質推計。

### 5. PopTotal は千人単位
PopTotal の生値は **千人**。億・百万人換算は手元で：

```python
pop_thousand = float(r["PopTotal"])
pop_million = pop_thousand / 1000   # 例: 1,450,936 → 1450.936M
```

UN は世界人口を表示する慣習で常に thousand を採用。FAOSTAT 等他APIと混在させる時の単位確認は必須。

### 6. 中国とインドの逆転（2024年データ点）
2023〜2024 年で **インドが中国を抜いて1位** になった。教材で「人口最大は中国」と書く場合、2024年版データ取得時に注意：
- 2024: India 1450.9M > China 1419.3M
- 2010: China 1340.9M > India 1234.3M

WPP 2024 ファイルでは過去年も最新の遡及推計で更新されているため、古い教材値と差が出ることがある。

### 7. ISO 国コードフィールド
- `ISO3_code` — 3文字（例: JPN, USA）
- `ISO2_code` — 2文字（例: JP, US）
- `LocID` — UN 内部数値ID

他APIと結合する場合は **ISO3 が事実上の標準**。

### 8. ファイルサイズと読み込み速度
720,000 行 × 14列 ≈ 全ロード 1〜2 秒。メモリは数百MB 程度。
**chunk 読みは不要**（FAOSTAT と違い）。

ただし year_from/year_to で時系列取得する場合は、全Variant×全年×全地域で巨大になるので注意。

### 9. PopDensity は空欄あり
人口密度（PopDensity）列は存在するが、**国によっては空欄**。
`r["PopDensity"].strip()` で空チェック必須。

### 10. 過去・推計年の境界
WPP 2024 では：
- 1950〜2023年: **実績**（Variant=Medium で取得）
- 2024年: 推計値の起点
- 2024〜2100年: **推計**（Variant 違いで複数）

「実績」と「推計」を区別したい場合は year ≤ 2023 で判定するのが慣例。

## 効くケース
- 「世界人口上位20カ国」（教材図表の典型）
- 任意年 × variant のスナップショット
- ISO3コード付きで他データセットと結合する準備

## 効かないケース（別レシピ推奨）
| 要求 | 推奨レシピ | 状態 |
|---|---|---|
| 多年時系列（推移グラフ） | `un_wpp/population_timeseries` | 未作成 |
| 地域・大陸別ランキング | `un_wpp/region_ranking` | 未作成（LocTypeID=2 で実装可） |
| 年齢別・性別構成 | `un_wpp/age_sex_pyramid` | 別ファイル必要（PopulationBySingleAgeSex） |
| 合計特殊出生率（TFR） | `un_wpp/tfr` | 別ファイル必要 |
| 人口密度ランキング | `un_wpp/density_ranking` | PopDensity 列の空欄処理が課題 |

## 関連レシピ
- `faostat/crops_ranking`（同様のランキングパターン）
- `world_bank/country_indicator`（補完的に使える）

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点
- ✅ ファイルI/O は `encoding="utf-8-sig"`（BOM対応）または `"utf-8"` 明示
- ✅ コンソール出力 `sys.stdout.reconfigure(encoding="utf-8")`
- ✅ 構造化例外 `DataFetchError`
- ✅ リトライ3回
- ✅ metadata.json に source URL / SHA256 / fetched_at / row_count
- ✅ APIキー不要

## このレシピを使うLLMへのヒント

新規の同種データ取得スクリプトを書くとき：

1. **UN系 CSV は `utf-8-sig` で読め** — BOM 付きが多い、`utf-8` だと最初の列名が壊れる
2. **LocTypeID, LocID 等の ID 系は文字列** — 整数キャストする前に確認
3. **年（Time）も文字列** — 比較時に型に注意
4. **PopTotal などは千人単位** — million/billion 換算は手元で
5. **Variant の選択をrecipeに記録** — Medium 以外を使う特殊ケースを明示
6. **2023→2024 で中国→インド逆転** — データ取得タイミングで結果が変わる典型例、教材整合性に注意
