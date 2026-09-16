---
id: world_bank/country_indicator
api: world_bank
task: 国別インジケータ取得（ranking / trend）
items: [GDP, 人口, 教育, 健康, 経済等の World Bank 全インジケータ]
tags: [world_bank, indicator, ranking, timeseries, country-level, rest-api, no-auth, json-paginated]
summary: World Bank Indicators API V2 から指定インジケータの国別ランキング or 時系列を取得
verified_at: 2026-05-18
complexity: medium
auth_required: false
data_size_mb: 0  # ライブAPI
---

# world_bank / country_indicator

## 何をする
World Bank Indicators API V2 から、任意のインジケータ（GDP, 人口, 教育, 健康 等）を指定国群について取得し、**最新値のランキング** または **時系列**を CSV + metadata.json に出力する。

## API情報
- **出典**: World Bank Open Data — Indicators API V2
- **エンドポイント**: `https://api.worldbank.org/v2/country/{cc1};{cc2}/indicator/{indicator}`
- **認証**: 不要
- **形式**: JSON（XML も選べるが本レシピは JSON）
- **レート制限**: 公式記載なし、ただし `per_page` 上限 1000
- **インジケータカタログ**: https://data.worldbank.org/indicator
- **更新頻度**: 月次〜年次、インジケータごと

## よく使うインジケータコード（参照表）

| 用途 | コード | 単位 |
|---|---|---|
| 名目GDP | `NY.GDP.MKTP.CD` | current US$ |
| 1人当たりGDP | `NY.GDP.PCAP.CD` | current US$ |
| 人口総数 | `SP.POP.TOTL` | 人 |
| 都市人口割合 | `SP.URB.TOTL.IN.ZS` | % |
| 合計特殊出生率 | `SP.DYN.TFRT.IN` | 1人あたり子供数 |
| 平均寿命 | `SP.DYN.LE00.IN` | 年 |
| 識字率（成人） | `SE.ADT.LITR.ZS` | % |
| 失業率 | `SL.UEM.TOTL.ZS` | % |
| 外国生まれ人口（割合） | `SM.POP.TOTL.ZS` | % |
| 外国生まれ人口（実数） | `SM.POP.TOTL` | 人 |
| 知的財産使用料 受取（≒技術輸出） | `BX.GSR.ROYL.CD` | current US$ |
| 知的財産使用料 支払（≒技術輸入） | `BM.GSR.ROYL.CD` | current US$ |
| CO2排出量（1人当たり） | `EN.ATM.CO2E.PC` | t/person |

## 使い方

### ranking モード（最新値の国別順位）
```bash
# GDP 上位30か国
python fetch.py --indicator NY.GDP.MKTP.CD --mode ranking --top-n 30 \
    --output-dir ./output

# 1人当たりGDP 上位20（任意の国群）
python fetch.py --indicator NY.GDP.PCAP.CD --mode ranking --top-n 20 \
    --countries USA,CHN,JPN,DEU,IND,GBR,FRA,ITA,CAN,BRA \
    --output-dir ./output
```

### trend モード（指定国の時系列）
```bash
# 日韓中の人口推移 2015年以降
python fetch.py --indicator SP.POP.TOTL --mode trend \
    --countries JPN,KOR,CHN --year-from 2015 --output-dir ./output
```

### 主要フラグ
| フラグ | 意味 |
|---|---|
| `--indicator` | WB インジケータコード（必須） |
| `--mode` | `ranking`（最新値順位） / `trend`（国×年） |
| `--countries` | ISO3 カンマ区切り。省略時は主要50か国 |
| `--top-n` | ranking の上位件数（default: 30） |
| `--year-from` | trend の開始年（default: 2000） |
| `--mrv` | Most Recent Values の取得年数（default: 10） |

## ハマり所（重要）

### 1. レスポンスは `[meta, data]` の2要素配列（**最重要**）
World Bank API のレスポンスは特殊：
```json
[
  {"page": 1, "pages": 1, "per_page": 500, "total": 490},
  [
    {"countryiso3code": "USA", "date": "2024", "value": 28750956130731.0, ...},
    {"countryiso3code": "CHN", "date": "2024", "value": 18743803170827.0, ...},
    ...
  ]
]
```
- `data[0]` = メタデータ（page, total等）
- `data[1]` = **実際の値配列**（これを使う）
- **エラー時は `[{"message": [...]}]` のように1要素しか返らない**

```python
# ❌ 危険: 値配列を期待して data を直接使う
rows = r.json()  # → ページ情報を rows と勘違い

# ✅ OK: 2要素チェック
data = r.json()
if not isinstance(data, list) or len(data) < 2:
    raise DataFetchError(...)  # エラーレスポンス
rows = data[1] or []
```

### 2. null value が大量に混入
全インジケータ × 全国 × 全年 で **欠損値が大量** にある。
ある国の最新値が `null` のことも、ある年だけ抜けることもある。

```python
# ✅ 必須: value=null を除外してから最新年を探す
for r in rows:
    if r.get("value") is None:
        continue
    ...
```

### 3. 同一国に複数年のレコードが返る
`mrv=10` を指定すると、各国について **直近10年分** のレコードが全部返ってくる（最新値1点ではない）。
ranking モードでは、**各国で最新の非null年を抽出** する処理が必要。

```python
# 国ごとに最新非null を抽出
by_cc = {}
for r in rows:
    cc = r["countryiso3code"]
    yr = int(r["date"])
    if cc not in by_cc or yr > int(by_cc[cc]["date"]):
        by_cc[cc] = r
```

### 4. mrv と per_page の使い分け
- `mrv=N` = Most Recent Values N年分（各国ごと）
- `per_page=M` = ページサイズ（全レコード合計）
- 国数 × mrv が per_page を超えると **ページングが必要**

50か国 × 10年 = 500レコード → per_page=500 で1ページに収まる。
ただし50か国 × 50年 = 2500レコード → per_page=500 だと5ページに分かれる。

本レシピは `per_page=500` 固定。50か国超 or mrv=50超 だとページング処理が必要（未実装）。

### 5. 国コードは ISO3
World Bank は ISO3 alpha 標準。例: 日本=JPN, 米国=USA。
**FAOSTAT (Area name) や e-Stat (5桁) とは互換性なし** → 結合時に変換テーブル要。

特殊な扱い：
- `HKG` = Hong Kong SAR, China
- `TWN` = Taiwan, China（中国の一部として扱う）
- `KOR` = Korea, Rep.（南朝鮮）
- `PRK` = Korea, DPR.（北朝鮮）
- 集計地域（"WLD"=World, "EUU"=European Union 等）も国コード扱いで返るので、ranking で除外したい場合は明示フィルタ必要

### 6. country フィールドの構造
レスポンスの `country` フィールドは **dict 形式**:
```json
"country": {"id": "JP", "value": "Japan"}
```
ISO2 と国名がそこに入っている。`countryiso3code` は別フィールド。

### 7. date は文字列、value は数値（または null）
- `date`: 文字列（"2024" であって 2024 ではない）
- `value`: float または null
- 比較・ソート時に型キャスト必須

### 8. インジケータ名のクエリは大文字小文字区別
`NY.GDP.MKTP.CD` ≠ `ny.gdp.mktp.cd`。**全角大文字で書く**。

### 9. ヒストリカルな国境変更
- USSR / SUN — 1991年に解体。それ以前のデータはあるが ISO3 が異なる
- Yugoslavia / YUG, SCG — 解体国
- East/West Germany — 1990年統合前のデータは別コード
- 古い年のデータを取る時は **国コード変遷を確認**

### 10. レート制限と並列化
World Bank API はおおむね寛容だが、**1秒あたり10リクエスト超えると 503 が返る** ことがある。
本レシピは1リクエストで全国分取得するため問題なし。
複数インジケータを並列で叩く場合は `asyncio.gather` + セマフォで5並列程度に抑制推奨。

### 11. TWN（台湾）を含むと多国一括クエリが 4xx になる（2026-05-23 検証）
**症状**:
- `country/USA;CHN;...;TWN;...` のような多国 `;` 連結クエリで `TWN` を含むと、HTTP 400/404 が返ることがある。
- TWN 単独や TWN を除外したリストは 200 OK。

**原因**:
- World Bank API は TWN を国コードリストに持つが、多くの indicator で台湾データを中国に統合しており **`page=0/total=0` を返す**。
- 多国一括時に「データなし国」が混ざるとレスポンス組立てが失敗する模様（API 側仕様、ドキュメント明記なし）。

**対策**:
- `DEFAULT_COUNTRIES` から **TWN を除外**（本 fetch.py は対応済、49カ国構成）。
- 台湾を明示的に欲しい場合は `--countries TWN` で単独取得する（ただし値は空）。

```python
# ❌ ダメな例: TWN を含む50カ国一括
"https://api.worldbank.org/v2/country/USA;CHN;...;TWN;...;KEN/indicator/NY.GDP.MKTP.CD"
# → HTTP 400/404

# ✅ OK: TWN を除外した49カ国
"https://api.worldbank.org/v2/country/USA;CHN;...;KEN/indicator/NY.GDP.MKTP.CD"
# → HTTP 200、全国分取得
```

**注意**:
- 同様の「データなし国」が他にも潜在する可能性（XKX=コソボ等）。新規 indicator を試す時は 200 OK を必ず検証する。

## 効くケース
- 「世界GDP上位30」「主要国の人口推移」「OECD加盟国の失業率」等の典型的教材データ
- 任意インジケータ × 任意国群の最新値ランキング
- 主要50か国 default リストでカバーできる範囲

## 効かないケース（別レシピ推奨）
| 要求 | 推奨レシピ | 状態 |
|---|---|---|
| 複数インジケータの結合（GDP × 人口 → 1人あたり計算） | `world_bank/multi_indicator` | 未作成 |
| 全世界217か国の取得 | `world_bank/all_countries`（ページング対応） | 未作成 |
| 地域・所得階級別ランキング | `world_bank/aggregate_groups` | 未作成 |
| 古い国コード（USSR等）の遡及 | 別レシピ要、変換テーブル必要 | 未作成 |

## 関連レシピ
- `un_wpp/population_ranking`（WB 人口データと整合性検証可）
- `faostat/crops_ranking`（同じ ISO3 で結合可能）

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点
- ✅ ファイルI/O は `encoding="utf-8"`
- ✅ コンソール出力 `sys.stdout.reconfigure(encoding="utf-8")`
- ✅ 構造化例外 `DataFetchError`
- ✅ リトライ3回
- ✅ metadata.json に request_url / SHA256 / fetched_at / row_count
- ✅ APIキー不要
- ✅ レスポンス形式の検証（2要素配列チェック）

## このレシピを使うLLMへのヒント

新規の REST API レシピを書くとき：

1. **API レスポンスの構造を recipe.md に必ず記録** — World Bank の `[meta, data]` 構造のような特殊な仕様は、ドキュメント読まないと分からない
2. **null 値の処理を最初に書け** — 統計APIは欠損が大量にある、`value is None` 除外を最初に
3. **「最新値ランキング」と「時系列」は別モード化** — 1つの関数に詰め込むと条件分岐が複雑になる
4. **国コードは ISO3 を標準とする** — 他APIと結合する時の基準点
5. **レスポンスの `country` フィールドが dict の場合あり** — `r["country"]["value"]` のような階層アクセスを忘れない
6. **mrv vs per_page の混同に注意** — 各国の値数と全体ページサイズは別物
