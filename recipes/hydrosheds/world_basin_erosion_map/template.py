#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hydrosheds/world_basin_erosion_map — ウィンケル世界主題図の作図テンプレート（再利用核）。

データ取得は reference_impl（river_erosion_p000/scripts/fetch_basins.py, fetch_drainage.py）側。
本ファイルは**作図の確定パターン**だけを部品化したもの。ローカルLLMはここを土台に
GeoDataFrame を差し替えて使う。罠の根拠は recipe.md「ハマり所」を参照。

提供物:
  PROJ                         ウィンケル・トリペル proj4
  winkel_graticule()           経緯線（±88で枠を閉じる）→ GeoSeries(PROJ)
  to_proj(gdf) / xy(lon,lat)   投影ヘルパ
  prop_radius(v,vmax,R)        比例円の半径（面積∝値・半径∝√値）
  ZONE                         内陸/無河/河川流域の配色（地図と凡例で共有＝ズレ防止）
  draw_zones(ax, arheic, endorh, basins)   2区分網掛け＋流域（不透明・黒縁）
  tangent_legend(ax, ...)      接線入り入れ子円＋スウォッチ凡例（オーバル内に置く）
"""
import numpy as np
import geopandas as gpd
from shapely.geometry import Point, LineString
import matplotlib.pyplot as plt

PROJ = "+proj=wintri +datum=WGS84 +units=m +no_defs"   # ウィンケル・トリペル（教科書/exam風）

# 濃淡は1箇所で定義し地図plotと凡例swatchの両方で参照（別ハードコードは凡例/地図ズレの元）
ZONE = {"無河流域": "#ededed", "内陸流域": "#aaaaaa", "河川流域": "#6e6e6e"}   # 薄→濃, 河川流域が最濃


def to_proj(gdf):
    return gdf.to_crs(PROJ)


def xy(lon, lat):
    return gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(PROJ).iloc[0]


def winkel_graticule(dlon=30, dlat=20):
    """経緯線。★緯線の両端に±88を必ず含め楕円の上下枠を閉じる（無いと「北極が切れる」）。"""
    g = []
    for lon in range(-180, 181, dlon):
        g.append(LineString([(lon, la) for la in range(-88, 89, 2)]))        # 経線は±88まで
    lats = sorted({-88, 88} | set(range(-80, 81, dlat)))                     # ★±88で枠を閉じる
    for lat in lats:
        g.append(LineString([(lo, lat) for lo in range(-180, 181, 2)]))
    return gpd.GeoSeries(g, crs="EPSG:4326").to_crs(PROJ)


def prop_radius(v, vmax, R=0.85e6):
    return R * np.sqrt(v / vmax)


def draw_zones(ax, arheic=None, endorh=None, basins=None):
    """無河（薄）→内陸（中）→河川流域（最濃）の順に重ねる。全て不透明・黒縁。"""
    if arheic is not None:
        arheic.plot(ax=ax, facecolor=ZONE["無河流域"], edgecolor="black", linewidth=0.35, zorder=2.2)
    if endorh is not None:
        endorh.plot(ax=ax, facecolor=ZONE["内陸流域"], edgecolor="black", linewidth=0.35, zorder=2.3)
    if basins is not None:
        basins.plot(ax=ax, facecolor=ZONE["河川流域"], edgecolor="black", linewidth=0.4, zorder=3)


def tangent_legend(ax, lx, lyb, values, title, vmax, R=0.85e6, swatches=("河川流域", "内陸流域", "無河流域")):
    """接線入り入れ子円＋スウォッチ凡例。lx,lyb は**オーバル内の空き海域**起点 例: xy(-172,-50)。
    values は降順（例 [1400,400,100]）。下から 円→タイトル→スウォッチ を上に積む。"""
    cx = lx + prop_radius(values[0], vmax, R)
    xline = cx + prop_radius(values[0], vmax, R) + 0.5e6
    for v in values:
        rr = prop_radius(v, vmax, R)
        ax.add_patch(plt.Circle((cx, lyb + rr), rr, facecolor="none", edgecolor="black", linewidth=0.9))
        yt = lyb + 2 * rr
        ax.plot([cx, xline], [yt, yt], color="#555555", linewidth=0.5)        # 接線
        ax.text(xline + 0.12e6, yt, f"{v:,}", fontsize=8, va="center", ha="left")
    top = lyb + prop_radius(values[0], vmax, R) * 2
    ax.text(lx, top + 0.45e6, title, fontsize=9.5, va="bottom")
    for i, lab in enumerate(swatches):                                        # 上から濃→薄
        yy = top + 1.30e6 + i * 0.62e6
        ax.add_patch(plt.Rectangle((lx, yy), 0.5e6, 0.3e6, facecolor=ZONE[lab],
                                   edgecolor="black", linewidth=0.6))
        ax.text(lx + 0.65e6, yy + 0.15e6, lab, fontsize=8.5, va="center")


# ── 組み立て順（reference_impl の make_erosion_map.py が完全版）──────────────
# fig, ax = plt.subplots(figsize=(12.2, 6.6), dpi=150)
# winkel_graticule().plot(ax=ax, color="#e6e6e6", lw=0.35, zorder=1)
# land.plot(ax=ax, color="#ffffff", edgecolor="#222222", lw=0.6, zorder=2)   # 陸白・海岸線黒
# draw_zones(ax, arheic, endorh, basins)                                     # 無河→内陸→河川流域
# rivers.plot(ax=ax, color="#3a6ea5", lw=0.45, zorder=4)                     # 流路
# ... 比例円は河口でなく引出線の先（海洋上）／ラベルは白bbox込み+0.42e6クリアランス ...
# ax.set_axis_off(); ax.set_aspect("equal")
# extent は grat/land の total_bounds＋全円・全ラベルから set_xlim/ylim を明示（見切れ防止）
# tangent_legend(ax, *(xy(-172,-50).x, xy(-172,-50).y), [1400,400,100], "平均侵食速度（t/km²・年）", vmax)
# fig.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.1)
