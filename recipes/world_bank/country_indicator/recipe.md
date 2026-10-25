---
id: world_bank/country_indicator
api: world_bank
task: 国別インジケータ取得（ranking / trend）
items: [GDP, 人口, 教育, 健康, 経済等の World Bank 全インジケータ]
tags: [world_bank, indicator, ranking, timeseries, country-level, rest-api, no-auth, json-paginated]
summary: World Bank Indicators API V2 から指定インジケータの国別ランキング or 時系列を取得
verified_at: 2026-10-26
complexity: medium
auth_required: false
data_size_mb: 0  # ライブAPI
---

# world_bank / country_indicator

## 何をする
World Bank Indicators API V2 から、任意のインジケータ（GDP, 人口, 教育, 健康 等）を指定国群について取得し、**最新値のランキング** または **時系列**を CSV + metadata.json に出力する。

**順位の母集団は3通り。出力に必ず書き出す**（CSV の `scope` 列と metadata の `scope`）:
| 指定 | 母集団 | scope の例 |
|---|---|---|
| `--all-countries` | 集計地域を除く全ての国・地域（2026-10-26 時点 217） | 集計地域を除く全217か国・地域の中での順位（値のある212か国・地域） |
| 省略 | 手で並べた既定49か国（**世界順位ではない**） | 既定49か国の中での順位（世界順位ではない。値のある49か国） |
| `--countries` | 指定した国 | 指定した10か国の中での順位（値のある10か国） |

「世界の上位N」と書くなら `--all-countries` を使う。既定49か国の外の国が上位に入る指標は多い（1人当たりGDP・比率・資源の指標など）。
ranking では集計地域（WLD・EUU・所得階層など）を必ず除く。判定は国メタデータ（`/v2/country`）の region が `Aggregates` のもの。
所得階層の集計（High income 等）は `countryiso3code` が空で返るので、これも順位に入らない。除いたものは metadata の
`dropped_aggregates`・`dropped_rows_without_iso3` に残る。各国の最新非null年で並べるので年が揃わないことがある（`year_min`・`year_max`）。

## API情報
- **出典**: World Bank Open Data — Indicators API V2
- **エンドポイント**: `https://api.worldbank.org/v2/country/{cc1};{cc2}/indicator/{indicator}`
- **認証**: 不要
- **形式**: JSON（XML も選べるが本レシピは JSON）
- **レート制限**: 公式の数値は確認していない。本レシピは `per_page=1000` で取り、`pages` を辿って全件を結合する
- **インジケータカタログ**: https://data.worldbank.org/indicator
- **更新日**: インジケータごとに違う。応答の先頭 `lastupdated` で確かめる（2026-10-26 に取った GDP は 2026-10-08）

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
# GDP 上位30か国（集計地域を除く全ての国・地域の中で＝世界順位）
python fetch.py --indicator NY.GDP.MKTP.CD --mode ranking --top-n 30 \
    --all-countries --output-dir ./output

# 指定した10か国の中での1人当たりGDPの順位（世界順位ではない。出力は最大10行）
python fetch.py --indicator NY.GDP.PCAP.CD --mode ranking --top-n 10 \
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
| `--countries` | ISO3 カンマ区切り。省略時は既定49か国（世界順位ではない） |
| `--all-countries` | 集計地域を除く全ての国・地域（`--countries` と同時に使えない） |
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

49か国 × 10年 = 490レコード → 1ページに収まる。全ての国・地域（集計地域を含め266）× 10年 = 2,660レコード → 3ページ。

本レシピは `per_page=1000` で取り、`pages` を辿って全ページを結合する。取得件数が `total` に届かなければ止まる（`INCOMPLETE_PAGING`）。

### 5. 国コードは ISO3
World Bank は ISO3 alpha 標準。例: 日本=JPN, 米国=USA。
**FAOSTAT (Area name) や e-Stat (5桁) とは互換性なし** → 結合時に変換テーブル要。

特殊な扱い：
- `HKG` = Hong Kong SAR, China
- `TWN` = Taiwan, China（中国の一部として扱う）
- `KOR` = Korea, Rep.（南朝鮮）
- `PRK` = Korea, DPR.（北朝鮮）
- 集計地域（"WLD"=World, "EUU"=European Union 等）も国コード扱いで返る。本レシピの ranking は国メタデータの region が `Aggregates` のものを除く（`fetch_aggregate_codes`）。trend は除かない（世界計の推移を取りたいことがあるため）

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
レート制限の公式の数値は確認していない（測ってもいない）。
本レシピは1つのインジケータを1本の URL（＋ページ）で取るので、並列にはしない。
複数インジケータを並列で叩くなら同時接続を少数に抑え、503 や接続切れが出たら間隔を空けて再試行する。

### 11. TWN（台湾）は値が返らない
- `country/TWN/indicator/NY.GDP.MKTP.CD` は `page=0/total=0`・値 `null`（2026-10-26 に確認）。台湾の値は World Bank では取れない
- 2026-05-23 に「TWN を含む多国一括で HTTP 400/404」を観測して既定から外した（記録は残っていない）。
  2026-10-26 に既定49か国＋TWN で再試行すると **200 OK・490件**（TWN は0件）で、4xx は再現しなかった。原因は分かっていない
- 既定49か国は TWN を外したまま。`--countries` に値の返らない国を入れたときは metadata の `countries_without_value` に出る
- 新しい国コード・インジケータを試すときは、応答が 200 で件数が `total` と合うことを確かめる

### 12. 航空旅客数・航空貨物は「航空会社の登録国」で数えた値（2026-10-21）
`IS.AIR.PSGR`（航空旅客数）・`IS.AIR.GOOD.MT.K1`（航空貨物）は、ICAO の統計を
**航空会社の登録国ごと**に足した値で、**その国の空港の利用者ではない。**
格安航空会社の本拠がある国が大きく出る。2023年の `IS.AIR.PSGR` を集計地域を除く全ての国・地域で並べると、
アメリカ合衆国・中国に次いで**アイルランドが3位**（1億9,253万人。2026-10-26 に API で確認。アイルランドを本拠とする大手格安航空会社の旅客が入るため）。
- 国の航空の大きさ・ハブ空港の話には使わない。空港の側で数えた値（ACI の空港別旅客数・`aviation/airport_passengers`）を使う
- どうしても使うときは「航空会社の登録国で数えた値」と注記し、外れて出る国の理由を書く

## 効くケース
- 「世界GDP上位30」（`--all-countries`）「主要国の人口推移」「OECD加盟国の失業率」（`--countries` で加盟国を渡す）
- 任意インジケータ × 任意国群の最新値ランキング（母集団は `scope` に出る）

## 効かないケース（別レシピ推奨）
| 要求 | 推奨レシピ | 状態 |
|---|---|---|
| 複数インジケータの結合（GDP × 人口 → 1人あたり計算） | `world_bank/multi_indicator` | 未作成 |
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
