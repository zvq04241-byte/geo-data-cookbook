---
id: estat/keizai_census_industry
api: estat
task: 経済センサス活動調査 産業（中分類）別 民営事業所数 都道府県別
items: [産業中分類別 事業所数]
tags: [estat, keizai-census, establishments, industry, prefecture, choropleth]
summary: e-Stat API で経済センサス活動調査の産業中分類別 事業所数を都道府県別に取得。業種の地理的分布（階級区分図）用
auth_required: true   # ESTAT_APP_ID（.env）
verified_at: 2026-06-21
complexity: easy
gotcha_count: 3
---

# e-Stat / keizai_census_industry（経済センサス 産業中分類別 事業所数 都道府県）

## 何をする
産業（中分類）別の民営事業所数を都道府県別に取得し、**業種の地理的集中**（情報サービス＝東京突出／道路貨物＝太平洋ベルト／農業＝農業県）を
階級区分図・シェア図にする。年次対比で構造の安定／変化を見る。

## API情報 / 使い方
- `getStatsData`、`appId`（`ESTAT_APP_ID`）、`cdCat01`（産業中分類,カンマ列）, `cdTab`（事業所数）, `cdCat02`（総数）, `limit`。
- 都道府県は area 5桁・末尾000（01000北海道〜47000沖縄、00000=全国は除外）。

## 表ID と 産業中分類コード（cat01）
| 年 | statsDataId |
|---|---|
| 2024（令和6 活動調査） | `0004040099` |
| 2021（令和3 活動調査） | `0004005665` |

主な中分類コード: `39`情報サービス業 / `44`道路貨物運送業 / `01`農業 / `G`情報通信業(大分類)。

## ハマり所
1. **「農業関連サービス業」は産業中分類では分離不可**（農業サービス業は細分類013）。代理に中分類 `01`農業を使うか、細分類取得の別表が要る。
2. **tab（表章事項）に事業所数以外（従業者数等）が混在** → `metaGetFlg=Y` で「事業所数」コードを特定して `cdTab` 指定。
3. **cat02（単独・本所・支所）は「総数」で絞る**（支所重複を避ける）。

## 効くケース
- 業種の都道府県分布（階級区分図・シェア棒）。経済センサスの年次更新。構造が安定なら「更新不要」判定の好例。

## 参照実装
- `kakomon_update_2020geoB_q2_p000`（問6 サービス業3業種・2021/2024）。詳細 [[kakomon_data_update_pipeline]]。
