---
id: jma/snowfall_ranking
api: jma
task: 内蔵20都市 年降雪量／最深積雪 ランキング（気象庁 etrn スクレイプ・全国順位ではない）
tags: [jma, kishocho, snowfall, snow, climate, ranking, japan, city-level, html-scrape, no-auth]
summary: 気象庁 etrn(annually_s.php) を内蔵20都市についてスクレイプし、指定寒候年の降雪量/最深積雪で20都市の中の順位を付ける（範囲は出力の Scope 列・metadata の scope に書く）
items: [snowfall, maxsnow]
verified_at: 2026-10-26
complexity: medium
auth_required: false
gotcha_count: 8
pattern: html-scrape + dynamic-column-detection + per-city-cache
---

# jma / snowfall_ranking

## 何をする
気象庁 etrn の `annually_s.php` を**内蔵20都市**（雪国中心に手で選んだ都市＋対照の東京・大阪）ごとにスクレイプし、
指定した**寒候年**の年合計降雪量（または最深積雪）で順位を付けて CSV + metadata.json に出力する。
**順位は「内蔵20都市の中の順位」であり、全国の都市・全観測点の順位ではない。** 出力の `Scope` 列と metadata の `scope` にそう書き出す。
落とした都市（取得失敗・値なし・資料不足値）は metadata の `dropped_cities` に名前と理由を残す。

## API情報
- **出典**: 気象庁 etrn 過去の気象データ（`annually_s.php`）
- **URL**: `https://www.data.jma.go.jp/stats/etrn/view/annually_s.php?prec_no=<>&block_no=<WMO>`
- **認証**: 不要（User-Agent は付けて取る。2026-10-26 に付けずに取っても 200 で同じ大きさの応答だった）
- **形式**: HTML テーブル（スクレイプ）/ 1都市=1リクエスト
- **単位**: cm（降雪量合計・最深積雪とも）

## 使い方
```bash
# 2024寒候年(2023年8月〜2024年7月)の年降雪量ランキング 上位15
python fetch.py --year 2024 --top-n 15 --output-dir ./output

# 最深積雪でランキング / 礼儀の待機を入れる
python fetch.py --year 2024 --metric maxsnow --sleep 0.3 --output-dir ./output
```
出力: `output/YYYYMMDD_jma_snowfall_snowfall_2024_top15.csv`（Rank,Area,CityKey,Value,Year,Metric,Unit,Flag,Scope）。
取得済み都市は `~/.cache/jma_snow/<city>.json` にキャッシュされ（取得時刻・URL・地点名・列の検出結果つき）、再実行は無通信。
取り直すときは `--refresh`。metadata の `per_city_fetch` に都市ごとの取得時刻とキャッシュ使用の有無が残る。

## ハマり所（重要）

### 1. 見出しは3段で colspan がある → 見出しを展開して名前で列を探す（最重要）
`<th>` を並び順に数えた番号は `<td>` の列番号と一致しない（colspan があるため）。
旧版は `<th>` の番号で「最深積雪」を探し、td の22列目＝**「降雪／日合計の最大」を最深積雪として出していた**（2026-10-26 に発見・修正）。
いまは見出しを rowspan/colspan ごと格子に展開し、「雪(寒候年・cm)／降雪／合計」「雪(寒候年・cm)／最深積雪」を**末尾の見出しの完全一致**で探す
（部分一致だと「降雪」「合計」が「降雪／日合計の最大」にも当たる）。見つからない・二つ当たる・段の列数が合わない・行の列数が見出しと違う、のどれでも**止める**。
固定 index へのフォールバックはやめた。
2026-10-26 に内蔵20都市すべてを取得して比べた結果、見出しの並びは20都市とも同じだった（td 28列、降雪合計＝21列目、最深積雪＝23列目）。
記録: `references/20261026_column_check.csv`。20都市以外の地点で並びが違うかは確かめていない。

### 2. 「年」は暦年でなく寒候年
表の見出しが「雪(寒候年・cm)」（ページ上の表記。上の記録の path 列）。`--year 2024` は 2023年冬〜2024年春の雪。
寒候年は「特に断りが無い限り、前年8月1日から当年7月31日まで」（気象庁 予報用語「時に関する用語」 https://www.jma.go.jp/jma/kishou/know/yougo_hp/toki.html）。暦年の降雪と混同しない。metadata と Year 列はこの寒候年。

### 3. 値欄の記号は気象庁の定義どおりに扱う
定義は気象庁「値欄の記号の説明」（https://www.data.jma.go.jp/stats/data/mdrr/man/remark.html）。
- `--` 該当現象（またはその量）がない → **0**（降雪なし）。旧版は None にして順位から消していた
- `)` 準正常値 → 正常値と同等に使う（Flag 列に `)`）。旧版は数値化に失敗して黙って落としていた
- `]` 資料不足値 → 値は信用できないので**順位から外し**、`dropped_cities` に値と理由を残す。旧版は `]` を削って正常値として使っていた
- `×` 欠測、`///` 欠測または観測していない、空白 観測していない → 値なし。順位から外し `dropped_cities` に残す
例: 2024寒候年の稚内の最深積雪は `107 ]`（資料不足値）なので、最深積雪の順位からは外れる。

### 4. User-Agent を付ける
`headers={"User-Agent": "Mozilla/5.0"}` を付けて取得する。2026-10-26 に httpx 既定の UA で取っても 200 で同じ大きさの応答だった（必須とは言えない。付けておく）。

### 5. 落とした都市は出力に残る
内蔵20都市には那覇・石垣など降雪の無い地点は入っていない。大阪の2024寒候年は `--`（降雪なし）で 0cm、東京は 10cm。
既定の上位15には東京・大阪は入らない（reference で「上位15に出ないこと」を検証。20都市中19・20位）。
取得失敗・値なしの都市は順位から外し、`dropped_cities`（名前と理由）と `n_dropped_cities` に残す。未対応の都市キーを `--cities` に書いたら止める。

### 6. 1都市=1リクエスト → ランキングはN都市ループ
元データは単一都市の時系列。ランキングは複数都市をループ取得して指定年で揃える。
**キャッシュ（都市別 JSON）と `--sleep`** で JMA への負荷を抑える。smoke_test 再実行はキャッシュで無通信。

### 7. block_no / prec_no は地点固有ID
都市→(`block_no`=WMO, `prec_no`)の対応表が必要。本レシピは20都市を内蔵（2026-10-26 に20都市すべてページの地点名で照合）。
誤ID は 404/別地点になる。旧版の秋田は仙台の番号だった。いまは取得したページの地点名（見出し「秋田（秋田県)」）が表示名で始まらなければ止める。

### 8. HTML構造変更で壊れうる
スクレイプは JMA のページ改修に弱い。見出しの構造が変われば止まる（固定 index には落ちない）。**定期的に reference で再検証**する（`verified_at` を更新）。

## 効くケース
- 内蔵20都市（雪国中心）の中の順位 × 単一寒候年 × 降雪量/最深積雪。**全国の順位として図に使わない**。使うなら注記に「20都市の中の順位」と書く
- `--cities` で対象都市を指定、`--metric maxsnow` で最深積雪

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 全国の観測点の中の順位 | 全観測点を取るレシピ | 未作成 |
| 1都市の長期時系列 | `jma/snowfall_timeseries` | 未作成 |
| AMeDAS 全観測点の面的分布 | `jma/amedas_*`（観測点が桁違い） | 未作成 |
| 平年値（1991-2020） | JMA AMeDAS normals 系レシピ | 未作成 |
| 月別・日別 | etrn の monthly/daily ページ | 未作成 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数・キャッシュは Path.home()/.cache）
- ✅ ファイルI/O は `encoding="utf-8"`、書き込みは `newline="\n"`
- ✅ 構造化例外 `DataFetchError`（source/url/kind）
- ✅ 都市ごと3回リトライ、通信の失敗都市は順位から外して `dropped_cities` に記録（地点の取り違え・表の改修は全体を止める）
- ✅ metadata.json に source URL / SHA256 / fetched_at / row_count / 寒候年
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）
- ✅ APIキー不要

## このレシピを使うLLMへのヒント
1. **見出しを colspan/rowspan ごと展開して列を名前で探す**。`<th>` の並び順の番号を td の列番号に使わない。見つからなければ止める
2. **値欄の記号は気象庁の定義で扱う**（`--`=0、`)`=使う、`]`=外して記録、`×`/`///`/空白=値なし）
3. **「年」の定義を疑う**（寒候年 vs 暦年）。気象データは集計期間の罠が多い
4. **複数地点ループは キャッシュ＋`--sleep`** で礼儀よく。reference は順位でなく不変条件で採点
5. **⚠データ源は HTML 表のスクレイプ。JSON API は存在しない**。`requests.get(url).json()` や
   `{年:{...}}` のネスト辞書を仮定すると必ず失敗する（`float()` に dict を渡す TypeError 等）。
   必ず fetch.py の HTML 解析（`<th>`/`<td>` を正規表現で抜き、`<th>` から列を動的検出）を踏襲する。
6. **出力CSVの先頭7列は固定 `Rank,Area,CityKey,Value,Year,Metric,Unit`**、続いて `Flag,Scope`。`Unit`(cm) 列を必ず付ける
   （validate が unit 項目で照合。列を落とすとデータが正しくても不合格）。`Scope` は図の注記に写す
