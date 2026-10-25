---
id: jma/amedas_normals
api: jma
task: AMeDAS 平年値(1991-2020) 観測所別テーブル
tags: [jma, kishocho, amedas, climate, normals, temperature, precipitation, ranking, japan, station-level, bulk-zip, no-auth]
summary: 気象庁 AMeDAS 月別平年値ZIPと観測所座標から、観測所別の年平均気温・年降水量等を取得し指標降順CSVに出力
items: [mean_temp, max_temp, annual_prec, annual_wind, annual_snow]
verified_at: 2026-10-26
complexity: medium
auth_required: false
gotcha_count: 8
pattern: bulk-zip-csv + json-coord-join + element-code-every-other-column
---

# jma / amedas_normals

## 何をする
気象庁の AMeDAS 月別平年値ZIP（1991-2020）と観測所座標表（amedastable.json）から、
観測所ごとの**年平均気温・年降水量・年平均風速・年降雪量**を取得し、
指定指標で降順に並べた CSV + metadata.json を出力する（地図用の空間間引きはしない＝その指標の値がある全観測所）。

## API情報
- **出典**: 気象庁 AMeDAS 平年値 1991-2020
- **URL**:
  - 座標表: `https://www.jma.go.jp/bosai/amedas/const/amedastable.json`
  - 平年値: `https://www.data.jma.go.jp/stats/data/mdrr/normal/2020/data/normal_amedas_monthly.zip`
- **認証**: 不要（User-Agent は付けて取る。2026-10-26 に付けずに取っても 200 で同じ大きさの応答だった）
- **形式**: JSON（座標）＋ ZIP内の観測所別CSV（平年値）

## 使い方
```bash
# 年平均気温で降順（既定・全観測所）
python fetch.py --output-dir ./output
# 年降水量で降順 / 上位N
python fetch.py --metric annual_prec --top-n 30 --output-dir ./output
```
出力: `output/YYYYMMDD_amedas_normals_mean_temp.csv`
（Rank,Area,Value,BlockNo,Lat,Lon,MeanTemp,MaxTemp,AnnualPrec,AnnualWind,AnnualSnow,Unit,NormYears,NormStart,NormEnd）。
取得した ZIP と座標表は `~/.cache/amedas_normals/` に生のままキャッシュ（旧版の station_records.json は使わない）。

## ハマり所（重要）

### 1. 値とRMKが交互に並ぶ・要素番号は3列目（最重要）
記録様式は気象庁「平年値ファイルの形式」（https://www.data.jma.go.jp/stats/data/mdrr/normal/2020/doc/format_amedas.pdf）にある:
`種別(21), 観測所番号, 要素番号, 資料年数, 統計開始年, 統計終了年, 1月の値, RMK, …, 12月の値, RMK, 年の値, RMK` の**32列**。
月の値は `cols[6 + i*2]`、年の値は `cols[30]`。素直に連続列として読むと全て狂う。32列でない行が出たら止める。
2026-10-26 に取得した ZIP（CSV 1298本）では全行が32列だった。

### 2. 要素番号と単位（0.1 単位に注意）・★降雪は 6300
`0500`=気温 月・年平均(**0.1℃**) / `4000`=降水量 月・年合計(**0.1mm**) / `2600`=風速 月・年平均(**0.1m/s**) /
`6300`=積雪差1時間差 月・年合計(**1cm**、降雪量)。
**旧版は降雪を `1500` で読んでいたが、`1500` は「日最低気温＜0.0℃ 月・年間日数（0.1日）」＝冬日の日数**だった（同PDFの要素番号表。2026-10-26 修正）。
年の値は気象庁が収録した**年の値（cols[30]）**を使う（旧版は月の値を12で割っていた。年平均気温で94局が0.1℃ずれる）。最暖月=月の値の最大。

### 3. 観測所座標は別ファイル・[度,分]配列
緯度経度は平年値ZIPに無く、`amedastable.json` 側にある。しかも **`lat:[度,分]` 配列**なので
`度 + 分/60` で十進化する。生の `lat[0]` だけ使うと分を落とす。

### 4. ZIP内CSV名 → block_no、座標表に無い局は外して記録
ファイル名末尾が観測所番号: `name.split('_')[-1].replace('.csv','')`。
2026-10-26 時点で ZIP内 1298局のうち **21局**が amedastable.json に無い（廃止局と見られるが確かめていない）。
外した番号は metadata の `skipped_not_in_station_table` に残る。

### 5. 値なしは RMK で判定する（0 は値なしのこともある）
RMK は `8`=正常値、`0`=統計値なし（同PDF「リマーク」）。統計値なしの月は値が `0` で入っている。
**RMK=8 の値だけ使う。** 旧版は「月の値が全部0なら値なし」で判定しており、
一部の月だけ統計値なしの局（例: 資料年数8年の局で1〜3月が統計値なし）の年平均気温を、0を混ぜて低く出していた。
降雪は「観測していない局」と「降雪0の局」を RMK で区別できる（6300 の年の値が RMK=8 の局は 320）。
値なしの理由別の件数は metadata の `no_value_reasons`。

### 6. User-Agent を付ける
`headers={"User-Agent": "Mozilla/5.0"}` を付けて取得する。2026-10-26 に httpx 既定の UA で取っても 200 で同じ応答だった（必須とは言えない。付けておく）。

### 7. 値のある全観測所を出す（間引きは地図側の責務）・母数は指標で変わる
2026-10-26 の ZIP で測った件数（座標表にある1277局が母数）:
年平均気温 903 / 最暖月 904 / 年降水量 1228 / 年平均風速 873 / 年降雪量 320。（記録: `references/20261026_counts.json`）
**指標ごとに母数が違う**ので、出力の範囲は metadata の `scope` に書き出す（`--top-n` を付けたら「上位N」とも書く）。
元コードにあった「グリッド1局間引き」は地図描画用なので**このレシピでは行わない**。

### 8. 平年値の統計期間は局で違う・ZIP は差し替えがある
統計期間 1991-2020 は30年そろった局の話で、**資料年数が30年未満の局がある**（年平均気温903局のうち130局。例 2003〜2020年）。
CSV の `NormYears,NormStart,NormEnd` に局ごとの期間を出す。図の注記で「1991-2020年平年値」と書くなら、短い局を含むことも書く。
気象庁の平年値ページには「第5版の変更ファイル」があり、ZIP は版が差し替わる。metadata の `inputs.normals_zip.sha256` で版を見分ける。
キャッシュ（`~/.cache/amedas_normals/` の ZIP と座標表）を使ったかどうかも `inputs.*.from_cache` に残る。取り直すときは `--refresh`。

## 効くケース
- 観測所別の気温・降水平年値ランキング/テーブル
- 気候平年値地図のベースデータ（lat/lon 付き）
- `--metric` で気温/降水/風速/降雪を切替

## 効かないケース（別レシピ推奨）
| 要求 | 推奨 | 状態 |
|---|---|---|
| 月別の平年値（12か月分） | 本レシピを拡張（年集約を外す） | 未対応 |
| 観測値（平年でなく実測年） | `jma/snowfall_ranking` 等 etrn 系 | 一部実装 |
| 地図描画・空間間引き | 各プロジェクト側 | 範囲外 |
| 標高・観測所詳細メタ | amedastable の全項目を使う拡張 | 未対応 |

## 規約準拠状況
- ✅ パスは `Path(__file__)` 基点（CLI引数・キャッシュは Path.home()/.cache）
- ✅ 出力 CSV/JSON は `encoding="utf-8"`、CSVは `newline="\n"`
- ✅ 構造化例外 `DataFetchError`（source/url/kind）
- ✅ 取得3回リトライ、観測所表＋平年値をキャッシュ
- ✅ metadata.json に 2 ソースURL / SHA256 / row_count / 平年期間
- ✅ `sys.stdout/stderr.reconfigure(encoding="utf-8")`（Win cmd.exe 対策）
- ✅ APIキー不要

## このレシピを使うLLMへのヒント
1. **列の並びは気象庁の形式文書（format_amedas.pdf）で確かめて読む**。要素番号の意味も文書で引く（1500 を降雪と思い込んだ誤りがあった）
2. **0.1 単位**の生値に注意（気温・降水・風速は ÷10）。指標の定義（平均/合計/最大）を明示
3. **座標は別ファイル**でしばしば [度,分] 形式。十進化を忘れない
4. **値なしは RMK で判定**（0 を値なしと見なさない／値と見なさない）。reference は順位でなく不変条件で採点
5. **⚠出力CSVの最終列に `Unit` を必ず付ける**（mean_temp/max_temp は `°C`、降水 `mm`、風速 `m/s`）。
   列は `Rank,Area,Value,BlockNo,Lat,Lon,...,Unit`。`Unit` 列を落とすと、データが全て正しくても
   validate の unit 項目で不合格になる（記録: `_workspace/experiments/local_recipe_check_20260620/RESULTS.md` の jma_amedas 行。ローカルモデルの生成コードが Unit 列を出さず unit 項目だけ不合格）。
