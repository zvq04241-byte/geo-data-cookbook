---
id: jma/amedas_normals
api: jma
task: AMeDAS 平年値(1991-2020) 観測所別テーブル
tags: [jma, kishocho, amedas, climate, normals, temperature, precipitation, ranking, japan, station-level, bulk-zip, no-auth]
summary: 気象庁 AMeDAS 月別平年値ZIPと観測所座標から、観測所別の年平均気温・年降水量等を取得し指標降順CSVに出力
items: [mean_temp, max_temp, annual_prec, annual_wind, annual_snow]
verified_at: 2026-06-08
complexity: medium
auth_required: false
gotcha_count: 8
pattern: bulk-zip-csv + json-coord-join + element-code-every-other-column
---

# jma / amedas_normals

## 何をする
気象庁の AMeDAS 月別平年値ZIP（1991-2020）と観測所座標表（amedastable.json）から、
観測所ごとの**年平均気温・年降水量・年平均風速・年降雪量**を取得し、
指定指標で降順に並べた CSV + metadata.json を出力する（地図用の空間間引きはしない＝全観測所）。

## API情報
- **出典**: 気象庁 AMeDAS 平年値 1991-2020
- **URL**:
  - 座標表: `https://www.jma.go.jp/bosai/amedas/const/amedastable.json`
  - 平年値: `https://www.data.jma.go.jp/stats/data/mdrr/normal/2020/data/normal_amedas_monthly.zip`
- **認証**: 不要（**User-Agent 必須**）
- **形式**: JSON（座標）＋ ZIP内の観測所別CSV（平年値）

## 使い方
```bash
# 年平均気温で降順（既定・全観測所）
python fetch.py --output-dir ./output
# 年降水量で降順 / 上位N
python fetch.py --metric annual_prec --top-n 30 --output-dir ./output
```
出力: `output/YYYYMMDD_amedas_normals_mean_temp.csv`
（Rank,Area,Value,BlockNo,Lat,Lon,MeanTemp,MaxTemp,AnnualPrec,AnnualWind,AnnualSnow,Unit）。
取得結果は `~/.cache/amedas_normals/station_records.json` にキャッシュ。

## ハマり所（重要）

### 1. 月別値は「6列目以降の1列おき」・要素コードは3列目（最重要）
平年値CSVの各行は、`cols[2]` が要素コード、月別値は **`cols[6 + i*2]`（i=0..11）の1列おき**で並ぶ
（間の列は統計品質情報など）。素直に連続列として読むと全て狂う。`len(cols) >= 32` の行のみ採用。

### 2. 要素コードと単位（0.1 単位に注意）
`0500`=平均気温(**0.1℃**) / `4000`=降水量合計(**0.1mm**) / `2600`=平均風速(**0.1m/s**) / `1500`=降雪量(cm)。
気温・降水・風速は **10で割る**。年平均気温=12か月平均、最暖月=max、年降水=12か月合計。

### 3. 観測所座標は別ファイル・[度,分]配列
緯度経度は平年値ZIPに無く、`amedastable.json` 側にある。しかも **`lat:[度,分]` 配列**なので
`度 + 分/60` で十進化する。生の `lat[0]` だけ使うと分を落とす。

### 4. ZIP内CSV名 → block_no、座標表に無い局はスキップ
ファイル名末尾が観測所番号: `name.split('_')[-1].replace('.csv','')`。
amedastable に無い番号（特殊局等）はスキップする。

### 5. 欠測・未観測は 0 で来る → None 化
平年値が無い要素は月別が全 0 で来ることがある。`any(v != 0)` で**全0を None 扱い**にする。
**降雪だけは None（未観測）と 0（無雪）を区別**する（南国は未観測、雪無し地域は 0）。

### 6. User-Agent 必須
`headers={"User-Agent": "Mozilla/5.0"}` を付けないとアクセスが弾かれることがある。

### 7. 全観測所を出す（間引きは地図側の責務）
1277局を読み、気温平年値が揃う **905局** を出力。元コードにあった「グリッド1局間引き」は
地図描画用なので**このレシピでは行わない**（素データを全量供給する）。

### 8. 平年値は固定（1991-2020）
平年値は10年ごと更新で、現行は 1991-2020 で固定。次回更新（〜2031頃）まで row_count は安定。
URL の `normal/2020/` がその版を指す。

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
1. **固定オフセット列レイアウト（1列おき）は実データで確認**してから読む。連続列の思い込みは禁物
2. **0.1 単位**の生値に注意（気温・降水・風速は ÷10）。指標の定義（平均/合計/最大）を明示
3. **座標は別ファイル**でしばしば [度,分] 形式。十進化を忘れない
4. **欠測 0 を None 化**、降雪は未観測と無雪を区別。reference は順位でなく不変条件で採点
5. **⚠出力CSVの最終列に `Unit` を必ず付ける**（mean_temp/max_temp は `°C`、降水 `mm`、風速 `m/s`）。
   列は `Rank,Area,Value,BlockNo,Lat,Lon,...,Unit`。`Unit` 列を落とすと、データが全て正しくても
   validate の unit 項目で不合格になる（実際に qwen3-coder-next が Unit 列を出し忘れて失敗した）。
