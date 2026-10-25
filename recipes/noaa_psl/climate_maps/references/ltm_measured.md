# NOAA PSL LTM ファイルの実測（2026-10-26）

入力: 手元に取得した *.mon.ltm.nc（2026-06-16 取得）。xarray（decode_times=False）で読んだ。

| ファイル | 緯度 | 格子 | NaN | climatology_bounds（time=0） | 1月 最小/最大 | 7月 最小/最大 |
|---|---|---|---|---|---|---|
| air（sigma 0.995, degC） | −90〜90 | 73×144 | 0 | 1991-01-01〜2020-01-01（time=11 終端 2020-12-01） | −37.5 / 33.6 | −62.1 / 39.7 |
| slp（millibars） | −90〜90 | 73×144 | 0 | 同上 | 983.4 / 1042.0 | 980.0 / 1055.7 |
| precip（CMAP, mm/day） | −88.75〜88.75 | 72×144 | 5828 | 同上 | 0.0 / 20.2 | 0.0 / 25.3 |
| uwnd（sigma 0.995, m/s） | −90〜90 | 73×144 | 0 | 同上 | −10.5 / 10.6 | −14.0 / 12.3 |
| vwnd | 同上 | | | 同上 | | |

- time=6 の climatology_bounds の始まりは 1991-07-01 → time=0 が1月、6 が7月。
- precip の NaN がある緯度（1月）: 73.75〜88.75°N、66.25〜73.75°S。
- 7月 air < −40℃ の格子は南緯70〜90°。7月 slp > 1044hPa の格子は南緯75〜85°。

URL の確認（curl、Range 0-200）:
- ncep.reanalysis.derived/surface/air.mon.ltm.1991-2020.nc → 404, text/html, 196B
- ncep.reanalysis.derived/surface/slp.mon.ltm.1991-2020.nc → 206, application/x-netcdf
- ncep.reanalysis.derived/surface/air.mon.ltm.nc → 206, application/x-netcdf
