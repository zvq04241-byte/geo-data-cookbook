---
id: cams/dust_aod_map
api: cams
task: サハラ砂塵などのダスト分布図（光学的厚さ）をCAMSから清書／平年＝定常 vs 事例＝一時の2図対比
tags: [cams, copernicus, ads, cdsapi, dust, aerosol, aod, duaod550, eac4, reanalysis, forecast, sahara, mediterranean, cartopy, xarray, netcdf, monochrome, exam-figure, gis, auth]
summary: CAMS（Copernicus 大気監視）のダスト光学的厚さ(550nm)から、ヨーロッパ域のモノクロ濃度分布図を和文・出典付きで清書する。EAC4再解析の月平均で「平年（定常）」、予報データで「特定日の事例（一時）」を描き、気候スケール vs 気象スケールを2図で対比できる。
items: [png_clim_april, png_event_day]
verified_at: 2026-06-16   # 何を測ったかは references/measured_20261026.md（2026-10-26。年リスト・変数名・次元・最大値）
complexity: medium
auth_required: true
gotcha_count: 7
pattern: cdsapi-ads-minimal-request + duaod550-single-level + forecast-vs-eac4-monthly + xarray-isel-time + cartopy-platecarree-contour + ipaex-font
reference_impl: (非公開)
---

# cams / dust_aod_map

## 何をする
CAMS の **ダストの光学的厚さ（dust AOD 550nm）** から、ヨーロッパ＋北アフリカ域の
**モノクロ濃度分布図**を**和文タイトル・出典付き**で清書する（新聞掲載のダスト図と同系統を、Copernicusのオープンデータから独自作図）。
2系統を1組で扱う:
- **平年図（気候・定常）** ＝ EAC4 **再解析の月平均**を複数年平均（実体は4月・2003〜2023年の21年）→ 4月の平年場で、**サハラから地中海へ**の張り出しが見える。図が示すのは分布だけで、運ぶ風系（シロッコ等）は図からは言えない。
- **事例図（気象・一時）** ＝ **予報データ**の特定日時 → ダストが**中部ヨーロッパまで**及んだ1日（実体は 2024-04-07 12UTC）。一例であり、代表性や「記録的」かどうかは本レシピでは確かめていない。
（平年／事例の2図対比）。

## データ（認証必要・出典明示）
- **事例**: `cams-global-atmospheric-composition-forecasts`（予報）、変数 `dust_aerosol_optical_depth_550nm`、`type=forecast`・`leadtime_hour=0`。日次・時刻指定。★`leadtime_hour=0` は予報の**初期時刻の値**（先の予測ではない）。「予報」と書くと将来の予測と読まれるので、図の説明は「予報データの初期値」とする。
- **平年**: `cams-global-reanalysis-eac4-monthly`（EAC4再解析・月平均, 2003年〜。実体は 2003〜2023 の4月21年・欠けなし＝references/measured_20261026.md）、`product_type=monthly_mean`、対象月を複数年取得し**作図側で年平均**。
- いずれも **NetCDF変数名は `duaod550`**（**単層**＝大気の柱で1枚。気圧面・モデル面は不要）。
- ★**モデル解析/再解析の推定値**であり実測点ではない（NOAA再解析と同じ注記）。出典は「CAMS（Copernicus）より作成・モデル解析値／再解析値」。

## 認証
ADS（Atmosphere Data Store）の個人トークンを `~/.cdsapirc` に:
```
url: https://ads.atmosphere.copernicus.eu/api
key: <個人アクセストークン>
```
登録は無料（ads.atmosphere.copernicus.eu）。

## 使い方
```bash
PY=python
# 実体は非公開（手元の作業場で実行した）
$PY cams_dust_europe_p000/scripts/fetch_cams_dust.py        # 事例: 予報 2024-04-05〜08・00/12UTC → data/cams_dust_*.nc
$PY cams_dust_europe_p000/scripts/fetch_cams_dust_clim.py   # 平年: EAC4月平均(4月×2003〜2023の21年) → data/cams_dust_april_clim_*.nc
$PY cams_dust_europe_p000/scripts/make_cams_dust_map.py     # 事例図 → output/dust_europe_cams_YYYYMMDD.png
$PY cams_dust_europe_p000/scripts/make_cams_dust_clim_map.py# 平年図 → output/dust_europe_cams_april_clim.png
```
依存: cdsapi / xarray / netCDF4 / cartopy / matplotlib / IPAexGothic。

## ★ハマり所
1. **巨大リクエストの罠**: ADSのダウンロード画面が出す「APIリクエスト例」は**全変数・全気圧面・全モデル面・全予報時間**を含み、非常に大きくなる（大きさは測っていない）。**dust AOD 1変数・必要な日時だけ**に絞る（実測: area 切り出し・1変数で事例 378KB／平年 286KB）。
2. **利用規約の未同意で拒否される**: 各データセットのページで**Terms of use / licence に同意**しておく（CAMS forecasts と EAC4 は別同意）。エラーの番号は記録していない。
3. **`area` でヨーロッパに切り出す**: `area=[N, W, S, E]`（例 `[62,-25,20,35]`）。全球は不要。★この範囲は**北緯20°以南と東経35°以東が入らない**。実測で平年の最大（0.355）が南端の行（0.353）でほぼ出ており、**ダストの多い所が南端で切れている**。図の説明に範囲（北緯20〜62°・西経25°〜東経35°）を書き、「サハラ全域」とは書かない。
4. **変数名は `duaod550`**: `data_format=netcdf` で取ると変数キーは `duaod550`（`dust_aerosol_optical_depth_550nm` ではない）。実測で確認（references/）。版が変わると変わりうるので、取得後に `list(ds.data_vars)` で確かめてから読む。★**ダストだけ**の光学的厚さで、全エアロゾルの AOD ではない。図の凡例・説明は「ダストの光学的厚さ」とし、「AOD」だけにしない。
5. **予報データの多時刻で `.squeeze()` が壊れる**: 数日×複数時刻だと次元が `(forecast_period, forecast_reference_time, lat, lon)`。1枚を選ぶには `da.isel(forecast_reference_time=k, forecast_period=0)`（時刻の並びは date×time の昇順）。実測（2024-04-05〜08・00/12UTC の取得）で次元・並びとも確認。取得条件が変わったら `da.dims` と `forecast_reference_time` の値を出してから選ぶ。
6. **平年図と事例図で濃淡の桁が違う**: 実測（上の area・4月2003〜2023平均／2024-04-07 12UTC）で、平年の最大 0.355、事例の最大 1.81。**同じ levels では平年が淡すぎる**。実体は平年図 `levels=[0.02..0.33]`、事例図 `[0.05..1.2]`（extend="max"）と分け、**並置時は「左右で目盛りが異なる」旨を明記**し、各図にカラーバーを付ける（色の濃さは左右で比べられない。強度差を言うなら最大値を数で書く）。
7. **EAC4月平均の年平均は作図側で**: monthly_mean は年ごとに時間次元が残る。`da.mean(dim=[lat/lon以外の次元])` で平年場にする。

## 体裁（教材品質）
- `cmap="Greys"`・`contourf`＋細い `contour`、海岸線（黒）＋国境（細灰）、`gridlines(draw_labels=True)`。
- IPAexGothic で和文の文字化け回避。`from lib.font_setup import setup`（正規の置き場 `_workspace/assets/fonts/ipaexg.ttf`）を使う。実体のスクリプトは別プロジェクトの assets を直に指しているので、再利用時は lib に差し替える。
- 出典脚注に「CAMS（Copernicus）より作成。値はモデル解析（推定値）」を必ず入れる。

## 関連
- 気候図の等温線・等圧線・降水は [noaa_psl/climate_maps]。docx組版は [docx/kyotsu_exam_layout]。
- ローカルLLMは**この確定スクリプトを再利用**（日時・領域・levels差し替え）する前提。ゼロ生成はハマり所1・5でほぼ失敗。
