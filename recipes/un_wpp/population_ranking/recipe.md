---
id: un_wpp/population_ranking
api: un_wpp
task: 国別人口 ランキング
items: [人口総数, ISO3, ISO2]
tags: [un_wpp, population, ranking, country-level, bulk-download, gz-csv, forecast]
summary: UN World Population Prospects 2024 から指定年・variant の国別人口ランキング上位N
verified_at: 2026-10-26
complexity: easy
auth_required: false
data_size_mb: 17  # gz 圧縮（2026-10-26 実測 16,980,593 バイト）
expanded_size_mb: 86  # CSV 展開（同 85,787,430 バイト）
---

# un_wpp / population_ranking

## 何をする
UN World Population Prospects (WPP) 2024 の TotalPopulationBySex データセットから、指定年・variant の国別人口を取得し、上位N国のランキングを CSV + metadata.json に出力する。
順位は **WPP の Country/Area（LocTypeID=4）全件の中で**付ける（2024年 Medium で237件。既定の国リストは使わない）。
この237件には独立国でない地域（香港・台湾・プエルトリコ・パレスチナ・グリーンランド・コソボ・バチカン等）が入る。
metadata の `scope` にこの範囲を、`check_sum_vs_world` に「237件の合計＝世界（LocTypeID=1）」の検算を書く（2024年 Medium で一致）。

## API情報
- **出典**: United Nations DESA, Population Division — World Population Prospects 2024
- **URL**: `https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/WPP2024_TotalPopulationBySex.csv.gz`
- **認証**: 不要（UN 公開バルクデータ）
- **更新頻度**: 2年に1度（2022 → 2024 と更新）
- **データ規模**: gz 約17MB / 展開 CSV 約86MB / 720,210 行 × 18列（2026-10-26 にこの手元のキャッシュで実測）
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
| `--year` | 対象年（必須）。1950〜2100（範囲外は止まる） |
| `--variant` | Medium/Low/High/Constant fertility/Instant replacement/Zero migration/No change。**Medium 以外は2024年以降だけ**（2023年以前を指定すると止まる） |
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

**過去年（1950〜2023）は Variant=Medium だけにある**。Medium 以外の variant は2024〜2100年だけ（2026-10-26 実測）。
ファイルにはほかに Momentum・Constant mortality・PI（予測区間）等の variant もある（計18種）。

### 5. PopTotal は千人単位
PopTotal の生値は **千人**。億・百万人換算は手元で：

```python
pop_thousand = float(r["PopTotal"])
pop_million = pop_thousand / 1000   # 例: 1,450,936 → 1450.936M
```

このファイル（TotalPopulationBySex）の PopMale/PopFemale/PopTotal は千人。FAOSTAT 等他APIと混在させる時の単位確認は必須。

### 6. 中国とインドの逆転（2024年データ点）
WPP 2024 の Medium では **2022年にインドが中国を上回る**（2021: 中国1426.4M・インド1414.2M → 2022: 中国1425.2M・インド1425.4M。2026-10-26 再計算）。教材で「人口最大は中国」と書く場合、年と版に注意：
- 2024: India 1450.9M > China 1419.3M
- 2010: China 1351.6M > India 1243.5M
（いずれも WPP 2024・Medium の PopTotal。2026-10-26 にキャッシュの gz から再計算。旧版の本文は2010年の値を 1340.9／1234.3 と書いていたが、このファイルとは一致しない）

WPP 2024 ファイルでは過去年も最新の遡及推計で更新されているため、古い教材値と差が出ることがある。

### 7. ISO 国コードフィールド
- `ISO3_code` — 3文字（例: JPN, USA）
- `ISO2_code` — 2文字（例: JP, US）
- `LocID` — UN 内部数値ID

他APIと結合する場合は **ISO3 が事実上の標準**。

### 8. ファイルサイズと読み込み速度
720,210 行 × 18列。csv.DictReader での全ロードは手元の Mac で約1秒（2026-10-26）。
**chunk 読みは不要**（FAOSTAT と違い）。

ただし year_from/year_to で時系列取得する場合は、全Variant×全年×全地域で巨大になるので注意。

### 9. PopDensity は空欄あり
人口密度（PopDensity）列は存在するが、空欄があり得る（2024年 Medium の237件では空欄0。年・variant で確かめる）。
`r["PopDensity"].strip()` で空チェック必須。PopTotal の空欄・非数値は fetch.py が除外して名前を metadata に書く。

### 10. 過去・推計年の境界
WPP 2024 では：
- 1950〜2023年: Medium だけにある値。WPP の用語では estimates（推計値）で、観測値そのものではない
- 2024〜2100年: projections（将来推計）。variant 違いで複数ある（Medium 以外の variant が2024年から始まることで確認）

区別したい場合は year ≤ 2023 で判定する。

### 11. 5年平均を折れ線にするとき、点は期間の真ん中に置く
WPP 2024 は毎年の値を出す。教材の図は「5年間の平均値」で描くことが多い（古い版の WPP が5年期間で出していた名残り）。
平均した1点は**時点ではなく幅**を代表するので、横軸の位置は **始まり＋年数/2**（1950～54年＝1952.5、最後が2020～23年の4年なら2022.0）。
`(1950+1954)/2＝1952` は年の番号の平均で、**半年ずれる**。目盛りは5年ごとにし、点が目盛りの間に入る形にする（Excel の「軸位置：目盛の間」と同じ）。
- 値がすべて正しくても、10年ごとの目盛り＋1952 の位置で描くと「目盛りがずれている」図になる（実際に起きた）

### 12. 版が変わると、過去の年の値まで変わる
WPP は版ごとに1950年以降の全系列を推計し直す。**新しい版で描いた「昔の値」は、昔の版の値と一致しない。**
- 例: リビアの乳児死亡率 2010～14年の平均は WPP 2024 で 13.2‰（Demographic_Indicators_Medium の IMR を5年単純平均。2026-10-26 再計算）。
  2015年ごろの版で描かれた図とは値が合わないことがある。旧版の図を描き直すときも、注に使った版を書く
古い教材の値と照合するときは、教材が使った版を先に確かめる。版の違いを実際の変化と取り違えない。

## 効くケース
- 「世界人口上位20カ国」（教材図表の典型。順位は国・地域237件の中で付くので、独立国だけの順位が要るなら絞って注記する）
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
6. **WPP 2024 では2022年に中国→インド逆転** — 版と年で結果が変わる典型例、教材整合性に注意
