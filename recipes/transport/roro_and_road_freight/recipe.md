---
id: transport/roro_and_road_freight
api: uk_dft + eurostat
task: 国境を越える道路貨物を、ロールオン航路（随伴/無随伴の別）と道路貨物統計の両側から取る
items: [英国のロールオン貨物(相手国別), 随伴トラック/無随伴トレーラーの別, 国際道路貨物(積地国×揚地国), 車両国籍別]
tags: [transport, roro, ferry, road-freight, uk, dft, eurostat, brexit, modal-split, ods, no-auth]
summary: 英国はDfT PORT0205（航路別・随伴/無随伴の別あり）、EU側はEurostat road_go_ia_lgtt。貿易統計の「道路」がどの海峡を渡ったかを詰める
verified_at: 2026-10-26
complexity: medium
auth_required: false
gotcha_count: 10
pattern: govuk-ods-scrape + eurostat-jsonstat + accompanied-unaccompanied-split
---

# transport / roro_and_road_freight

## 何をする

貿易統計（`eurostat/trade_by_transport_mode`）で「道路輸送」と記録された貨物について、
**どの航路にどれだけのトラック・トレーラーが載っているか**を、航路側の統計で確かめる。
★貿易統計・港の統計・道路貨物統計は別々の調査で、**同じ貨物を追跡してはいない**。
重ねて言えるのは「量の釣り合い」までで、個々の貨物の経路は分からない。

| 側 | 出所 | 分かること |
|---|---|---|
| 英国 | DfT `PORT0205`（.ods） | 相手国別のロールオン貨物。**随伴トラックと無随伴トレーラーが別カテゴリ** |
| EU | Eurostat `road_go_ia_lgtt` | 車両国籍×揚地国の国際道路貨物（千トン）。2026-10-26 時点で2008〜2025年 |

## 英国 DfT PORT0205

`https://www.gov.uk/government/statistical-data-sets/port-and-domestic-waterborne-freight-statistics-port`
から `port0205.ods`（約5.8MB）。**URLはメディアIDつきで更新のたび変わる**のでページから拾う。

- シート `Data`、**`skiprows=3`**（上に説明行が3行）
- 列: `Year / Port of Load Unload Region / Port of Load Unload Country / Cargo Code /
  Cargo Name / Cargo Group Code / Cargo Group Name / Direction / Tonnage (thousands) /
  Units (thousands) / TEU (thousands)`
- `Cargo Group Name` = All Cargo / Liquid Bulk / Dry Bulk / Lo-Lo / **Ro-Ro** /
  Other General Cargo / Main Freight
- Ro-Ro の `Cargo Name` は6区分。うち道路貨物は次の2つ
  - `Road goods vehicles with or without accompanying trailers` … **随伴トラック**
  - `Unaccompanied road goods trailers & semi-trailers` … **無随伴トレーラー**

## 検証済み ― ポルトガルの対英「道路」輸送と航路の量

Comext で 2025年のポルトガル→英国輸出は**額の45.3%が道路**（`references/comext_pt_gb_2025.csv`）。

**英国のロールオン随伴トラック（千トン・往復計。`references/20261026_uk_roro.csv`）**

| 相手国 | 2016 | 2019 | 2021 | 2023 | 2025 |
|---|---:|---:|---:|---:|---:|
| **フランス** | 28,841 | 24,623 | 20,284 | 19,661 | **19,511** |
| アイルランド | 5,776 | 5,814 | 3,353 | 3,793 | 2,773 |
| オランダ | 3,890 | 3,707 | 3,339 | 3,376 | 3,632 |
| **スペイン** | 256 | 248 | 103 | 96 | **109** |
| ポルトガル | 1.1 | 1.6 | ― | ― | ―（行が無い） |

**車両国籍別の英国揚げ（Eurostat `road_go_ia_lgtt`、千トン。`references/20261026_eu_road.csv`）**

| 車両国籍 | 2016 | 2019 | 2021 | 2023 | 2025 |
|---|---:|---:|---:|---:|---:|
| ポルトガル | 329 | 212 | 175 | 185 | 72 |
| スペイン | 1,930 | 2,020 | 1,998 | 1,802 | 1,658 |

このデータで言えること:
- 2025年の随伴トラックは、フランス航路（19,511千t）がスペイン航路（109.5千t）の約178倍。
- ポルトガル–英国のロールオン道路貨物は、2016・2019年にわずか（1千t台）にあり、2021年以降は行が無い。
- 2025年のスペイン籍トラックの英国揚げ（1,658千t）は、スペイン航路のロールオン道路貨物全体（随伴109.5＋無随伴416.4＝525.8千t、全国籍）より大きい。
- ポルトガル籍トラックの英国揚げ（2025年 72千t）は、スペイン航路の随伴トラック（109千t）より小さい。**ポルトガル籍の量だけでは経路は絞れない。**

言えないこと: ポルトガルの貨物のうち何割がどの航路・ユーロトンネルを通ったか。
この表はユーロトンネルを含まず（ハマり所2）、道路貨物統計は車両の国籍で数える（ハマり所7）ので、
ポルトガルの貨物をスペイン籍・他国籍の車両が運んだ分はポルトガルの行に入らない。

## 随伴か無随伴か ― 航路で割合が大きく違う

2025年・千トン（`references/20261026_uk_roro.csv`）

| 相手国 | 随伴トラック | 無随伴トレーラー | 無随伴の割合 |
|---|---:|---:|---:|
| フランス | 19,511 | 944 | 4.6% |
| ベルギー | 1,892 | 3,614 | 65.6% |
| アイルランド | 2,773 | 5,835 | 67.8% |
| オランダ | 3,632 | 11,862 | 76.6% |
| スペイン | 109 | 416 | 79.2% |
| デンマーク | 42 | 1,418 | 97.1% |
| スウェーデン | 22 | 1,735 | 98.7% |

**随伴に偏るのはフランス航路だけ**で、ほかは無随伴が6割を超える。
航路の距離・所要時間との関係は測っていない（アイルランド航路のように近くても無随伴が多い例がある）。
なお Comext では 2025年のフランス→英国輸出の額の56.1%が道路、3.3%が鉄道（`references/comext_pt_gb_2025.csv`）。
Comext の「道路」が随伴・無随伴のどちらにあたるかは、この2つの統計からは決められない。

## 荷の側 ― 単価を見る

Comext の HS6 と単価（額÷重量）で、道路で運ばれている荷を見る（`references/measure_comext_pt_gb.py`）。
ポルトガル→英国・道路輸送の額の上位は**衣料ではなく計器と自動車電装**だった。

| HS6 | 品目 | 額(百万EUR) | 単価(EUR/kg) |
|---|---|---:|---:|
| 902920 | 速度計・回転計 | 65.2 | **155.5** |
| 852990 | 送受信機器の部分品 | 57.6 | **354.8** |
| 610910 | Tシャツ(ニット) | 40.2 | 47.4 |
| 640399 | 革靴 | 36.6 | 46.3 |
| 854430 | 自動車用点火配線セット | 35.5 | 53.0 |

単価と道路の関係を測ると（2025年ポルトガル→英国、額100万EUR以上の HS6 365品目）、
単価と道路比率の順位相関は **0.35**。単価の四分位ごとの道路の割合（額加重）は
低い順に **18.5% / 54.8% / 35.6% / 77.5%**。最も単価の高い4分の1で道路が多いが、きれいな右上がりではない。
理由（在庫・輸送日数の費用など）はこのデータでは確かめていない。

Tシャツ（HS 610910）の英国向け輸出の単価（全手段）は、ポルトガル 49.0 EUR/kg、イタリア 107.5 EUR/kg。

★HS2桁の「道路比率」（2025年ポルトガル→英国、額ベース）で見ると履物（64類）93.3%・ニット（61類）91.4%が目立つが、**金額で見ると順位が違う**。
比率と金額のどちらを見ているかを取り違えない。

## Eurostat `road_go_ia_lgtt`

次元は `freq . tra_type . c_unload . nst07 . unit . geo . time`。
`geo` は**車両の国籍**（報告国）、`c_unload` が揚地国。`unit=THS_T`、`tra_type=TOTAL`、`nst07=TOTAL`。

## 使い方

```bash
python fetch.py --uk-roro --year 2025
python fetch.py --uk-roro --years 2016,2019,2021,2023,2025 --countries France,Spain,Netherlands
python fetch.py --eu-road --geo PT,ES,FR --unload UK
```

## ハマり所

1. **`PORT0302` と `PORT0205` を取り違えやすい。** gov.uk の一覧でリンクが並んでおり、
   ファイル名 `port0302.ods` を落としたつもりで中身が PORT0205 のことがある。
   **`Data` シートの1行目（`Data sheet for PORT0205`）で表番号を確かめる。** Cover の表題には番号が無い。
   `fetch.py` は番号が違えば止まる。
   （PORT0205＝航路別、PORT0302＝港別×航路別で6.6MB）
2. **これは「港」の統計。ユーロトンネルは入っていない。**
   海峡トンネルのシャトルで運ばれるトラックはこの表に入らないので、英仏間の道路貨物の全体はこの数字より大きい。
3. **随伴と無随伴を足さないと道路貨物の全体にならない。** 逆に分けると航路の性格が見える。
   片方だけ見ると、オランダ航路（2025年は無随伴が随伴の3.3倍）を過小評価する。
4. **相手国名が独特。** `Irish Republic`（Ireland ではない）、`Cote Divoire`、
   `All European Union - Small Flows` のような集計行も同じ列に混じる。`fetch.py` は除き、
   除いた行の重量を metadata の `excluded_aggregate_rows_thousand_t` に残す（国別の行の和はその分だけ全体より小さい）。
5. **`.ods` は `odfpy` が要る**（`pip install odfpy`、`pandas.read_excel(engine="odf")`）。
6. **`Data` シートは `skiprows=3`。** そのまま読むと列名が `Unnamed: 1` になる。
7. **Eurostat `road_go_ia_tc`（積地国×揚地国）は2013年止まり。**
   現行は `road_go_ia_lgtt` だが、こちらは **`geo` が車両の国籍**。
   ポルトガルの貨物をスペイン籍・ポーランド籍のトラックが運べば計上されない。
   **「ポルトガルからの陸送量」ではなく「ポルトガル籍が運んだ量」。**
8. **比率と金額を取り違えない。** HS2桁で「その品目の何%が道路か」を見ると履物・衣類が
   上位に来るが、**金額**で見ると計器・自動車電装が上。どちらを見ているかで結論が変わる。
9. **`Direction` に `Both Directions` がある。** 輸出だけ見たいときに足すと倍になる。
   `fetch.py` は Both Directions（往復計）だけを使う。範囲は metadata の `scope` に出る。
10. **`--eu-road` の既定は車両国籍 PT,ES,FR の3か国。** 全国籍ではない。`scope` に国と年の範囲が出る。
   取れなかった国籍があれば止まる。
