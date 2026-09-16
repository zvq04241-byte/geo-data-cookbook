---
id: aviation/airport_passengers
api: eurostat + bts + estat + miaa + caap
task: 空港別の旅客数（国内線／国際線）・空港間の旅客流動を取得
items: [空港別旅客数, 国内線・国際線の別, EU域内/域外の別, 貨物, 空港間の旅客流動（日本）]
tags: [aviation, airport, passengers, eurostat, bts, estat, miaa, caap, avia_paoa, air-traffic]
summary: 空港別統計は国ごとに別系統しかない。欧州=Eurostat avia_paoa、米国=BTS T-100、日本=e-Stat（国内線は航空輸送統計・国際線は出入国管理統計）、比=MIAA/CAAP
verified_at: 2026-09-15
complexity: medium
auth_required: true   # e-Stat 側のみ ESTAT_APP_ID
gotcha_count: 11
---

# aviation / airport_passengers

## 何をする

空港別の旅客数を取る。共通テストで繰り返し出る型（「いくつかの都市の空港における
国内線と国際線の旅客数」「EU圏内の空港から出発した旅客数と貨物量」）に対応する。

**★世界を一括で取れる無料のデータは無い。** ACI・OAG・ICAO はいずれも有料。
国・地域ごとの公的統計を組み合わせるしかない。本レシピは**欧州・米国・日本・フィリピン**を押さえる。

| 地域 | 出所 | 国内/国際の別 | 状態 |
|---|---|---|---|
| 欧州（EU＋EFTA＋候補国） | Eurostat `avia_paoa`（空港別）/ `avia_par`（空港ペア） | ○ `tra_cov` | ○ 無認証 |
| アメリカ | BTS T-100 Segment Summary By Origin Airport（Socrata `r495-tyji`） | △ 国際は「総−国内」 | ○ 無認証・2014年〜 |
| 日本（国内線） | e-Stat 航空輸送統計調査 第9表「国内定期航空空港間旅客流動表」 | ─ 国内のみ | ○ 要 `ESTAT_APP_ID` |
| 日本（国際線） | e-Stat 出入国管理統計「港別 出入国者」`0003449063` | ─ 国際のみ | ○ ただし**旅客数ではなく出入国者数** |
| フィリピン（マニラ） | MIAA Operational Statistics（PDF） | ○ 到着/出発×国際/国内 | ○ 2018年〜 |
| フィリピン（地方） | CAAP `AirpasscarANNUAL-{year}.xls` | △ 空港名の接尾辞 | ○ 2018年〜。**NAIA・Mactanは0** |
| 韓国・その他アジア | 各国の空港公社 | | ✗ 個別

## 使い方

```bash
python fetch.py --eu CDG,FRA,MAD --year 2024      # 欧州の空港別
python fetch.py --eu CDG --year 2024 --detail     # EU域内/域外の内訳まで
python fetch.py --eu AMS --year 2024 --departures # 出発便のみ（米BTSと並べるとき）
python fetch.py --us ATL,JFK,LAX --year 2024      # 米国
python fetch.py --jp --year 2023                  # 日本の国内線 空港間流動
python fetch.py --jp-intl --year 2024             # 日本の国際線（出入国者）
python fetch.py --ph --year 2024                  # フィリピン（NAIA＋地方45空港）
python fetch.py --list-eu-airports FR             # 空港コードを探す
```

## Eurostat `avia_paoa` の次元

```
freq . unit . tra_meas . rep_airp . schedule . tra_cov . time
```

- `rep_airp` … **報告空港**。`FR_LFPG`（パリCDG）のように「国コード_ICAO」
  ★`geo` ではない。`geo=FR` を渡すと `INVALID_QUERY_DIMENSION: Dimension "GEO" is not defined`
- `tra_meas=PAS_CRD` 旅客（到着＋出発）/ **`PAS_CRD_DEP` 出発のみ**・`PAS_CRD_ARR` 到着のみ /
  `FRM_LD_NLD` 貨物（`avia_gor`）
- `tra_cov` … **`NAT`＝国内線 / `INTL`＝国際線**。さらに `INTL_EU27_2020`（域内）と
  `INTL_XEU27_2020`（域外）に分かれる。原問の「国内線と国際線」はここで取れる
- `schedule` … `TOTAL` / `SCHED`（定期）/ `NSCHED`（不定期）

検証済み（パリCDG 2024年・旅客数）:

| | |
|---|---|
| Total | 70,257,116 |
| 国内線 NAT | 7,177,779 |
| 国際線 INTL | 63,079,337 |
| うちEU域内 | 21,707,525 |
| うちEU域外 | 41,371,812 |

検証済み（アムステルダム 2024年・旅客数）: Total 66,824,331／国内線 **1,273**／国際線 66,823,058。
乗り継ぎ拠点の空港は国内線がほぼ0になる。

## アメリカ BTS

Socrata。`https://data.bts.gov/resource/r495-tyji.json`

- `origin_airport_code`（ATL・JFK…）、`year`、`total_passengers`、`domestic_passengers`
- **国際線の列は無い。`total − domestic` で出す**
- 2014年〜。月次レコードなので年で `sum()` して集計する

```
$select=sum(total_passengers) as tot, sum(domestic_passengers) as dom
$where=origin_airport_code='ATL' AND year='2024'
```

検証済み（2024年・出発旅客）: ATL 総 52,616,638／国内 45,479,185／国際 7,137,453（国際13.6%）

## e-Stat 航空輸送統計調査（日本の国内線）

- 第9表（年度次）`statsDataId=0003173927` … **発空港×着空港 92×92** の旅客流動。2006〜2023年度
- 第10表 … 貨物流動
- 分類は `cat01`＝着空港、`cat02`＝発空港。どちらにも `1000 合計` がある
- 空港名は「羽田」「成田」。**「東京国際」ではない**

## e-Stat 出入国管理統計（日本の国際線）

`statsDataId=0003449063`「総括 港別 出入国者」月次。`cat03`＝港（180件、空港は名前に「（空港）」）、
`cat02`＝1010 入国者／1020 出国者／1000 総数、`cat01`＝1000 計／日本人／外国人。

検証済み（2024年・出国者）: 成田 14,750,713／羽田 10,570,358／関西 11,8xx,xxx 台

## フィリピン

**NAIA（マニラ）と地方空港で出所が違う。**

- **MIAA**（NAIA運営者）… `https://www.miaa.gov.ph/index.php/reports/operational-statistics` の
  `*_Total_Statistics.pdf`。**ファイル名に更新日が入る**ので、ページから拾う。
  到着/出発 × 国際/国内 × 旅客・便数、2018年〜、月別＋年計。`pdftotext -layout` で読める
- **CAAP**（地方空港運営者）… `AirpasscarANNUAL-{year}.xls`（2018〜2025）。
  シート `passenger`、A列＝空港・B列＝航空会社・O列＝年計

検証済み（NAIA 2024年）: 国際線 23,365,779（到着 11,491,737＋出発 11,874,042）／
国内線 26,990,686（到着 13,540,635＋出発 13,450,051）

## 4都市を並べた例（2016年追試Ｂ第3問の型）

母数を揃えるため**すべて出発便のみ**にする。

| 都市 | 国内線 | 国際線 | 国際線比 | 出所 |
|---|---:|---:|---:|---|
| アトランタ | 45,479,185 | 7,137,453 | 13.6% | BTS 2024 |
| アムステルダム | 103 | 33,318,367 | 100.0% | Eurostat 2024 |
| 東京（羽田＋成田） | 34,105,636 | 25,321,071 | 42.6% | e-Stat 2023年度／出入国2024 |
| マニラ | 13,450,051 | 11,874,042 | 46.9% | MIAA 2024 |

**★東京とマニラの国内:国際の比が 42.6% と 46.9% でほぼ並ぶ。**
100%積み上げの図にすると識別できない。実数の図なら規模差（5,943万 対 2,532万）で分かれる。

## ハマり所

1. **Eurostat の空港次元は `rep_airp`。`geo` ではない。**
   `geo=FR` で 400。`INVALID_QUERY_DIMENSION` が返る。
2. **`tra_cov` を指定しないと5種類の行が同時に返る**（Total／NAT／INTL／域内／域外）。
   合計すると二重計上。必要な区分だけ取るか、後で分ける。
3. **一つの都市に複数の空港がある。** 原問は「東京＝成田＋羽田の合算」「パリ＝CDG＋オルリー」と
   注記している。**空港単位のデータを都市単位に足す処理が要る。**
4. **e-Stat 第9表は国内線のみ。** 国際線旅客は含まれない。日本の国際線は
   国交省「空港管理状況調書」（e-Stat未収録・PDF/Excel）に当たる。
5. **「就航都市数」は旅客数とは別のデータ。** 航空時刻表（OAG）由来で、
   2026-09-15 時点で無料の全球データが見つからない。
   2020年本試Ａ第4問（国際線・国内線の就航都市数）はこの経路では作れない。
6. **★前版の「BTSのAPIは落ちている」は誤りだった。** 2026-09-15 に
   `transtats.bts.gov/api/`＝404、`bts.gov`＝403 を見て「API が死んでいる」と書いたが、
   **404 は当てずっぽうのデータセットIDを叩いたせい**で、`data.bts.gov` の Socrata は
   生きている。`https://data.bts.gov/api/views.json?limit=400` で一覧が引ける。
   **エラーコードだけで「無い」と決めない。まず一覧を引く。**
7. **BTSの「AFF - Passengers By Airport」(`tqbz-sck3`) は空の殻。**
   HTTP 200 で `[]` が返る。これは**グラフ表示用のビュー**で、実データは
   `metadata.modifyingViewUid` が指す `r495-tyji` のほう。
   200＋空配列を「データが無い」と読むと経路を落とす。
8. **BTSには国際線の列が無い。** `total_passengers` と `domestic_passengers` だけ。
   国際線は引き算で出す。さらに**出発空港基準なので出発便のみ**。
   到着＋出発の Eurostat と直接並べると米国だけ半分になる。
   並べるときは Eurostat 側を `PAS_CRD_DEP` にする。
9. **日本の国際線と国内線は出所も定義も年もずれる。**
   国内線＝航空輸送統計（航空旅客・年度・2023年度まで）、
   国際線＝出入国管理統計（**出入国者数**・暦年）。
   出入国者数は乗り継ぎだけの客を含まず、船の港も同じ表にある。
   「東京の国内線と国際線」を1枚の図にするなら、この差を注記する。
10. **CAAP の xls には NAIA と Mactan の行があるのに数字は全部0。**
   NAIA は MIAA、Mactan は MCIAA が別に運営していて CAAP に報告が上がらない。
   **行が在ることを「データが在る」と読むと、マニラを0人として図にしてしまう。**
   A列には地方名（Region I・CAR・NCR）と `Total` 行も混じるので、空港名と区別する。
11. **MIAA の PDF はファイル名に更新日が入る**（`20260708_Total_Statistics.pdf`）。
   URL を決め打ちにすると次の更新で404。一覧ページから `*_Total_Statistics.pdf` を拾う。
