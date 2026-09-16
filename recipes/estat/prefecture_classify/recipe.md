---
id: estat/prefecture_classify
api: estat
task: 都道府県統計 + N階級分類
items: [都道府県別 任意統計（人口・経済・社会）]
tags: [estat, prefecture, classification, japan, choropleth, ranking, rest-api, auth-required]
summary: e-Stat REST API から都道府県別データを取得し、N階級分類してCSV出力
verified_at: 2026-05-18
complexity: medium
auth_required: true
auth_method: ESTAT_APP_ID 環境変数 or ~/.env
data_size_mb: 0  # ライブAPI、ローカルキャッシュなし
---

# estat / prefecture_classify

## 何をする
e-Stat REST API の `getStatsData` から、指定の統計表・カテゴリ・年度の都道府県別データを取得し、N階級分類（階級区分図の元データ）して CSV + metadata.json を出力する。

## API情報
- **出典**: e-Stat 政府統計の総合窓口
- **エンドポイント**: `https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData`
- **認証**: **APIキー必須**（`appId` パラメータ）
- **キー取得**: https://www.e-stat.go.jp/api/api-info/api-guide （無料登録）
- **レート制限**: 公式記載なし、過度な並列は避ける
- **更新頻度**: 統計表によりまちまち（社会人口統計体系は年1回）

## 認証セットアップ

スクリプトは以下の順で APIキーを読む：

1. 環境変数 `ESTAT_APP_ID`
2. ファイル `~/.env` の `ESTAT_APP_ID=xxx` 行

### Mac
```bash
echo 'export ESTAT_APP_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' >> ~/.zshrc
source ~/.zshrc
```

### Win (PowerShell)
```powershell
[Environment]::SetEnvironmentVariable("ESTAT_APP_ID", "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "User")
# 新しい PowerShell セッションで反映
```

### .env 方式（両機共通推奨）
```bash
# ~/.env （.gitignore 済み）
ESTAT_APP_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 使い方

### 例1: 人口増加率 2024年度 4階級分類
```bash
python fetch.py \
    --stats-id 0000010101 \
    --cat01 A192003 \
    --time 2024100000 \
    --classify-n 4 \
    --output-dir ./output
```

### 例2: 自然増加率
```bash
python fetch.py --stats-id 0000010101 --cat01 A4401 --time 2024100000 --classify-n 4
```

### 例3: 階級分類しない（生データ）
```bash
python fetch.py --stats-id 0000010101 --cat01 A192003 --time 2024100000 --classify-n 0
```

### 主要なフラグ
| フラグ | 意味 |
|---|---|
| `--stats-id` | 統計表ID（必須）。例: `0000010101`=社会人口統計体系 |
| `--cat01` | 1次カテゴリ（指標選択）。例: `A192003`=人口増加率 |
| `--cat02` / `--cat03` | 2次/3次カテゴリ |
| `--tab` | 表側選択（性別・年齢区分等） |
| `--area` | 地域絞り込み（指定なしは全都道府県） |
| `--time` | 時間軸（10桁形式、例: `2024100000` = 2024年度） |
| `--classify-n` | 階級分類数（default: 4、0=分類なし） |
| `--city-only` | 市区町村レベルのみ抽出 |

### 出力
- `output/YYYYMMDD_estat_{stats_id}_{cat01}_{time}_class{n}.csv`
  列: class / class_range_hi / class_range_lo / area / value / unit
- `output/YYYYMMDD_estat_..._metadata.json`

## よく使う統計表ID（参照表）

| 指標 | stats_data_id | cat01 | time例 | 備考 |
|---|---|---|---|---|
| 人口増加率 | 0000010101 | A192003 | 2024100000 | ‰ |
| 自然増加率 | 0000010101 | A4401 | 2024100000 | ‰ |
| 社会増加率 | — | — | — | A192003 - A4401 で別途計算（別レシピ） |

`--stats-id 0000010101` は **社会・人口統計体系** で、A192003/A4401/A5101 等多数の指標を含む。
新規 stats_id を探す場合は `estat/search`（未作成）レシピを使う。

## ハマり所（重要）

### 1. appId はログに残るので注意（最重要）
httpx のデフォルト INFO ログレベルは **リクエストURLをフル出力する → appId が露見する**。
本レシピは `logging.getLogger("httpx").setLevel(logging.WARNING)` で抑止済。
他のスクリプトで e-Stat を呼ぶ際は **必ず同じ抑止コードを入れること**。

CI ログ・Slack 通知などに URL がコピーされる経路があると、API キーが流出する。
metadata.json の `request_url` は appId をマスク済（`***`）。

### 2. 時間軸コード（cd_time）の桁数
e-Stat の時間軸は **10桁**:
- `2024100000` = 2024年度
- `2024100400` = 2024年第4四半期
- `2024100012` = 2024年12月
- 過去の旧フォーマット（4桁・6桁）が混在することもある

統計表によって採用桁数が違うので、新規 stats_id を扱う際は **CLASS_INF の time オブジェクトでコード一覧を確認** すること。

### 3. area コードの体系
- 5桁
- `00000` = 全国
- `XX000` = 都道府県（XX=01〜47）
- `XXYYY` = 市区町村（XX=都道府県, YYY=市区町村, 末尾000でない）
- `13101`〜`13123` = 東京23区（市区町村ではなく特別区）
- 過去の合併で消滅した市町村コードも残る（例: 22202=旧浜松市）

本レシピは：
- デフォルト: 都道府県のみ（`is_prefecture` フィルタ）
- `--city-only`: 市区町村レベル（東京23区は除外）

### 4. classify_n の分割ルール
N階級は **データ件数の均等分割**（n_total // n_classes、最終階級が余りを吸収）。
等量分位（quantile）ベースなので、教科書の階級区分図に合わせる場合は OK。

**値の等間隔分割（等区間階級）が必要な場合は別途実装が必要**。

### 5. CLASS_INF からの名前マッピング必須
e-Stat の値レコードは area code（5桁）でしか返ってこない。
`CLASS_INF` メタデータから area code → 都道府県名 のマップを作って結合する。
名前先頭の `【XX】` プレフィクス除去も必要。

### 6. 表示用名称の文字種
e-Stat は area name に `Ｊ全角アルファベット` を使うことがある（`Ａ　人口・世帯` 等）。
教材出力時に半角化したいなら `unicodedata.normalize('NFKC', name)` を適用。

### 7. データ取得失敗時の RESULT.STATUS
HTTP は 200 でも、`RESULT.STATUS != 0` なら API エラー。
- `1` = パラメータ不正
- `100` = 該当データなし
- 詳細は ERROR_MSG を見る

本レシピは `RESULT.STATUS != 0` で `DataFetchError` を発生させる。

### 8. limit の上限
`limit=20000` がデフォルト。大規模統計表（市区町村×多年）では足りない場合がある。
ページング機構なし。範囲を絞って分割取得が必要。

## 効くケース
- 都道府県別の階級区分図元データの取得（教科書・問題集）
- 任意の e-Stat 統計表から「47件＋階級分類」を一発生成
- 市区町村レベルのデータ抽出（--city-only）

## 効かないケース（別レシピ推奨）
| 要求 | 推奨レシピ | 状態 |
|---|---|---|
| 統計表検索（キーワードから stats_id を探す） | `estat/search` | 未作成 |
| 社会増加率（A192003 - A4401） | `estat/calc_social` | 未作成 |
| 多年時系列 | `estat/timeseries` | 未作成 |
| 等区間階級（値範囲均等） | `estat/prefecture_classify_equal_interval` | 未作成 |
| ジニ係数等の派生指標 | 別レシピ | — |

## 関連レシピ
- `estat/search`（統計表検索）— 未作成
- `estat/calc_social`（社会増加率 = 人口増加率 - 自然増加率）— 未作成

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点
- ✅ ファイルI/O は `encoding="utf-8"` 明示
- ✅ CSV書き出し `newline=""` 明示
- ✅ コンソール出力 `sys.stdout.reconfigure(encoding="utf-8")` で Win 対応
- ✅ 構造化例外 `DataFetchError`
- ✅ リトライ3回
- ✅ **APIキーは環境変数 → .env フォールバック**（直書きなし）
- ✅ httpx のINFOログを抑止して appId 漏洩防止
- ✅ metadata.json の request_url は appId マスク済
- ✅ exit code でエラー伝達

## このレシピを使うLLMへのヒント

新規の e-Stat 系または認証付き REST API 系スクリプトを書くとき：

1. **`logging.getLogger("httpx").setLevel(logging.WARNING)` を必ず入れろ** — 認証付きAPIは httpx のINFO ログでキー漏洩する
2. **APIキーは `os.environ → .env フォールバック`** — 直書き厳禁、`load_api_key()` 関数のパターンを使え
3. **metadata.json の request_url はマスクする** — appId を `***` に置換してから保存
4. **e-Stat のような複雑APIは CLASS_INF からコード→名称マップを作る** — 値レコードはコードしか持っていない
5. **`RESULT.STATUS != 0` のAPIエラー判定を忘れない** — HTTP 200 でも API レベルで失敗していることがある
6. **時間軸コード（cd_time）の桁数は統計表ごとに違う** — ハードコードせず CLASS_INF で確認するヘルパーを作るのが望ましい
