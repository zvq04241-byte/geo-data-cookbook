---
id: aquastat/water_resources
api: aquastat
access_layer: world_bank_data360
tags: [aquastat, water, water-resources, irwr, trwr, renewable-water, per-capita, country-level, data360, rest-api, no-auth]
items_supported: [TRWR(総), IRWR(国内), 1人当たり(4190), 外来依存率(算出＋4192で検算)]
pattern: data360-rest-api + variable-id-verification + per-capita-derivation
auth_required: false
verified_at: 2026-10-26
complexity: medium
gotcha_count: 7
---

# AQUASTAT 国別 水資源賦存量（国内IRWR・総TRWR・1人当たり）

## 何をする

FAO AQUASTAT の国別水資源指標を取得する。
- **総 TRWR**（Total renewable water resources）＝ 国内産＋外来（上流国からの流入）
- **国内 IRWR**（Total internal renewable water resources）＝ 自国内で生成される分
- **1人当たり**（AQUASTAT の `4190`）と **外来依存率**（(TRWR−IRWR)/TRWR を算出し、AQUASTAT の依存率 `4192` で検算）

「総と国内の差＝外来河川（上流）への依存」が見えるのが眼目（エジプト＝ナイル下流98%、
パキスタン＝インダス78%、ナイジェリア＝ほぼ自給23%、サウジ＝河川なし0%）。

## API情報

- **AQUASTAT のネイティブ API/バルクは公開エンドポイントが辿りにくい**（fao.org 側はクエリUIのみ、
  data.apps.fao.org の dissemination CSV は降水・IRWR の格子サブセットで TRWR が無い）。
- そこで **World Bank Data360 の FAO_AS（AQUASTAT 公式ミラー）** を取得層に使う。認証不要。
  - データ: `GET https://data360api.worldbank.org/data360/data?DATABASE_ID=FAO_AS&INDICATOR=<code>&REF_AREA=<ISO3>`
  - 指標一覧: `GET https://data360api.worldbank.org/data360/indicators?datasetId=FAO_AS`
  - 指標コード ＝ `FAO_AS_<AQUASTAT変数ID>`
- 使用変数: 総TRWR=`FAO_AS_4188` / 国内IRWR=`FAO_AS_4157` / 1人当たりTRWR=`FAO_AS_4190` / 依存率=`FAO_AS_4192`
  （総人口 `FAO_AS_4104` は 2026-10-26 に指標一覧から消えていた。ハマり所3）
- レスポンス: `{"count": N, "value": [ {OBS_VALUE, TIME_PERIOD, UNIT_MULT, UNIT_MEASURE, OBS_STATUS, LATEST_DATA, ...}, ... ]}`

## 使い方

```bash
python fetch.py --countries EGY,SAU,PAK,NGA --year 2022 --output-dir ./output
python fetch.py --countries EGY,SAU,PAK,NGA              --output-dir ./output  # 各指標の最新年
```
出力: `<date>_aquastat_water_resources.csv` ＋ `_metadata.json`（source/SHA256/年/取得時刻）。
metadata の `skipped` に指標が欠けて出さなかった国、`year_fallback` に指定年が無く最新年に落ちた 国:指標 が残る。

検証済み参照値（2022年, km3/yr）:
| 国 | 国内IRWR | 総TRWR | 外来% | 1人当(m3) |
|---|---|---|---|---|
| エジプト | 1.0 | 57.5 | 98% | 511 |
| サウジアラビア | 2.4 | 2.4 | 0% | 75 |
| パキスタン | 55.0 | 246.8 | 78% | 1013 |
| ナイジェリア | 221.0 | 286.2 | 23% | 1283 |

## ハマり所（実テストで遭遇したものを記録）

1. **総IRWRは `4157`。`4187` ではない。** 直感的に「4188=TRWR の隣の 4187=IRWR」と当てると**間違う**。
   `FAO_AS_4187` はナイジェリアで **87**（地下水成分の部分値）を返すが、ナイジェリアの総IRWRは **221**＝`FAO_AS_4157`。
   エジプト・パキスタンでは 4187 と 4157 が近接するため気づけない。**国内外で差が大きい国（ナイジェリア=221）で必ず検算**すること。
   - 回避: `FAO_AS_4157` を使い、公表値（NGA IRWR≈221, TRWR≈286）と1件照合する。

2. **urllib は User-Agent なしで `403 Forbidden`。** `httpx` は既定UAがあるため通るが、`urllib.request` は
   ヘッダ無指定だと弾かれる。`headers={"User-Agent": "Mozilla/5.0 ..."}` を必ず付ける。

3. **指標は Data360 から消えることがある。** 2026-06-12 には `FAO_AS_4174` が空で、`4188 ÷ 総人口 4104` で1人当たりを算出していた。
   2026-10-26 には **4104 も 4174 も指標一覧（`/data360/indicators?datasetId=FAO_AS`、112本）に無く、値0件**だった。
   旧コードは4か国とも「欠損」で止まった。→ 今は AQUASTAT 自身の **`4190`（1人当たり TRWR, m3/inhab/yr, `UNIT_MULT=0`）** を使う。
   2022年の4か国で、旧算出値（511・75・1013・1283）と1 m3 の位まで一致した。人口は TRWR ÷ 4190 で逆算して参考に出す。
   単位係数に注意: TRWR は `UNIT_MULT=9`（×10^9 m3）。使う前に指標一覧に載っているかを確かめる。

4. **`OBS_VALUE` は文字列**（"57.5"）。`float()` 必須。`UNIT_MULT` も文字列ではなく int だが、
   桁合わせ（×10^UNIT_MULT）を忘れると 10^9 倍ずれる。本レシピは内部で m3 に正規化してから km3 へ戻す。

5. **TRWR/IRWR は長期平均で年変化しない。** 時系列(1961〜)に**同じ値が延々と並ぶ**。
   「最新年だけ違う値」ではないので、`LATEST_DATA` フラグ or 対象年フィルタでどの年を拾っても値は同じ。
   ただし**1人当たりは人口で年変化する**ので、年を**揃える**（本レシピは `--year` で固定可。指定年が無い指標は最新年に落ち、`year_fallback` に残る）。

6. **`OBS_STATUS` は配信側で変わる。この列で推計かどうかを決めない。**
   2026-06-12 の出力（`output/`）では4か国とも TRWR が `I`。2026-10-26 に全件を取り直すと、
   TRWR（4188）11,033行・189か国、IRWR（4157）10,527行・181か国の**すべてが `A`** だった。
   値は同じ（エジプトの TRWR は 57.5 のまま）で、符号だけが変わっている。出力には `obs_status_trwr`・`obs_status_irwr` を残すが、
   E/I/A を図の注記に使うときは、取得日の値であることを書く。欠損は value=[] で表れる。

7. **国名は ISO3（REF_AREA）。** 本レシピは国を明示指定する（全件を取って並べる機能は無い）。
   2026-10-26 に 4188・4157 を全件取ったときは、REF_AREA はすべて英字3文字で、集計らしいコードは見当たらなかった。
   全件で順位を付ける場合は、M49 等の国の表と照らしてから並べる。

## 効くケース

- アフリカ・西アジア・南アジアなど**水資源の偏在・国際河川依存**を問う地誌教材。
- 「総と国内の差＝上流依存」「賦存量大≠1人当たり大（人口圧）」を判別軸にした統計問題。
- 乾燥国の水ストレス（1人当たり <1000 m3 が water scarcity の目安＝Falkenmark）。

## 効かないケース（別レシピ推奨）

- 取水量・灌漑・用途別需要など水「利用」側の細目 → AQUASTAT の他変数（4188/4157/4190/4192 以外）。本レシピは賦存量の指標に限定。
- 流域・小地域（sub-national）や格子データ → `data.apps.fao.org` の dissemination CSV（precipitation/irwr-km3 等）。ただし TRWR は無い。
- 純粋な人口だけが欲しい → `un_wpp/population_ranking`（本レシピの人口は 1人当たりからの逆算で、参考値）。

## 規約準拠状況

- `Path(__file__)` 基点（ハードコードパス無し）／`encoding="utf-8"`／書き込み `newline="\n"`。
- 構造化例外 `DataFetchError`／HTTPエラー時リトライ3回。
- `metadata.json` 同時出力（source / 指標コード / SHA256 / 年 / retrieved_at / row_count / scope / skipped / year_fallback）。
- `sys.stdout.reconfigure` 相当（`TextIOWrapper(...,encoding="utf-8")`）で Win cmd.exe 対策。
- 認証なし（appId 漏洩リスク無し）。

## このレシピを使うLLMへのヒント

- **最優先で「総IRWR=4157」を守る**（ハマり所1）。4187 を使うと外来依存率が国によって過大評価になり、
  判別問題なら正解が変わりうる。生成後は必ずナイジェリア IRWR=221 で1件検算する。
- 1人当たりは AQUASTAT の `4190`。年を揃える（ハマり所3・5）。設問で「統計年次」を書くなら全指標同一年（例 2022）に固定。
- `OBS_STATUS` は取得日で変わる（ハマり所6）。出典表記は「FAO AQUASTAT（World Bank Data360 経由）」とし、年次を明記する。
