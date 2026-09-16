---
id: transport/roro_and_road_freight
api: uk_dft + eurostat
task: 国境を越える道路貨物を、ロールオン航路（随伴/無随伴の別）と道路貨物統計の両側から取る
items: [英国のロールオン貨物(相手国別), 随伴トラック/無随伴トレーラーの別, 国際道路貨物(積地国×揚地国), 車両国籍別]
tags: [transport, roro, ferry, road-freight, uk, dft, eurostat, brexit, modal-split, ods, no-auth]
summary: 英国はDfT PORT0205（航路別・随伴/無随伴の別あり）、EU側はEurostat road_go_ia_lgtt。貿易統計の「道路」がどの海峡を渡ったかを詰める
verified_at: 2026-09-15
complexity: medium
auth_required: false
gotcha_count: 9
pattern: govuk-ods-scrape + eurostat-jsonstat + accompanied-unaccompanied-split
---

# transport / roro_and_road_freight

## 何をする

貿易統計（`eurostat/trade_by_transport_mode`）で「道路輸送」と記録された貨物が、
**実際にどの経路で海を渡ったか**を詰める。橋のない相手国に「道路」で輸出されているとき、
トラックがフェリーに載ったのか、トレーラーだけ載ったのか、どの航路かを切り分ける。

| 側 | 出所 | 分かること |
|---|---|---|
| 英国 | DfT `PORT0205`（.ods） | 相手国別のロールオン貨物。**随伴トラックと無随伴トレーラーが別カテゴリ** |
| EU | Eurostat `road_go_ia_lgtt` | 車両国籍×揚地国の国際道路貨物（千トン）、2024年まで |

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

## 検証済み ― ポルトガルの対英「道路」輸送はどこを通るか

Comext で 2025年のポルトガル→英国輸出は**道路45.3%**。直行フェリーなのか陸路縦断なのか。

**英国のロールオン随伴トラック（千トン・往復計）**

| 相手国 | 2016 | 2019 | 2021 | 2023 | 2025 |
|---|---:|---:|---:|---:|---:|
| **フランス** | 28,841 | 24,623 | 20,284 | 19,661 | **19,511** |
| アイルランド | 5,776 | 5,814 | 3,353 | 3,793 | 2,773 |
| オランダ | 3,890 | 3,707 | 3,339 | 3,376 | 3,632 |
| **スペイン** | 256 | 248 | 103 | 96 | **109** |
| ポルトガル | ― | ― | ― | ― | ―（航路なし） |

**フランス経由がスペイン経由の178倍。** さらに Eurostat でポルトガル籍トラックの英国揚げは
年7〜21万トンあり、スペイン航路の随伴トラック109千トン（全国籍）には収まらない。
→ **ほぼ全量がスペイン・フランスを縦断してカレー／ダンケルクかユーロトンネル。**

## 随伴か無随伴かで航路の性格が分かる

2025年・千トン

| 相手国 | 随伴トラック | 無随伴トレーラー |
|---|---:|---:|
| フランス | 19,511 | 944 |
| オランダ | 3,632 | 11,862 |
| スウェーデン | 22 | 1,735 |

**短い海峡は運転手ごと、長い北海航路はトレーラーだけ。** Comext が「道路」と記録するのは
前者にあたる。これでフランス→英国が貿易統計で道路56.1%・鉄道3.3%になる理由が説明できる。

## 荷の側からの裏づけ ― 単価を見る

「なぜ随伴トラックなのか」は、Comext の HS6 と単価（額÷重量）で確かめられる。
ポルトガル→英国・道路輸送の上位は**衣料ではなく計器と自動車電装**だった。

| HS6 | 品目 | 額(百万EUR) | 単価(EUR/kg) |
|---|---|---:|---:|
| 902920 | 速度計・回転計 | 65.2 | **155.5** |
| 852990 | 送受信機器の部分品 | 57.6 | **354.8** |
| 610910 | Tシャツ(ニット) | 40.2 | 47.4 |
| 640399 | 革靴 | 36.6 | 46.3 |
| 854430 | 自動車用点火配線セット | 35.5 | 53.0 |

**単価が高い荷ほど陸送が引き合う。** 在庫と輸送日数の費用が効くため。
衣料も、ポルトガルはバングラ(13.6)・中国(20.4)の2〜3.6倍の単価で、量販帯ではない。

| Tシャツ EUR/kg | ポルトガル 49.0 | イタリア 107.5 | バングラ 13.6 | 中国 20.4 | トルコ 26.7 |
|---|---|---|---|---|---|

★HS2桁の「道路比率」で見ると履物93.3%・ニット91.4%が目立つが、**金額で見ると順位が違う**。
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
   **Cover シートの1行目で表番号を必ず確かめる。**
   （PORT0205＝航路別、PORT0302＝港別×航路別で6.6MB）
2. **これは「港」の統計。ユーロトンネルは入っていない。**
   英仏間の実際の陸送はこの数字より大きい。海峡トンネルのシャトル貨物は別系統。
3. **随伴と無随伴を足さないと道路貨物の全体にならない。** 逆に分けると航路の性格が見える。
   片方だけ見ると、オランダ航路（無随伴が3倍）を過小評価する。
4. **相手国名が独特。** `Irish Republic`（Ireland ではない）、`Cote Divoire`、
   `All European Union - Small Flows` のような集計行も同じ列に混じる。
5. **`.ods` は `odfpy` が要る**（`pip install odfpy`、`pandas.read_excel(engine="odf")`）。
6. **`Data` シートは `skiprows=3`。** そのまま読むと列名が `Unnamed: 1` になる。
7. **Eurostat `road_go_ia_tc`（積地国×揚地国）は2013年止まり。**
   現行は `road_go_ia_lgtt` だが、こちらは **`geo` が車両の国籍**。
   ポルトガルの貨物をスペイン籍・ポーランド籍のトラックが運べば計上されない。
   **「ポルトガルからの陸送量」ではなく「ポルトガル籍が運んだ量」。**
8. **比率と金額を取り違えない。** HS2桁で「その品目の何%が道路か」を見ると履物・衣類が
   上位に来るが、**金額**で見ると計器・自動車電装が上。どちらを見ているかで結論が変わる。
9. **`Direction` に `Both Directions` がある。** 輸出だけ見たいときに足すと倍になる。
