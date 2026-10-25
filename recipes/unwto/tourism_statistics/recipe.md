---
id: unwto/tourism_statistics
api: unwto
task: 国際観光の統計（到着客数・観光収入・支出・宿泊・雇用・GDP寄与）を国別に取得
items: [inbound arrivals, inbound expenditure(収入), outbound departures/expenditure, accommodation, employment, tourism direct GDP]
tags: [unwto, un-tourism, tourism, arrivals, receipts, expenditure, country-level, bulk-download, xlsx, no-auth]
summary: UN Tourism（旧UNWTO）の一括ダウンロードzipから観光統計を取る。観光収入は1995〜2024年・214の報告国・地域（2026年5月版）。世界銀行WDIの観光指標は穴だらけなので一次を取る
verified_at: 2026-10-26
complexity: easy
auth_required: false
data_size_mb: 9
---

# unwto / tourism_statistics

## 何をする

UN Tourism（2023年に UNWTO から改称）が公開する **一括ダウンロードzip**（約9MB）から、
国別・年別の観光統計を取る。認証不要。
2026年5月版 zip（`UN_Tourism_bulk_05_2026.zip`）で、観光収入（02_Inbound/02_Expenditure）は **1995〜2024年・214の報告国・地域**
（香港・マカオ・台湾を別に数える。到着客数は215）。ただし**2024年まであるのは121**（2023年まで47・2022年まで15…）で、
年ごとの報告国は 1995年184 → 2015年202 → 2019年193 → 2023年167 → 2024年121（2026-10-26 実測。`references/zip_measured.md`）。

収録は7分野。`Bulk/` の下に分野ごとのxlsxが入る。

| フォルダ | 中身 |
|---|---|
| `01_Domestic` | 国内旅行の回数・宿泊 |
| `02_Inbound` | **到着客数／観光収入**／地域別・目的別・交通手段別到着客数／宿泊 |
| `03_Outbound` | 出国者数・観光支出 |
| `04_Accommodation` | ホテル等の客室数・稼働率 |
| `05_Macroeconomic` | 観光直接GDP（SDG 8.9.1） |
| `06_Employment` | 観光就業者数（SDG 8.9.2） |
| `07_SDGs` | TSA/SEEA の実施状況（SDG 12.b.1） |

## ★なぜ一次を取るのか — World Bank WDI は使えない

WDI に `ST.INT.RCPT.CD`（International tourism, receipts）があるが、

- **中国は 1997〜2004 年の 8 件しかない。** それ以降が無い
- 世界計（WLD）は 2019 年止まり。系列の最終年は 2020年が129、2019年が46（国と集計地域を合わせた数）
（保管庫の WDI_CSV.zip で 2026-10-26 に数えた）

2026-09-15 にこれで「国際観光収入は取得できない」と判断しかけた。**指標が存在して
値が返ってくると、それが全部だと思い込む**のが誤り。UN Tourism 本体には 2024 年まである。

## 取得

```bash
python fetch.py --list                                   # zip の中身を見る
python fetch.py --domain inbound_expenditure --countries China,France,Poland,Mexico
python fetch.py --domain inbound_arrivals --countries Japan --from-year 1995
```

URL は日付でバージョンが変わる（`.../2026-05/UN_Tourism_bulk_data_download_05_2026.zip`）。
リンクは https://www.unwto.org/tourism-statistics/key-tourism-statistics に載る。
`--refresh` でページを見に行って最新の zip を取り直す。

## ハマり所

1. **シートは "Data"。1枚目は "Overview"（説明文だけ）。**
   `sheet_name=0` で読むと説明文の断片が返る。必ず `sheet_name="Data"` を指定する。

2. **「観光収入」は3指標が同じ表に混在する。** `indicator_label` で分けること。
   - `... - total - visitors` … 旅行 ＋ 旅客輸送
   - `... - travel - visitors` … **旅行のみ。教材の「国際観光収入」はこれ**
   - `... - passenger transport - visitors` … 旅客輸送のみ
   合算すると二重計上になる。この zip では total＝travel＋passenger transport が全3,995組（国×年）で差0.21以内で成り立つ
   （例: フランス2019年 total 70,786 = travel 63,424 + passenger 7,362）。

3. **`partner_area_label` の扱いはドメインで変わる。**
   `01_Total_arrivals` や `02_Expenditure` は `World` の行だけが要る（相手先別の内訳行が混ざる）。
   逆に **`03_Total_arrivals_by_region` は内訳が本体**で、`World` で絞ると World の行（33,839行中5,923行）だけになる。`--partner` で切り替える。
   なお**二国間（国×国）の内訳はこの zip に無い**（2026年5月版の全14ドメインを見て、相手先の列があるのは到着・支出系で、値は World か下の地域だけ）。
   相手先の地域は `Africa (UNWTO total)` / `Americas (UNWTO total)` / `East Asia and the Pacific (UNWTO total)` / `Europe (UNWTO total)` /
   `Middle East (UNWTO total)` / `South Asia (UNWTO total)` / `Other not classified (UNWTO total)` / `World`。
   `--partner breakdown` は World 以外を全部残すので「Other not classified」も入る。地域別の合計を出すなら含めるかを決めて注記する。
   「日本とアメリカの往来」のような国ペアは各国の統計（日本なら `jnto/inbound_outbound`）に当たる。

4. **1995年から。1990年は無い。** 1990年基準の指数を使う図は、このデータでは再現できない。
   （観光直接GDP・就業者・SDGs の3分野は2008年から）

5. **単位は分野で違う。必ず `unit` 列で確認する。** 収入・支出は `million US dollars (nominal values)`、
   到着・出国は `thousand trips`、宿泊は `thousand guests` / `thousand overnights`、ホテルは `overnights` / `percent` / `units`。

5b. **到着客数・宿泊などは複数の指標が同じ表に入る。** 到着客数は visitors（計）/ overnight visitors (tourists) /
   same-day visitors / cruise ships の4種。`--indicator-contains` で1つに絞る（絞らないと fetch.py は stderr に出し、
   国別の要約表示はしない。旧版は4種を平均した値を表示していた）。

6. **中国は `China`。香港・マカオ・台湾は別行**
   （`China, Hong Kong Special Administrative Region` / `China, Macao Special Administrative Region` / `Taiwan Province of China`）。
   `China` の行に香港・マカオ・台湾を足し込んだ集計値かどうかは、ラベルからは分からない（UN Tourism の注記で確かめる）。
   教材で「中国」に香港等を含めるかは方針で決める。

7. **世界計の行は無い**（報告国・地域のラベルに World・大陸名は無い）。シェアを出すなら国の合計を自分で取る。
   報告国が年で変わる（上の数）ので分母が動く。metadata に `n_reporters` と `scope` を書く。

8. **ダウンロードに User-Agent が要る。** `Python-urllib` のままだと Cloudflare に当たる。

## 出典表記

> UN Tourism（国連世界観光機関）の資料により作成。統計年次は◯◯年。

元の図が「UNWTO」表記なら、2023年の改称を踏まえて「UN Tourism（旧UNWTO）」とするか、
元の表記に合わせるかを決めること。
