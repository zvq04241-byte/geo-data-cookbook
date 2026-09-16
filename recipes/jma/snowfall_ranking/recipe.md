---
id: jma/snowfall_ranking
api: jma
task: 主要都市 年降雪量／最深積雪 ランキング（気象庁 etrn スクレイプ）
tags: [jma, kishocho, snowfall, snow, climate, ranking, japan, city-level, html-scrape, no-auth]
summary: 気象庁 etrn(annually_s.php) を都市別にスクレイプし、指定寒候年の降雪量/最深積雪で都市ランキングを取得
items: [snowfall, maxsnow]
verified_at: 2026-06-08
complexity: medium
auth_required: false
gotcha_count: 8
pattern: html-scrape + dynamic-column-detection + per-city-cache
---

# jma / snowfall_ranking

## 何をする
気象庁 etrn の `annually_s.php` を主要都市ごとにスクレイプし、指定した**寒候年**の
年合計降雪量（または最深積雪）で都市をランキングして CSV + metadata.json に出力する。

## API情報
- **出典**: 気象庁 etrn 過去の気象データ（`annually_s.php`）
- **URL**: `https://www.data.jma.go.jp/stats/etrn/view/annually_s.php?prec_no=<>&block_no=<WMO>`
- **認証**: 不要（**User-Agent 必須**）
- **形式**: HTML テーブル（スクレイプ）/ 1都市=1リクエスト
- **単位**: cm（降雪量合計・最深積雪とも）

## 使い方
```bash
# 2024寒候年(2023年8月〜2024年7月)の年降雪量ランキング 上位15
python fetch.py --year 2024 --top-n 15 --output-dir ./output

# 最深積雪でランキング / 礼儀の待機を入れる
python fetch.py --year 2024 --metric maxsnow --sleep 0.3 --output-dir ./output
```
出力: `output/YYYYMMDD_jma_snowfall_snowfall_2024_top15.csv`（Rank,Area,CityKey,Value,Year,Metric,Unit）。
取得済み都市は `~/.cache/jma_snow/<city>.json` にキャッシュされ、再実行は無通信。

## ハマり所（重要）

### 1. 列位置は地点で揺れる → <th> を動的検出（最重要）
`annually_s.php` の列順は地点で微妙に異なる。**`<th>` ヘッダをキーワードで走査**して
「降雪量＋合計」「最深積雪」の列 index を特定する（`find_col`）。
検出失敗時のみ固定 index（降雪量合計=21／最深積雪=22）にフォールバック。固定 index 決め打ちは壊れる。

### 2. 「年」は暦年でなく寒候年
降雪量合計は**寒候年（前年8月〜当年7月）**集計。`--year 2024` は 2023年冬〜2024年春の雪。
暦年の降雪と混同しない。metadata と Year 列はこの寒候年。

### 3. 欠測トークンの正規化
セルには `--`（観測なし）/ `×`（資料不足）/ `///`（欠測）/ 空 が混じる。
これらは数値でなく **None** に正規化。さらにセル末尾の `rstrip(" ]")` でゴミ記号を除去する。

### 4. User-Agent 必須
`headers={"User-Agent": "Mozilla/5.0"}` を付けないとアクセスを弾かれる/異なる応答になる。

### 5. 無雪地点は自動除外される
那覇・石垣等の亜熱帯地点は降雪観測列が無く、全年 None。`val is None` で**ランキングから除外**。
東京・大阪も降雪ごく僅かで上位には出ない（reference で「上位に出ないこと」を検証）。

### 6. 1都市=1リクエスト → ランキングはN都市ループ
元データは単一都市の時系列。ランキングは複数都市をループ取得して指定年で揃える。
**キャッシュ（都市別 JSON）と `--sleep`** で JMA への負荷を抑える。smoke_test 再実行はキャッシュで無通信。

### 7. block_no / prec_no は地点固有ID
都市→(`block_no`=WMO, `prec_no`)の対応表が必要。本レシピは主要20都市の対応表を内蔵。
誤ID は 404/別地点になるので、追加時は etrn 画面で URL を確認する。

### 8. HTML構造変更で壊れうる
スクレイプは JMA のページ改修に弱い。動的列検出で頑健化しているが、**定期的に reference で再検証**する
（`verified_at` を更新）。列が全部ズレたら固定 index フォールバックが誤値を返す危険がある。

## 効くケース
- 主要都市（既定20・雪国中心）× 単一寒候年 × 降雪量/最深積雪 ランキング
- `--cities` で対象都市を指定、`--metric maxsnow` で最深積雪

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 1都市の長期時系列 | `jma/snowfall_timeseries` | 未作成 |
| AMeDAS 全観測点の面的分布 | `jma/amedas_*`（観測点が桁違い） | 未作成 |
| 平年値（1991-2020） | JMA AMeDAS normals 系レシピ | 未作成 |
| 月別・日別 | etrn の monthly/daily ページ | 未作成 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数・キャッシュは Path.home()/.cache）
- ✅ ファイルI/O は `encoding="utf-8"`、書き込みは `newline="\n"`
- ✅ 構造化例外 `DataFetchError`（source/url/kind）
- ✅ 都市ごと3回リトライ、失敗都市はスキップ（全体は継続）
- ✅ metadata.json に source URL / SHA256 / fetched_at / row_count / 寒候年
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）
- ✅ APIキー不要

## このレシピを使うLLMへのヒント
1. **スクレイプは列を決め打ちせず `<th>` から動的検出**。固定 index はフォールバックに留める
2. **欠測トークン（`--`/`×`/`///`）を必ず None 化**してから数値化する
3. **「年」の定義を疑う**（寒候年 vs 暦年）。気象データは集計期間の罠が多い
4. **複数地点ループは キャッシュ＋`--sleep`** で礼儀よく。reference は順位でなく不変条件で採点
5. **⚠データ源は HTML 表のスクレイプ。JSON API は存在しない**。`requests.get(url).json()` や
   `{年:{...}}` のネスト辞書を仮定すると必ず失敗する（`float()` に dict を渡す TypeError 等）。
   必ず fetch.py の HTML 解析（`<th>`/`<td>` を正規表現で抜き、`<th>` から列を動的検出）を踏襲する。
6. **出力CSVは 7列固定 `Rank,Area,CityKey,Value,Year,Metric,Unit`**。`Unit`(cm) 列を必ず付ける
   （validate が unit 項目で照合。列を落とすとデータが正しくても不合格）。
