---
id: faostat/crops_ranking
api: faostat
task: 作物生産量 国別ランキング
items: [Wheat, Rice, Maize, Soybeans, Barley, Potatoes, Cassava, Sugarcane, Cotton, Coffee, Tea, Cocoa]
tags: [faostat, crops, production, ranking, single-item, single-year, country-level, bulk-download]
summary: FAOSTAT Production_Crops_Livestock から指定作物の生産量で世界上位N国を取得
verified_at: 2026-05-18
complexity: easy
auth_required: false
data_size_mb: 65  # 圧縮ZIP
expanded_size_mb: 300  # 展開CSV
gotcha_count: 6
experiment_validated: true  # Phase 0.5 で cookbook 効果を実証したリファレンスレシピ
---

## ⚠ 2026-08-20 追記：集計地域名は改称される

`Least Developed Countries` は FAO 側で **`Least Developed Countries (LDCs)`** に改称されており、
完全一致の除外リストから漏れて Rice/2024 の第3位に混入していた（2億t超＝インド・中国に次ぐ位置）。
**除外は完全一致で行うため、FAO が表記を変えると静かに壊れる。**
新しい作物・年で使うときは、上位に不自然な巨大値が出ていないか必ず目視する。
2026-08-20 に全233地域名を監査した結果、漏れはこの1件のみだった（監査キーワード＝
Countries/Developing/Income/European Union/World/大陸名 等）。

## ⚡ このレシピが解決した実証済み問題（Phase 0.5 実験）

**2026-05-18 の A/B 実験で、本レシピの「ハマり所」セクションがどんなLLMにも欠如している暗黙知を補完できることを確認**。

| LLM | cookbook 無し | cookbook 有り（本レシピ） |
|---|---|---|
| gpt-oss-120b | 0/3 正解 (集計地域汚染) | 2/3 正解 |
| claude-sonnet-4-5 | 0/3 正解 (China-aggregate 漏れ) | (未試行・本レシピ準拠で正解見込) |
| claude-opus-4-1 | 0/3 正解 (China-aggregate 漏れ) | (同上) |

→ **強モデルでも見逃す gotcha を本レシピが伝達**。詳細: `experiments/phase0_5_first_run_20260518/summary_exp1.md`

特に効いた知見：
- §2「集計地域の混入」の `China` = `China, mainland + Taiwan + HK + Macao` の合計だという指摘
- `Australia and New Zealand`、`LLDCs`（末尾s）等の見落としやすい地理集計
- 古い歴史的アグリゲート（USSR, Yugoslav SFR 等）も含めること


# faostat / crops_ranking

## 何をする
FAOSTAT Production_Crops_Livestock データセットから、指定作物の生産量（または収穫面積・単収）で世界上位N国を取得し、CSV + metadata.json を出力する。

## API情報
- **出典**: FAOSTAT bulk download
- **URL**: `https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip`
- **認証**: 不要
- **データ規模**: ZIP約65MB / 展開CSV約300MB
- **更新頻度**: 年1〜2回（FAO発表サイクル）
- **単位**: tonnes（Production の場合）

## 使い方

### 既存CSVを使う場合（推奨・テスト時）
```bash
python fetch.py \
    --item Wheat --year 2023 --top-n 10 \
    --csv ./cache/fao_data/Production_Crops_Livestock_E_All_Data_\(Normalized\).csv \
    --output-dir ./output
```

### フルダウンロードする場合（初回）
```bash
python fetch.py --item Wheat --year 2023 --top-n 10 --output-dir ./output
# ~/.cache/faostat/ にZIP+CSVがキャッシュされる
```

### 出力
- `output/YYYYMMDD_faostat_wheat_2023_top10.csv` — Rank/Area/Item/Element/Year/Value/Unit
- `output/YYYYMMDD_faostat_wheat_2023_top10_metadata.json` — 出典URL/SHA256/行数/取得時刻

## ハマり所（重要）

### 1. CSV のエンコーディング
FAOSTAT CSV は **UTF-8**。`encoding="latin-1"` で読むと `TÃ¼rkiye` のように文字化けする。
古いコード例で `latin-1` を見ても真似しない。

### 2. 集計地域の混入（最重要）
Area 列に国名と集計地域が混在する。ランキング前に必ず除外（`AGG_AREAS` セット参照）。

特に **見落としやすいアグリゲート**:
- `China` — FAOSTAT 仕様: `China` = `China, mainland` + `Taiwan` + `Hong Kong SAR` + `Macao SAR` の合計。
  教材用途では `China, mainland` を採用するため `China` の方を除外する（重複防止）。
- `Australia and New Zealand` — 大洋州の地理集計
- `Land Locked Developing Countries (LLDCs)` — **末尾 s 付き**で出ることがある。`LLDC` だけ除外していると漏れる。両形を含めること
- `European Union (27)` / `European Union (28)` — 加盟国数で複数表記
- `Belgium-Luxembourg` / `USSR` / `Yugoslav SFR` 等 — 古い年データに残る歴史的アグリゲート

実測例（2026-05-18 検証時の Wheat 2023）:
- 修正前トップ10には `China` と `China, mainland` が重複、`Australia and New Zealand`・`LLDCs` が混入
- 修正後は China, mainland → India → Russia → USA → France → Canada → Pakistan → Australia → Türkiye → Ukraine の妥当な結果

### 3. Item 名の表記揺れ
作物によって正式名が異なる：
- 米: `Rice, paddy`（"Rice" 単独だとヒットしない年もある）
- トウモロコシ: `Maize (corn)`（"Corn" や "Maize" 単独はヒットしない）
- 大豆: `Soya beans`（"Soybeans" はヒットしない）
- パーム油: `Oil, palm`
- 綿花: `Cotton lint` または `Seed cotton, unginned`（リント基準か原綿基準で別物）

→ `ITEM_ALIASES` 辞書で展開してから検索する。

### 4. メモリ使用量
フルロードで約2GBメモリを食うので、`pd.read_csv(chunksize=200_000)` で chunk 処理。

### 5. ZIP内の付帯CSV
ZIP 内には本体 CSV 以外に Flag/AreaCode/ItemCode/Element 等のメタCSVが入っている。
ファイル名フィルタで本体だけ抽出する（`extract_csv` 関数参照）。

### 6. データセット名の歴史的変更
- 〜2021年頃: `Production_Crops_E_All_Data_(Normalized)`（作物のみ）
- 2022年〜: `Production_Crops_Livestock_E_All_Data_(Normalized)`（畜産統合）
古い記事を参考にする時は注意。

## 効くケース
- 単一作物 × 単一年 × 国別上位N
- "Production"（生産量）以外でも `--element` 切替で動く
  - `Area harvested`（収穫面積、単位 ha）
  - `Yield`（単収、単位 hg/ha）
- 教材図表向けの「上位10カ国シェア」「地図塗り分け対象国の抽出」

## 効かないケース（別レシピ推奨）
| 要求 | 推奨レシピ | 状態 |
|---|---|---|
| 多年時系列 | `faostat/crops_timeseries` | 未作成 |
| 国別の World 集計値（合計） | `faostat/crops_world_total` | 未作成 |
| 国間貿易（輸出入相手国） | `faostat/trade_matrix` | 未作成 |
| 食料バランス（供給熱量等） | `faostat/food_balance` | 未作成 |
| 畜産物（家畜頭数・畜産物生産） | `faostat/livestock_ranking` | 未作成 |

## 関連レシピ
（このレシピが第1号。今後追加）

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数で受け取り、相対なら絶対化）
- ✅ ファイルI/O は `encoding="utf-8"` 明示
- ✅ コンソール出力は `sys.stdout.reconfigure(encoding="utf-8")` で Win cmd.exe 対応
- ✅ 構造化例外 `DataFetchError` で source/url/kind を保持
- ✅ リトライ3回（HTTPエラー時）
- ✅ metadata.json に source URL / SHA256 / fetched_at / row_count を記録
- ✅ exit code でエラー伝達（成功=0、失敗=1）
- ✅ APIキー不要（よって直書きリスクなし）

## このレシピを使うLLMへのヒント

新規の類似データ取得スクリプトを書くとき：
1. **ITEM_ALIASES のパターンを真似ろ** — どんな統計APIでも品目名は揺れる
2. **AGG_AREAS のような除外集合を必ず用意しろ** — 集計値の混入は典型的バグ
3. **chunk読み込みで大容量CSVに対応しろ** — メモリ管理を怠ると死ぬ
4. **metadata.json を必ず出せ** — 教材出典追跡に必須
5. **`--csv` のような既存ファイル迂回オプションを残せ** — テスト・開発時に再ダウンロード時間を節約できる
