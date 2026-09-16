---
id: comtrade/trade_ranking
api: comtrade
task: 貿易相手国ランキング
items: [TOTAL, HS01-HS99 各品目]
tags: [comtrade, trade, ranking, single-item, single-year, partner-country, rest-api, no-auth]
summary: UN Comtrade Public Preview API から特定国×HS×年の貿易相手国上位N国を取得
verified_at: 2026-06-08
complexity: medium
auth_required: false
data_size_mb: 0  # ライブAPI、ローカルキャッシュなし
gotcha_count: 8
---

# comtrade / trade_ranking

## 何をする
UN Comtrade Public Preview API から、**特定国（reporter）の特定HS品目の特定年の輸出 or 輸入における相手国ランキング上位N国** を取得し、CSV + metadata.json を出力する。

## API情報
- **出典**: UN Comtrade Public Preview API
- **URL**: `https://comtradeapi.un.org/public/v1/preview/C/A/HS`
- **認証**: 不要（Preview版は無料・無認証）
- **更新頻度**: 各国データは年単位で随時追加（最新年は遅れて反映）
- **レート制限**: 明示なし、過度な並列は避ける
- **入力単位**: M49 国コード（日本=392, 米国=842, 中国=156 等）、HS品目コード（小麦=1001, 乗用車=8703, 原油=2709 等）

## 使い方

### 単発取得
```bash
# 日本の小麦輸入 2023 上位5
python fetch.py --reporter 392 --hs 1001 --flow M --year 2023 --top-n 5 \
    --output-dir ./output

# 米国の自動車輸出 2022 上位10
python fetch.py --reporter 842 --hs 8703 --flow X --year 2022 --top-n 10
```

### 主要なフラグ
- `--reporter`: M49 国コード（必須）
- `--hs`: HS 品目コード or `TOTAL`（全品目集計）（必須）
- `--flow`: `M`=輸入 / `X`=輸出（default: M）
- `--year`: 対象年（必須）
- `--top-n`: 上位件数（default: 10）

### 出力
- `output/YYYYMMDD_comtrade_{flow}_{reporter}_hs{hs}_{year}_top{n}.csv`
- `output/YYYYMMDD_comtrade_..._metadata.json`

## ハマり所（重要）

### 1. 500件打ち切り → 逆引き集計で解消（最重要）
Public Preview API は **`maxRecords=500` 固定上限**。輸入統計で相手国が500件超える場合、
列挙が途中で打ち切られ、相手国ランキングが不完全になる。

**本レシピの対応（実装済）**: `--reverse auto`（既定）で、輸入が打ち切られたら**逆引き集計**に切替える。
- `MAJOR_EXPORTERS`（工業国＋農産物主要輸出国 計28か国, M49）の各国について、
  「対象国(reporter)向け輸出(flow=X, partnerCode=reporter)」を個別取得し fobvalue を合算
- `--reverse on` で常時逆引き、`--reverse off` で無効。`flow=X`(輸出) には適用しない
- 結果は metadata の `used_reverse_lookup=true` で明示

### 2. 輸出国側と輸入国側の値は非対称（逆引き時の注意）
逆引きは**相手国の輸出統計**を使うため、reporter の輸入統計とは値も順位も食い違う。
例: 日本の小麦輸入(2023)は直接(輸入側)では 米>加>豪 だが、逆引き(輸出側)では **加>米>豪**
（カナダの対日輸出申告がFOBで大きく、日本のCIF輸入申告と非対称）。
逆引きは「打ち切りで相手国が消えるより、輸出側で復元する方がマシ」という**近似**。
正確なシェアが要るときは直接(輸入側)を使い、相手国の網羅が要るときは逆引きを使う、と用途で選ぶ。
逆引き時の World 合計は整合のため逆引き和に統一（輸入側 World とは別物）。

### 3. CIF / FOB の混在
- 輸入統計の value 列は `cifvalue`（運賃・保険込み）
- 輸出統計の value 列は `fobvalue`（本船渡し価格）
- 同じ取引でも CIF と FOB は数値が異なる（CIF > FOB が一般的）
- 本レシピは `cifvalue or fobvalue` のフォールバックで取得しているが、
  メタデータ上はどちらが採用されたかを明示する必要あり（recipe v2で対応予定）

### 4. partnerCode=0 は "World"（合計）
レコードに `partnerCode=0` の行が含まれる場合、それは **個別国ではなく World 合計**。
- ランキングからは必ず除外（本レシピでは `aggregate_by_partner` で対応済）
- World 行は合計シェア計算用に別途保持（`extract_world_total`）

### 5. 自国レコードの混入
`partnerCode == reporter` の行が稀に含まれる場合があるため、本レシピでは除外している。

### 6. qty の単位は HS によって異なる
- HS 1001（小麦）: 通常 kg または tonnes
- HS 8703（乗用車）: 個数（units）
- HS 2709（原油）: barrels または tonnes
- **`qtyUnitAbbr` フィールドで単位を確認すること**
- 本レシピでは qty を raw 値のままCSVに出力。単位変換は recipe を分けるか、
  メタデータの units 欄に記録した上で別途処理

### 7. データ遅延
- 最新年（例: 当年）のデータは数か月遅れで反映される
- 取得時点で空配列が返る場合、年を1〜2年遡って候補年探索する実装が推奨
- 本レシピは年指定のみ。リトライ式の年探索は実装していない（recipe v2 候補）

### 8. customsCode / motCode の指定
本レシピは固定値 `customsCode=C00`（一般通関手続）, `motCode=0`（全運輸モード）を使用。
特殊な通関区分・運輸モードを分析する場合は調整必要。

## 効くケース
- 「日本の○○輸入相手国 トップ5」のような典型的教材データ
- 結果が500件以下に収まる、HSコードがある程度狭い品目（HS6桁レベル等）
- 単一年・単一品目・単一国の取得
- 輸入が500件で打ち切られる広範な品目（TOTAL 等）→ `--reverse` で相手国を復元（輸出側の近似）

## 効かないケース（別レシピ推奨 or 未対応）
| 要求 | 状態 |
|---|---|
| 500件超の品目で相手国を網羅 | **`--reverse` で対応（実装済）**。ただし輸出側の近似値 |
| 500件超で輸入国側の正確なシェア | 構造上不可（Premium API or 別ソース） |
| 多年時系列 | 別レシピ `comtrade/trade_timeseries`（未作成） |
| HS 2桁レベルでの自動集計 | `cmdCode=TOTAL` で代用可、または別レシピ |
| HS品目検索（名前から品目コードを引く） | 別レシピ `comtrade/hs_lookup`（未作成） |
| Premium API（subscription, より広範データ） | スコープ外 |

## 関連レシピ
- `faostat/trade_matrix`（FAOSTATの貿易データ、農産物特化）— 未作成
- `comtrade/trade_timeseries`（多年時系列）— 未作成

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数で受け取り）
- ✅ ファイルI/O は `encoding="utf-8"` 明示
- ✅ コンソール出力 `sys.stdout.reconfigure(encoding="utf-8")` で Win 対応
- ✅ 構造化例外 `DataFetchError` で source/url/kind 保持
- ✅ リトライ3回（HTTPエラー時）
- ✅ metadata.json に request_url / SHA256 / fetched_at / row_count / truncated フラグ記録
- ✅ exit code でエラー伝達
- ✅ APIキー不要（直書きリスクなし）

## このレシピを使うLLMへのヒント

新規の類似データ取得スクリプトを書くとき：
1. **REST API は `httpx.Client(timeout=N)` + リトライ3回** が定石
2. **APIレスポンスのページング・打ち切り上限を必ず確認** — 静かに切り捨てるとシェア計算が崩れる
3. **集計地（partnerCode=0 等）と個別エンティティの区別** — どのAPIにも似た構造あり
4. **複数の同義金額フィールドのフォールバック順** — `cifvalue or fobvalue` のような明示が必要
5. **国コードの表記体系を統一** — M49 / ISO3 / ISO2 のどれを採用するか recipe.md で宣言
6. **APIが返す `qty` の単位はHS依存** — 単位を勝手に解釈せず、`qtyUnitAbbr` を保持する
