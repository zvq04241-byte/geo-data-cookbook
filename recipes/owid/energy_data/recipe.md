---
id: owid/energy_data
api: owid
task: 国別エネルギー構成・絶対量取得
items: [一次エネルギー構成比, 発電量, 各エネルギー源消費量]
tags: [owid, energy, mix, share, abs, country-level, github-csv, ttl-cache]
summary: Our World in Data energy-data から指定国の一次エネルギー構成（share / abs）を取得
verified_at: 2026-05-18
complexity: medium
auth_required: false
data_size_mb: 25  # 単一CSV
---

# owid / energy_data

## 何をする
Our World in Data (OWID) の energy-data リポジトリから、指定国・期間の一次エネルギーデータを取得し、**構成比 (%)** または **絶対量 (TWh)** または **任意metrics列**で CSV + metadata.json に保存する。

## API情報
- **出典**: Our World in Data — energy-data
- **URL**: `https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv`
- **認証**: 不要（GitHub raw 公開）
- **形式**: 単一CSV、全部入り（国 × 年 × 全カラム）
- **データ規模**: 約 25MB / 約 22,000 行 / 100+ カラム
- **基礎統計**: IEA + BP Statistical Review + Ember を OWID が統合
- **更新頻度**: 年1〜2回（IEA / BP の更新を反映）
- **TTL**: ファイルmtimeで管理、default 7日

## 使い方

### 構成比モード（教材の典型用途）
```bash
# 日本の一次エネルギー構成 2015-2023
python fetch.py --country Japan --year-from 2015 --year-to 2023 \
    --mode share --output-dir ./output
```

### 絶対量モード（TWh）
```bash
python fetch.py --country China --year-from 2000 --year-to 2023 \
    --mode abs --output-dir ./output
```

### 任意 metrics 列（発電量等）
```bash
python fetch.py --country Germany --year-from 2010 --year-to 2023 \
    --mode metrics --metrics solar_electricity,wind_electricity,coal_electricity \
    --output-dir ./output
```

### 主要フラグ
| フラグ | 意味 |
|---|---|
| `--country` | 国名（OWID表記、例: Japan, China, World, OECD） |
| `--year-from` / `--year-to` | 年範囲 |
| `--mode` | share / abs / metrics |
| `--metrics` | mode=metrics で使う列名カンマ区切り |
| `--step` | 年の間引き（例: 5 で5年毎） |
| `--ttl-days` | キャッシュ有効日数（default: 7） |
| `--cache` | 既存CSV を直接指定 |

## ハマり所（重要）

### 1. country 列に集計値が混在（**最重要**）
`country` 列には **個別国だけでなく以下も混在**：

| 種別 | 例 |
|---|---|
| 個別国 | `Japan`, `China`, `United States` |
| 大陸 | `Africa`, `Asia`, `Europe`, `Oceania`, `North America`, `South America` |
| 経済グループ | `OECD`, `Non-OECD`, `European Union (27)`, `G7`, `G20` |
| 所得階級 | `High-income countries`, `Upper-middle-income countries`, `Low-income countries` |
| 世界 | `World` |
| 歴史的国家 | `USSR`, `Yugoslavia`, `Czechoslovakia` |

教材でランキングする場合は **個別国だけにフィルタ** が必要（FAOSTAT の AGG_AREAS と同じ問題）。
本レシピは単一国指定なので問題ないが、**ranking レシピを別途作る場合は明示除外必須**。

### 2. 国名の表記揺れ
| 一般通称 | OWID表記 |
|---|---|
| United States | `United States` （注: "America" や "USA" ではヒットしない） |
| United Kingdom | `United Kingdom` |
| South Korea | `South Korea` （"Korea, Rep." ではない） |
| Russia | `Russia` （"Russian Federation" ではない） |
| Czech Republic | `Czechia`（2018年頃改名） |
| Turkey | `Turkey`（Türkiye 表記には未対応） |
| Hong Kong | `Hong Kong` |
| Taiwan | `Taiwan`（中国の一部としては扱わない） |

`--country` で見つからなければ部分一致候補を出すヘルパを実装している。

### 3. 100% にならない構成比
`{source}_share_energy` の合計が **常に 100% にはならない**。理由:
- 主要5源（coal / oil / gas / nuclear / renewables）以外に `biofuels`, `other_renewables` 等の細目あり
- データ欠損（特に古い年で renewables 列が null）
- OWID 内部で換算誤差

本レシピでは合計列 `total_pct` を計算して出力するが、98〜102% の範囲なら正常。
**「合計100%にならない」とユーザに指摘される前に metadata.json の notes に明記**。

### 4. share と consumption の単位の違い
- `{source}_share_energy` = **% of primary energy**（一次エネルギー比）
- `{source}_share_elec`   = **% of electricity**（電力に占める比）
- `{source}_consumption`  = **TWh of primary energy**（一次エネルギー絶対量）
- `{source}_electricity`  = **TWh of electricity generation**（発電量絶対量）

「一次エネルギー」と「電力」は **概念が異なる**。一次エネルギーは「資源投入量」、電力は「最終発電量」。
教材で混同すると致命的（例: 原子力の「発電シェア」と「一次エネルギーシェア」は数値が大きく異なる）。

### 5. 集計値 World の扱い
`country=World` の行は **個別国の合計**。data validation 用に使える：
- 各国の `{source}_consumption` の合計 ≈ `World` の `{source}_consumption`
- 一致しない場合は欠損あり or 換算差異

### 6. データ遅延（IEA/BP の更新サイクル）
- 当年データはほぼ無い（IEA/BP は前年データを6-12か月遅れで発表）
- 例: 2026年5月時点で最新は 2023 or 2024 年
- 古い教材データと比較する時、「OWID の2020年値」と「他APIの2020年値」が異なることがある

### 7. キャッシュ更新戦略
`mtime` 基準の TTL（default 7日）。
- ローカル開発: 7日で十分
- 教材本番制作: 月1回の `--ttl-days 30` 程度
- 緊急更新: `--ttl-days 0` で即時再ダウンロード

GitHub raw は ETag を返すが本レシピは未対応（将来 ETag/If-Modified-Since 対応で帯域節約可能）。

### 8. 100+ カラムからの選択
OWID CSV は 100+ カラムあり、欲しいデータの列名が分からないと使えない：

主要カラム命名規則：
- `{source}_consumption` — 消費量 (TWh, primary)
- `{source}_share_energy` — 一次エネルギー比 (%)
- `{source}_share_elec` — 電力比 (%)
- `{source}_electricity` — 発電量 (TWh)
- `{source}_elec_per_capita` — 1人当たり発電量 (kWh)
- `{source}_cons_change_pct` — 前年比変化率 (%)

source は `coal / oil / gas / nuclear / biofuels / hydro / wind / solar / renewables / fossil_fuels` 等。
**全カラム一覧** は OWID のドキュメント参照: https://github.com/owid/energy-data/blob/master/owid-energy-codebook.csv

### 9. 単位プレフィックスの混在
- `_consumption` 系: **TWh**（terawatt-hours）
- `_per_capita` 系: **kWh / person**
- `_share_*` 系: **%**
- `co2_per_capita` 系: **tonnes / person**

カラム名末尾を見ないと単位を間違える。`recipe.md` の query セクションで明示せよ。

### 10. 「再エネ」の定義の揺れ
`renewables` には bioenergy/biofuels が含まれる場合と含まれない場合がある：
- `renewables_consumption` — 全再エネ（hydro + wind + solar + bio + geothermal）
- `wind_consumption + solar_consumption + hydro_consumption` ≠ `renewables_consumption`（差は bio 等）

「再エネ」と言うだけでは何を指すか曖昧。**何が含まれるか recipe で記録**。

## 効くケース
- 単一国の一次エネルギー構成推移（教科書「日本のエネルギー事情」等）
- 国別エネルギー絶対量の経年変化
- 任意の発電カラム（太陽光・風力等）の取得

## 効かないケース（別レシピ推奨）
| 要求 | 推奨レシピ | 状態 |
|---|---|---|
| 多国比較（同じ年で複数国） | `owid/energy_compare` | 未作成 |
| 国別ランキング | `owid/energy_ranking`（集計値除外必要） | 未作成 |
| CO2 排出量データ | `owid/co2_data`（別ファイル） | 未作成 |
| 食料・農業・人口等の他テーマ | OWID の他リポジトリを別レシピ化 | 未作成 |

## 関連レシピ
- `iea/electricity_generation` — **発電量を IEA 一次データで**取りたい時（出典をIEAに統一・火力内訳の長期推移 1990–）。
  OWIDは IEA+Ember+EI 統合の派生データなので、出典の権威性が要る教材では IEA 直接を選ぶ。
  ただし OWID は Ember 速報込みで**当年・前年の最新値**に強い／分散型太陽光推計込み（IEAは gross・当年-2）。**1枚の図でソース混在は禁止**。
- `world_bank/country_indicator`（補完的に使える）
- `un_wpp/population_ranking`（1人当たり計算時の人口分母として）

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点
- ✅ ファイルI/O は `encoding="utf-8"`
- ✅ コンソール出力 `sys.stdout.reconfigure(encoding="utf-8")`
- ✅ 構造化例外 `DataFetchError`
- ✅ リトライ3回
- ✅ TTL キャッシュ（mtime 基準）
- ✅ metadata.json に source URL / SHA256 / cache_age / row_count
- ✅ APIキー不要

## このレシピを使うLLMへのヒント

新規の GitHub raw CSV データ取得スクリプトを書くとき：

1. **TTL キャッシュは必須** — github raw は無料だが、毎回25MB DL は無駄。`mtime + ttl_days` で簡単に実装可
2. **`country` 列に集計値が混在することを疑え** — FAOSTAT・OWID・WB すべてに共通
3. **国名表記揺れの候補表示ヘルパを書け** — `--country USA` でヒットしないユーザに「`United States` では？」と提案
4. **`{prefix}_{suffix}` 命名規則をrecipeに記録** — OWID のように 100+ カラムあると、命名規則が分からないと使えない
5. **「再エネ」「化石燃料」のような曖昧用語は定義を明示** — recipe.md で何が含まれるか書く
6. **share と abs を別 mode で分ける** — 1関数に詰め込まない、教材用途では使い分けが多い
