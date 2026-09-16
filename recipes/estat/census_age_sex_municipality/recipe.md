---
id: estat/census_age_sex_municipality
api: estat
task: 国勢調査 男女・年齢（5歳階級）別人口 市区町村 ― 人口ピラミッド用
items: [年齢5歳階級別人口（男女別）]
tags: [estat, census, population-pyramid, age-sex, municipality, no-key-ui-but-appid]
summary: e-Stat API で国勢調査の市区町村別 年齢5歳階級×男女 人口を取得。人口ピラミッド作図用。新旧年で表構造が異なる罠あり
auth_required: true   # ESTAT_APP_ID（リポジトリ直下 .env）
verified_at: 2026-06-21
complexity: medium
gotcha_count: 4
---

# e-Stat / census_age_sex_municipality（国勢調査 年齢5歳階級×男女×市区町村）

## 何をする
市区町村単位の「男女・年齢（5歳階級）別人口」を取得し、**人口ピラミッド**（都心/郊外/外縁の型比較等）に使う。
2020(令和2) と 2015(平成27) の対比で「都心回帰・高齢化」等を可視化できる。

## API情報 / 使い方
- エンドポイント: `https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData`
- 認証: `appId`（`ESTAT_APP_ID`＝リポジトリ直下 `.env`。40桁）
- 取得: `cdArea`（市区町村コード,カンマ列）, `cdCat01/02/03`, `limit`, `metaGetFlg=Y`

## 表ID（statsDataId）と分類コード
| 年 | statsDataId | 男女(cat) | 年齢(cat) | 備考 |
|---|---|---|---|---|
| 2020 | `0003445162` | cat02（0総数/1男/2女） | cat03（01=0-4 … 18=85-89, 21=100+） | cat01=国籍（0総数） |
| 2015 | `0003149862` | **cat03**（0010男/0020女） | **cat02**（1180=0-4 … 1350=85-89） | cat01=全域(00710)/DID, cat04=国籍(0000), cat05=出生月(0000) |

## ハマり所（重要）
1. **★2015と2020で男女・年齢の cat 番号が入れ替わる**（2020: 男女=cat02/年齢=cat03、2015: 年齢=cat02/男女=cat03）。
   両年を同じコードで取ると空になる。年ごとに分類IDを確認（`metaGetFlg=Y` でCLASS_OBJを見る）。
2. **2015は全域/人口集中地区の区分(cat01)がある** → 全域 `00710` を指定しないとDIDと二重になる。さらに国籍・出生月も総数で絞る。
3. **市区町村コードは5桁・末尾000**（例 千代田区=13101, 多摩市=13224, 群馬県南牧村=10383）。同名異市（長野/群馬の南牧村）に注意。
4. **年齢コードに再掲（R1〜R6=15歳未満等）や不詳(22/1490)が混じる** → ピラミッドは 5歳階級の本系列のみ使う。

## 効くケース
- 人口ピラミッドの型比較（都心=生産年齢の山／郊外NT=50代の膨らみ／外縁=逆三角）。国勢調査の年次更新。

## 効かないケース（別レシピ）
- 小地域（町丁字）別の年齢3区分 → `niigata_chuo_age_population_p000`（小地域集計・第3表・比例パイ図）。

## 参照実装
- `kakomon_update_2020geoB_q3_p000`（2015/2020の3市区ピラミッド。inline fetch＋make_figures.py）。詳細 [[kakomon_data_update_pipeline]]。
