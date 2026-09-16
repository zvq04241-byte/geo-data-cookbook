---
id: unwto/tourism_statistics
api: unwto
task: 国際観光の統計（到着客数・観光収入・支出・宿泊・雇用・GDP寄与）を国別に取得
items: [inbound arrivals, inbound expenditure(収入), outbound departures/expenditure, accommodation, employment, tourism direct GDP]
tags: [unwto, un-tourism, tourism, arrivals, receipts, expenditure, country-level, bulk-download, xlsx, no-auth]
summary: UN Tourism（旧UNWTO）の一括ダウンロードzipから観光統計を取る。1995〜2024年・214か国。世界銀行WDIの観光指標は穴だらけなので一次を取る
verified_at: 2026-09-15
complexity: easy
auth_required: false
data_size_mb: 9
---

# unwto / tourism_statistics

## 何をする

UN Tourism（2023年に UNWTO から改称）が公開する **一括ダウンロードzip**（約9MB）から、
国別・年別の観光統計を取る。**1995〜2024年・214か国**。認証不要。

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
- 世界計（WLD）は 2019 年止まり、多くの国は 2020 年止まり

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
   合算すると二重計上になる。2026-09-15 に実際にやった。

3. **`partner_area_label` の扱いはドメインで変わる。**
   `01_Total_arrivals` や `02_Expenditure` は `World` の行だけが要る（相手先別の内訳行が混ざる）。
   逆に **`03_Total_arrivals_by_region` は内訳が本体**で、`World` で絞ると中身が消える。
   2026-09-15、一律に World で絞って地域別の表を28行に潰した。`--partner` で切り替える。
   なお**二国間（国×国）の内訳は一括データに無い**。相手先は地域8区分まで
   （Africa / Americas / East Asia and the Pacific / Europe / Middle East / South Asia / Other / World）。
   「日本とアメリカの往来」のような国ペアは各国の統計（日本なら `jnto/inbound_outbound`）に当たる。

4. **1995年から。1990年は無い。** 1990年基準の指数を使う設問は再現できない。
   2017年追試Ｂ第2問問6（国際観光収入の1990年=100の指数）はこれで再現不能だった。

5. **単位は million US dollars。** `unit` 列で確認する。

6. **中国は `China`。香港・マカオ・台湾は別行**
   （`China, Hong Kong Special Administrative Region` 等）。FAOSTAT の China(351) のような
   集計値ではないので、そのまま使ってよい。

7. **世界計の行は無い。** シェアを出すなら国の合計を自分で取る。報告国が年で変わるので
   分母が動く点に注意。

8. **ダウンロードに User-Agent が要る。** `Python-urllib` のままだと Cloudflare に当たる。

## 出典表記

> UN Tourism（国連世界観光機関）の資料により作成。統計年次は◯◯年。

原問が「UNWTO」表記なら、2023年の改称を踏まえて「UN Tourism（旧UNWTO）」とするか、
原問に合わせるかを決めること。
