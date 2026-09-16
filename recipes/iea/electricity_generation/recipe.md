---
id: iea/electricity_generation
api: iea
task: 国別・電源別の年次発電量取得（1990–）
items: [発電量, 電源別発電量, 火力内訳, 化石一括]
tags: [iea, electricity, generation, by-source, country-level, data-browser, ttl-cache, free]
summary: IEA Energy Statistics Data Browser から指定国の電源別年次発電量（TWh, 1990–）を無料取得
verified_at: 2026-06-22
complexity: medium
auth_required: false
data_size_mb: 1  # 国あたり数百KBの JSON
---

# iea / electricity_generation

## 何をする
IEA のエネルギー統計データブラウザ（＝Webで「CSVダウンロード」できるのと同一データ）の
バックエンドを叩き、指定国・期間の**電源別・年次発電量**を **TWh** で CSV + metadata.json に保存する。
火力内訳（石炭・石油・天然ガス）まで分解され、原子力・水力・風力・太陽光・バイオ等も個別に取れる。

## API情報
- **出典**: IEA — Energy Statistics Data Browser（World Energy Statistics & Balances）
- **URL**: `https://api.iea.org/stats?series=ELECTRICITYANDHEAT&countries=<CODE>`
- **認証**: 不要（無料・データブラウザのバックエンド。手動CSVダウンロードと同一データ）
- **形式**: JSON 配列。1行 = 国×年×flow×product。`product="ELECTR"`（電力）を抽出（"HEAT" は熱）
- **年範囲**: **1990–（当年-2 程度まで確定）**。この経路の下限は 1990 年
- **単位**: 原系列は **GWh** → 本レシピで **TWh** に換算（/1000）
- **TTL**: 国別 JSON を mtime ベースでキャッシュ（default 30日）

## 使い方
```bash
# 5か国・電源別 1990–2024
python fetch.py --countries USA,FRANCE,GERMANY,DENMARK,SWEDEN \
    --year-from 1990 --year-to 2024 --output-dir ./output

# 単一国（最新まで）
python fetch.py --countries JAPAN --output-dir ./output
```
出力: 国ごとに `YYYYMMDD_iea_electricity_<code>_<y0>_<y1>.csv`（year + 電源列, TWh）と metadata.json。

### 主要フラグ
| フラグ | 意味 |
|---|---|
| `--countries` | IEA国コード カンマ区切り（**大文字フルネーム**: USA, FRANCE, GERMANY, DENMARK, SWEDEN, JAPAN, CHINA …） |
| `--year-from` / `--year-to` | 年範囲（下限は1990） |
| `--ttl-days` | キャッシュ有効日数（default 30） |
| `--cache-dir` | JSONキャッシュ先（default `~/.cache/iea`） |

## ハマり所（重要）

### 1. 国コードは「大文字フルネーム」（最重要・LLMが幻覚しやすい）
`?country=` ではなく **複数形 `?countries=`**。小文字や `?COUNTRY=` は別仕様（mes 月次）。
**正しい国コードを表からコピーすること**（ローカルLLMが GERMANY を `DEUTHERY` 等に幻覚した実例あり 2026-06-22）：

| 国 | コード | 国 | コード |
|---|---|---|---|
| 米国 | `USA`（✕`UNITEDSTATES`＝地域群に誤爆） | 日本 | `JAPAN` |
| フランス | `FRANCE` | ドイツ | `GERMANY`（✕`DEUTHERY`/`DEUTSCHLAND`） |
| デンマーク | `DENMARK` | スウェーデン | `SWEDEN` |
| 英国 | `UNITEDKINGDOM` | 中国 | `CHINA` |
| 韓国 | `KOREA` | インド | `INDIA` |

不明な国は IEA データブラウザの URL で確認してから使う（`fetch.py` は既知リスト外で warn を出す）。

### 1b. 正確性ガード（fetch.py 実装済）
不正コードはエラーにならず**ゴミ応答**を返すことがある（内訳合計＞総生産 等、内部矛盾）。
`fetch.py` は `_sanity_check` で「電源内訳の合計 > 総生産(EHINDPROD)×1.1」を検出して `DataFetchError` で落とす。
**smoke test（構造検査）は通っても中身が壊れている事故**を防ぐための砦（検証はモデルでなくコードで）。

### 2. product="ELECTR" でフィルタ（電力 ≠ 熱）
同じエンドポイントに熱（HEAT）の行も混在。発電量が欲しいなら **`product=="ELECTR"` 必須**。

### 3. flow コードを知らないと使えない（電源別の肝）
| flow | 電源 | flow | 電源 |
|---|---|---|---|
| `EHCOAL` | 石炭 | `EWIND` | 風力 |
| `EHOIL` | 石油 | `ESOLARPV` | 太陽光PV |
| `EHNATGAS` | 天然ガス | `EHBIOMASS` | バイオ燃料 |
| `EHNUCLEAR` | 原子力 | `EHGEOTHERM` | 地熱 |
| `EHYDRO` | 水力 | `ETIDE` | 潮汐 |
| `EHMUNWASTR` | 再生可能廃棄物 | `EHINDPROD` | **総生産（合計）** |

化石一括 = `EHCOAL+EHOIL+EHNATGAS`。`EHINDPROD` が総発電量（gross）。

### 4. 単位は GWh（→TWh換算必須）
`value` は GWh。教材は TWh が多いので /1000。metadata に明記する。

### 5. null は欠損（0埋めしない）
`value=null` の行あり → skip。0 と欠損を混同しない（CLAUDE.md 規約）。

### 6. gross（総生産）であること / OWID との差
- IEA は **gross（総生産 EHINDPROD）**。OWID `electricity_generation` は gross だが**分散型太陽光推計込み**で太陽光がやや大きい。
- **最新年**: IEA は当年-2 程度（年次確定）。OWID は Ember 速報込みで前年・当年に踏み込む。
- **混在禁止**: 定義差で段差が出る。**ソースは IEA なら IEA で統一**する。

### 7. 残差「その他」の作り方（積み上げ図）
電源を積み上げると `EHMUNWAST`（非再生廃棄物）・`EHWASTE`・`EHOTHER`・統計差が残る。
`その他 = EHINDPROD − 計上分（>=0）` で吸収し、metadata に内訳を明記する。

### 8. デンマーク等の早期年
IEA系列は全国 **1990年始まり**（それ以前は無い）。ただし 1990 以降は化石内訳も欠損なく揃う
（OWIDは1985–だがデンマークの化石内訳が1985–89欠損→アーティファクト。IEAは構造的に発生しない）。

## 効くケース
- 電源別発電量の長期推移（1990–）を**IEA一次データで**作りたい（出典をIEAに統一）
- 火力内訳（石炭/石油/天然ガス）まで分解した積み上げ面グラフ
- 多国比較（同一定義・同一単位で複数国を並べる）

## 効かないケース（別手段）
| 要求 | 手段 |
|---|---|
| 当年・前年の速報値 | OWID（Ember速報込み）or IEA Monthly Electricity Statistics（`api.iea.org/mes`, 2010–月次） |
| 1990年より前 | IEAの有料製品 *Electricity Information*（1960/1971–, OECD）。この無料経路では不可 |
| 一次エネルギー構成（発電でなく資源投入） | `owid/energy_data`（概念が別） |

## 関連レシピ
- `owid/energy_data` — 同種の発電量を統合データ（IEA+Ember+EI）で。速報年・分散型太陽光込みが要るとき
- 実体例: `electricity_by_source_compare4_p000/scripts/make_iea.py`（5か国・化石一括・2×3比較図）

## 規約準拠状況
- ✅ パスは `Path(__file__)` / 引数基点、ハードコード絶対パスなし
- ✅ ファイルI/O `encoding="utf-8"` / `sys.stdout.reconfigure`
- ✅ 構造化例外 `DataFetchError` / リトライ3回 / TTLキャッシュ
- ✅ metadata.json に source URL / SHA256 / row_count / 単位 / 欠損処理
- ✅ APIキー不要 / Python 3.9 互換（`X | None` を使わない）

## このレシピを使うLLMへのヒント
1. **国コードは大文字フルネーム＋`countries=`（複数形）** を疑え（`UNITEDSTATES`誤爆・`USA`正）
2. **product="ELECTR" と flow コード表** が無いと電源別にできない → recipe を見る
3. **GWh→TWh** 換算と **gross/OWID差** を metadata に明記
4. **混在禁止**: 図1枚は単一ソース（IEAならIEA）で。OWIDと年でつながない
