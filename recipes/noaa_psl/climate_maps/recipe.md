---
id: noaa_psl/climate_maps
api: noaa_psl
task: 世界の気候図（等温線・等圧線・降水）をNOAA長期平均から清書
tags: [noaa, psl, ncep, ncar, reanalysis, cmap, climate, temperature, pressure, precipitation, isotherm, isobar, cartopy, xarray, netcdf, monochrome, exam-figure, gis, no-auth]
summary: NOAA PSL の月別長期平均(LTM)データ（NCEP/NCAR再解析の気温・気圧、CMAPの降水）から、cartopyで等温線・等圧線・降水のモノクロ世界図を和文・出典付きで清書する。教材用。
items: [png_temp, png_slp, png_precip]
verified_at: 2026-06-16
complexity: medium
auth_required: false
gotcha_count: 6
pattern: noaa-psl-ltm-netcdf + xarray-by-name + cartopy-platecarree-contour + cyclic-point + ipaex-font
reference_impl: ../../../noaa_climate_maps_p000
---

# noaa_psl / climate_maps

## 何をする
NOAA PSL の**月別長期平均(LTM)** NetCDF から、**1月/7月の等温線・等圧線・降水量**の世界図を
**モノクロ・和文タイトル・出典付き**で清書する（教材で使える品質）。


## データ（認証不要・出典明示）
- 気温/気圧 ＝ **NCEP/NCAR Reanalysis 1**（derived surface, NOAA PSL）長期平均。`air.mon.ltm.nc`(℃) / `slp.mon.ltm.nc`(hPa)。
- 降水 ＝ **CMAP**（NOAA PSL）長期平均。`precip.mon.ltm.nc`(mm/日)。
- 風向 ＝ NCEP/NCAR Reanalysis 1 surface（NOAA PSL）。`uwnd.sig995.mon.ltm.nc`/`vwnd.sig995.mon.ltm.nc`(m/s)。矢印(quiver)で風向＋風速＝貿易風・偏西風・モンスーンが読める（`make_wind.py`）。
- DL元: `https://downloads.psl.noaa.gov/Datasets/...`。次元 `(time=12,lat,lon)`、**time=0が1月・6が7月**。

## 使い方
```bash
PY=python
$PY noaa_climate_maps_p000/scripts/fetch_data.py        # NetCDF 取得
$PY noaa_climate_maps_p000/scripts/make_climate_maps.py # 清書 → output/{jan,jul}_{temp,slp,precip}.png
```
依存: cartopy / xarray / netCDF4 / matplotlib / IPAexGothic。

## ★ハマり所
1. **気温URLの罠**: `air.mon.ltm.1991-2020.nc` は**存在せずHTMLエラー**（196B `<!DO…`）。**年号なし `air.mon.ltm.nc`** を使う（slpは1991-2020版あり）。DL時に**NetCDFマジック（\x89HDF / CDF\x0x）を検証**して取り違えを防ぐ。
2. **変数は名前で取る**: `open_dataset` の最初の data_var が **`climatology_bounds`** のことがある。`d["air"]/["slp"]/["precip"]` と名前指定。
3. **単位そのまま**: air=degC, slp=millibars(=hPa), precip=mm/日。Kelvin変換等は不要。
4. **継ぎ目消し**: `cartopy.util.add_cyclic_point` で経度0/360の空白帯を消す。
5. **`decode_times=False`** で開く（LTMの time 軸は climatology bounds で decode 失敗しやすい）。
6. **和文フォント**: `font_manager.addfont(ipaexg.ttf)`＋`rcParams`。CFF系(Hiragino)はPDF/サブセットで豆腐化→IPAex(glyf)。

## 作図仕様
- `ccrs.PlateCarree(central_longitude=0)`＋`set_global`＋`cfeature.COASTLINE`。
- 気温/気圧＝黒の等値線＋インライン値（気温−40〜40/10刻み、気圧980〜1044/4刻み）。
- 降水＝グレースケール塗り（白→濃灰6段）＋黒等値線（[0,1,2,4,8,16] mm/日）。
- `gridlines(draw_labels=True)`（上右OFF）、和文タイトル＋下端に出典。

## 拡張
- 月は `(0,'jan'),(6,'jul')` を変える（4月=3,10月=9…）。等値線間隔は `tlev/plev/rlev`。
- 中心経度・投影・変数（風・高層気温等）も同枠組みで差し替え可。

関連: [[wintri_map_cartography]] / hydrosheds/world_basin_erosion_map / naturalearth/japan_prefectures
