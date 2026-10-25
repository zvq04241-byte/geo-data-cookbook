---
id: unido/industry_output
api: unido
task: 業種別の工業生産額（Output）・付加価値を国別に取得
items: [Output, Value added]
tags: [unido, indstat, industry, manufacturing, isic, sdmx, rest-api, no-auth, cloudflare]
summary: UNIDO INDSTAT（Rev.3/Rev.4）から ISIC 分類別の産出額を SDMX API で取得。4か国以上は3か国ずつ取って結合し、範囲を metadata の scope に書く
verified_at: 2026-10-26
complexity: medium
auth_required: false
gotcha_count: 8
---

# unido / industry_output

## 何をする
UNIDO の INDSTAT から、国 × 指標 × ISIC 分類 × 年 の工業統計を取る。
工業生産額（産出額 output）を検算するときは、World Bank（付加価値）ではなく UNIDO を一次に取る。
『世界国勢図会』の工業生産額とは、ある1か国1年の6区分（下の表）で値が一致した（手元のプロジェクトの照合記録）。
誌面の出典表記と、ほかの国・年での一致は、このレシピでは確かめていない。

## API情報
- ポータル: https://stat.unido.org/
- **実際に叩くのは `https://stat.unido.org/portal/`**（後述）
- 仕様書: `/portal/v3/api-docs/api` と `/portal/v3/api-docs/sdmx`（OpenAPI JSON）
- 認証: 不要（2022年2月以降、全データベースが無料・登録不要）
- 主なデータベース: INDSTAT_R3 / INDSTAT_R4 / IDSB_R3 / IDSB_R4 / NADB / MTD / MMTD / IIP / SDG / CIP

## 使い方
```bash
python fetch.py --list-flows                                       # データベース一覧
python fetch.py --countries 682,050,704 --rev 3 --start 2015 --end 2023
python fetch.py --countries 036 --rev 4 --indicator 20             # 付加価値
```

## ハマり所（重要）

### 1. サイト直下は Cloudflare で 403。`/portal/` 配下だけが通る（最重要）
`https://stat.unido.org/`・`/data/download`・`/rest/...` はいずれも Cloudflare の
managed challenge に当たって 403（本文は "Just a moment..."）。
**`/portal/` 以下の `/portal/sdmx/dataflow`・`/portal/sdmx/data`・`/portal/sdmx/datastructure`・`/portal/v3/api-docs/*` は通った**（2026-08-29、2026-10-26 にも sdmx は通った）。2026-08-18 に「403で取得できず、API仕様も不明」と
記録して諦めたが、原因はこれだった（2026-08-29 に解決）。

### 2. urllib 既定の User-Agent は弾かれる
`Python-urllib/3.x` は Cloudflare の **Error 1010（browser signature banned）**。
`curl/8.x` は通る。ブラウザの UA を明示して送ること。

### 3. Accept ヘッダが必須。間違えると 400
ワイルドカードや `application/json` は `Invalid Accept Header` / `Wildcard Accept not allowed`。
呼び分けが要る。

| エンドポイント | Accept |
|---|---|
| `/sdmx/dataflow/...` | `application/vnd.sdmx.dataflow+json;version=2.0.0` |
| `/sdmx/datastructure/...` | `application/vnd.sdmx.structure+json;version=2.0.0` |
| `/sdmx/data/...` | `application/vnd.sdmx.data+json;version=2.0.0` |

### 4. キーは4段。空の段は不可
`countries.indicators.classification.classification_combination`。
`682.14..` のように空けると `Invalid dimension key format. Remove leading, trailing,
or consecutive dots`。**全件は `*`** で書く（`682.14.*.*`）。

### 5. 国は1回あたり3か国まで → fetch.py が3か国ずつに分けて取る
4か国以上は 400（応答「Due to response size, up to three countries can be requested」。2026-10-26 確認）。
fetch.py は3か国ずつ取って結合し、metadata に `countries_requested`・`countries_with_data`・`countries_without_data`・`years_present`・`scope` を書く。
値の無い国は落ちても名前が残る。国コードは **ISO 3166 数字3桁**（682=サウジアラビア、
050=バングラデシュ、704=ベトナム、036=オーストラリア）。

### 6. 値は自国通貨。ドルではない
INDSTAT の値は national currency。教材の「億ドル」に直すには自分で換算する。
為替は World Bank `PA.NUS.FCRF`（公式為替・期中平均）を使う。保管庫の WDI から引ける。

### 7. Rev.3 と Rev.4 で収録国・年がまるで違う
2026-10-26 の実測（Output=14、要求 2015–2023。記録 `references/20261026_checks.md`）:

| 国 | Rev.4 | Rev.3 |
|---|---|---|
| サウジアラビア | 2015-2023 | 2015-2023 |
| バングラデシュ | **2015, 2018** | 2018, 2020 |
| ベトナム | **製造業なし**（2020-2022、ISIC 05–09・35–39 のみ） | 2015-2022 全分類 |

収録は更新で変わる（2026-08-29 の実測では Rev.4 のサウジは2018年から、バングラデシュは2018年のみだった）。
上の1か国1年の一致は Rev.3 の束ね方で取ったもの。Rev.4 だけ見て「データがない」と判断しない。

### 8. Output と Value added を混同しない
- `14` Output（産出額）＝中間消費を**含む**。そのため GDP を上回ることがある（下の実例）
- `20` Value added（付加価値）＝output − 中間投入。World Bank `NV.IND.MANF.CD` はこちら

実例: ベトナムの工業生産額 4,813億ドル > 同国のGDP 4,134億ドル（2022年。INDSTAT_R3・indicator 14・ISIC D を、保管庫 WDI の PA.NUS.FCRF 2022 で換算。GDP は WDI NY.GDP.MKTP.CD。記録 `references/20261026_checks.md`）。
**定義どおりで異常ではない。** World Bank の付加価値（1,019億ドル）と比べて
「大きすぎる」と誤認しかけた（2026-08-18）。

## 『世界国勢図会』の6区分の中身（2026-08-29）
ある1か国1年で、6項目すべてが誌面値と一致した ISIC Rev.3 の束ね方。ほかの国・年では確かめていない。

| 誌面の区分 | ISIC Rev.3 |
|---|---|
| 食料品 | 15 食料品・飲料 + 16 たばこ |
| 繊維 | 17 繊維 + 18 衣服 |
| **石油製品・化学** | **23 コークス・石油製品 + 24 化学** |
| 金属 | 27 第1次金属 + 28 金属製品 |
| 機械 | 29 一般機械 + 30 事務用 + 31 電気 + 34 自動車 + 35 その他輸送 |
| その他 | 残り（19皮革・20木材・21紙・22印刷・25ゴム/プラ・26窯業・32,33・36家具ほか） |

※「石油製品・化学」は 23+24 の直訳。**「化学製品」ではない**（「化学製品」は貿易統計＝
SITC 5類の呼び名で、工業の業種名ではない）。

## 効くケース
- 「業種別工業生産額」の図表の検算
- 国際比較（産業構造の違いを見せる図）
- indicator は応答に 01・04・05・14・20・31 が現れる。14=Output・20=Value added 以外の名前はこのレシピでは確かめていない（codelist を取れなかった）。使う前に UNIDO の定義で確かめる

## 効かないケース
| 要求 | 推奨 |
|---|---|
| 製造業付加価値の国際比較（GDP比など） | World Bank `NV.IND.MANF.*` |
| 工業製品の貿易 | UNIDO MTD、または `comtrade/trade_ranking` |
| 日本国内の業種別出荷額 | `estat/manufacturing_shipment_prefecture` |

## 関連
- `_workspace/docs/api_notes/unido.md`
- 手元のプロジェクト `sougou4_p000` の照合スクリプト（この API を使った実際の検算）
