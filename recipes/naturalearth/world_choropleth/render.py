#!/usr/bin/env python3
"""naturalearth / world_choropleth

国レベルの階級区分図（コロプレス）を「描画」する確定レシピ。
Natural Earth admin_0 を境界に、CSV（国コード＋値）を結合し、
N分位で階級分類して PNG + PDF（日本語安全）+ metadata を出力する。

★ 苦労して確立した3つの確定パターンをコード化（2026-06-24）:
  1. 図法 = 正方形図法（PlateCarree / 投影なし matplotlib 直描き）
  2. PDF = SVG → Inkscape 変換（matplotlib PdfPages は日本語が化ける）
  3. 切り出し = centroid フィルタ禁止、xlim/ylim で範囲指定

使い方:
  python render.py --csv data.csv --code-col geo --value-col value \\
      --bbox -30 50 34 75 --classify-n 3 --title "タイトル" \\
      --output-dir ./output --basename 20260624_foo

CSV 仕様:
  - 国を識別する列（--code-col）: ISO_A2（2文字）か英語国名のどちらか。--code-kind で指定（既定 auto）
  - 値の列（--value-col）: 数値。欠損はデータなし（灰色）として描く
"""
import os, sys, json, csv as csvmod, hashlib, datetime, argparse, subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

NE_URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip"

# 高位=赤 / 中位=黄 / 低位=青（3階級の既定は手置きの3色）。N≠3 は RdYlBu_r を等分。
DEFAULT_3 = ["#4575b4", "#fee090", "#d73027"]  # 低→高
NODATA = "#e8e8e8"

# Eurostat 等で使う非ISO地理コード → Natural Earth ISO_A2 への補正
GEO_FIXUP = {"EL": "GR", "UK": "GB"}  # ギリシャ, 英国


class RenderError(Exception):
    def __init__(self, msg, kind=""):
        super().__init__(msg)
        self.kind = kind


def sha256_of(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(8192), b""):
            h.update(c)
    return h.hexdigest()


def load_ne(cache_dir):
    import geopandas as gpd
    # geopandas は URL 直読み。3回試して駄目なら止める（ローカルキャッシュは持たない。cache_dir は未使用）。
    for attempt in range(3):
        try:
            return gpd.read_file(NE_URL)
        except Exception as e:
            if attempt == 2:
                raise RenderError(f"Natural Earth 取得失敗: {e}", kind="fetch")
    return None


def quantile_classify(values, n):
    """欠損を除いた値を N 分位で階級化。境界（昇順）を返す。"""
    import pandas as pd
    s = pd.Series(values).dropna()
    if len(s) < n:
        raise RenderError(f"値のある国が {len(s)} しかなく {n} 階級に分けられない", kind="classify")
    qs = [s.quantile(i / n) for i in range(n + 1)]
    qs[0], qs[-1] = s.min(), s.max()
    # 同値が多いと境界が重なり、空の階級が凡例に並ぶ。黙って描かずに止める
    if any(qs[i] >= qs[i + 1] for i in range(n)):
        raise RenderError(f"分位の境界が重なる（同値が多い）: {qs}。階級数を減らすか値で切る",
                          kind="classify")
    return qs


def class_of(x, breaks):
    import pandas as pd
    if pd.isna(x):
        return -1
    for i in range(len(breaks) - 1):
        hi = breaks[i + 1]
        if x <= hi or i == len(breaks) - 2:
            return i
    return len(breaks) - 2


def palette(n):
    if n == 3:
        return DEFAULT_3
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    cmap = cm.get_cmap("RdYlBu_r")
    return [mcolors.to_hex(cmap(i / (n - 1))) for i in range(n)]


def main():
    ap = argparse.ArgumentParser(description="国レベル階級区分図の描画")
    ap.add_argument("--csv", required=True, help="国コード+値のCSV")
    ap.add_argument("--code-col", required=True, help="国コードの列名")
    ap.add_argument("--value-col", required=True, help="値の列名")
    ap.add_argument("--code-kind", default="auto", choices=["auto", "iso_a2", "name"],
                    help="コード種別（既定auto: 2文字ならISO_A2扱い）")
    ap.add_argument("--classify-n", type=int, default=3, help="階級数（既定3）")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "EAST", "SOUTH", "NORTH"),
                    required=True,
                    help="切り出し範囲（経度西東・緯度南北）。必須（旧版は既定が欧州で、渡し忘れると黙って欧州図になった）。"
                         "世界図なら -180 180 -90 90")
    ap.add_argument("--projection", default="platecarree",
                    choices=["platecarree", "albers", "laea", "cea"],
                    help="platecarree=正方形図法(既定) / albers=正積円錐図法(中緯度・矩形クロップ良・推奨) "
                         "/ laea=正積方位図法(形は最良だが扇形で切りにくい) "
                         "/ cea=正積円筒図法(高緯度が潰れる・非推奨)")
    ap.add_argument("--std-parallel", type=float, default=None,
                    help="cea の標準緯線（既定: bbox南北の中央）。形の歪みが最小になる緯度")
    ap.add_argument("--title", default="階級区分図", help="図タイトル")
    ap.add_argument("--unit", default="", help="凡例の単位（例: %%）")
    ap.add_argument("--source", default="", help="出典注記")
    ap.add_argument("--output-dir", default="./output")
    ap.add_argument("--basename", default=None, help="出力ファイル名の基底（既定: 日付_choropleth）")
    ap.add_argument("--font", default=None, help="日本語フォントパス（未指定なら lib.jp_font を試行）")
    args = ap.parse_args()

    import geopandas as gpd
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    # 日本語フォント
    JP_FP = None
    MAP_AXES = LEG_CHECK = LEG_FIT = LEG_PLACE = None
    try:
        # render.py → world_choropleth/ → naturalearth/ → cookbook/ → _workspace/
        wp = str(Path(__file__).resolve().parents[3] / "scripts")
        if wp not in sys.path:
            sys.path.insert(0, wp)
        from lib.jp_font import setup_matplotlib_jp
        JP_FP = setup_matplotlib_jp()
        from lib.world_map import (map_axes as MAP_AXES,
                                   assert_legend_clear as LEG_CHECK,
                                   fit_legend_axis as LEG_FIT,
                                   place_legend as LEG_PLACE)
    except Exception:
        if args.font and Path(args.font).exists():
            from matplotlib.font_manager import FontProperties
            JP_FP = FontProperties(fname=args.font)
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42

    def fp(**kw):
        return dict(fontproperties=JP_FP, **kw) if JP_FP else kw

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = args.basename or f"{datetime.date.today():%Y%m%d}_choropleth"

    # === データ読み込み ===
    df = pd.read_csv(args.csv)
    if args.code_col not in df.columns or args.value_col not in df.columns:
        raise RenderError(f"列が無い: {args.code_col}/{args.value_col} in {list(df.columns)}", kind="input")
    df = df[[args.code_col, args.value_col]].rename(
        columns={args.code_col: "code", args.value_col: "value"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    w, e, s, north = args.bbox
    if not (w < e and s < north):
        raise RenderError(f"--bbox は 西<東・南<北 で渡す: {args.bbox}", kind="input")
    codes = df["code"].dropna().astype(str)
    if codes.empty:
        raise RenderError("国コードが1件も無い", kind="input")

    # === Natural Earth 結合 ===
    print("Fetching Natural Earth 50m...")
    g = load_ne(out_dir)

    kind = args.code_kind
    if kind == "auto":
        # 先頭1件で決めると、2文字と国名が混ざったとき片方が丸ごと未結合になる。全件で見る
        lens2 = codes.str.len().eq(2)
        if lens2.all():
            kind = "iso_a2"
        elif not lens2.any():
            kind = "name"
        else:
            raise RenderError(f"2文字コードと国名が混在（2文字 {int(lens2.sum())} / 他 {int((~lens2).sum())}）。"
                              "--code-kind を明示する", kind="input")

    if kind == "iso_a2":
        # ★ Natural Earth は仏・諾などで ISO_A2="-99"（欠番）。ISO_A2_EH が正しい値を持つ。
        if "ISO_A2_EH" not in g.columns and (g["ISO_A2"] == "-99").any():
            raise RenderError("ISO_A2=-99 の国があるのに ISO_A2_EH 列が無い（NE の版を確かめる）",
                              kind="fetch")
        eh = g["ISO_A2_EH"] if "ISO_A2_EH" in g.columns else g["ISO_A2"]
        g["_key"] = g["ISO_A2"].where(g["ISO_A2"] != "-99", eh).str.upper()
        df["_key"] = df["code"].str.upper().replace(GEO_FIXUP)
    else:
        g["_key"] = g["ADMIN"]
        df["_key"] = df["code"]

    # 同じ国が2行あると後勝ちで1つに潰れ、分位にも二重に入る。止める
    dup = sorted(df.loc[df["_key"].duplicated(keep=False) & df["_key"].notna(), "_key"].unique())
    if dup:
        raise RenderError(f"同じ国コードが複数行: {dup}（年・版の違う行が混ざっていないか）", kind="input")

    # 結合検証: CSV側で地図に乗らなかったコードを必ず報告（黙って欠落させない）
    matched = set(df["_key"]) & set(g["_key"])
    unmatched = sorted(set(df["_key"].dropna()) - matched)
    print(f"結合: {len(matched)}/{len(df)} 一致")
    if unmatched:
        print(f"★  地図に未結合のコード（分位の計算にも入れない。集計行・表記ゆれを確かめる）: {unmatched}")

    # === 分類 ===
    # ★分位は「地図に乗る国の値」だけで切る。未結合のコード（World・EU 等の集計行、表記ゆれ）を
    #   入れると、地図の色分けと凡例の境界が食い違う
    n = args.classify_n
    on_map = df[df["_key"].isin(matched)]
    breaks = quantile_classify(on_map["value"].tolist(), n)
    cols = palette(n)
    df["cls"] = df["value"].apply(lambda x: class_of(x, breaks))
    cls_map = dict(zip(on_map["_key"], df.loc[on_map.index, "cls"]))
    val_map = dict(zip(on_map["_key"], on_map["value"]))
    g["cls"] = g["_key"].map(cls_map)
    g["value"] = g["_key"].map(val_map)

    # === 投影（既定=正方形図法＝再投影なし / laea・cea は to_crs で再投影）===
    midlon, midlat = (w + e) / 2.0, (s + north) / 2.0
    if args.projection in ("albers", "laea", "cea"):
        if args.projection == "albers":
            # アルベルス正積円錐図法。中緯度の東西に広い地域に最適、矩形クロップしやすい。
            # 標準緯線は「1/6ルール」（上下端から1/6内側）で歪み最小化。
            lat1 = round(s + (north - s) / 6.0)
            lat2 = round(north - (north - s) / 6.0)
            crs = (f"+proj=aea +lat_1={lat1} +lat_2={lat2} +lat_0={midlat} "
                   f"+lon_0={midlon} +datum=WGS84 +units=m +no_defs")
            proj_label = f"正積円錐図法 (Albers equal-area, 標準緯線 {lat1}/{lat2})"
        elif args.projection == "laea":
            # ランベルト正積方位図法（欧州なら EPSG:3035 相当）。円筒でないので高緯度が潰れない。
            crs = f"+proj=laea +lon_0={midlon} +lat_0={midlat} +datum=WGS84 +units=m +no_defs"
            proj_label = "正積方位図法 (Lambert azimuthal equal-area / EPSG:3035相当)"
        else:
            lat_ts = args.std_parallel if args.std_parallel is not None else round(midlat)
            crs = f"+proj=cea +lon_0={midlon} +lat_ts={lat_ts} +datum=WGS84 +units=m +no_defs"
            proj_label = f"正積円筒図法 (cylindrical equal-area, lat_ts={lat_ts})"

        import numpy as np
        from shapely.geometry import box as _shp_box
        from pyproj import Transformer

        # xlim/ylim は bbox をグリッドサンプルして投影（方位図法の湾曲した辺も内包）
        tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        lons = np.linspace(w, e, 60)
        lats = np.linspace(s, north, 60)
        gx, gy = np.meshgrid(lons, lats)
        X, Y = tr.transform(gx.ravel(), gy.ravel())
        xlim, ylim = (float(np.min(X)), float(np.max(X))), (float(np.min(Y)), float(np.max(Y)))

        # ★ 再投影アーティファクト対策: 窓で先にクリップ（遠方ジオメトリの滲み線を除去）。
        #   窓は「表示枠（投影後の矩形）を緯度経度に戻した範囲」＋2°で取る。
        #   旧版は bbox±8°で、円錐・方位図法では枠の上隅が経度で bbox の外まで広がる
        #   （欧州 -30..50 の albers で -68..88°）ため、枠の中に見える陸が切られて白く抜けていた。
        inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        ex, ey = np.linspace(*xlim, 400), np.linspace(*ylim, 400)
        fx = np.concatenate([ex, ex, np.full(400, xlim[0]), np.full(400, xlim[1])])
        fy = np.concatenate([np.full(400, ylim[0]), np.full(400, ylim[1]), ey, ey])
        flon, flat = inv.transform(fx, fy)
        flon, flat = np.asarray(flon), np.asarray(flat)
        ok = np.isfinite(flon) & np.isfinite(flat)
        wl, wr = max(float(flon[ok].min()) - 2, -180), min(float(flon[ok].max()) + 2, 180)
        ws, wn = max(float(flat[ok].min()) - 2, -89), min(float(flat[ok].max()) + 2, 89)
        for plat in (90, -90):   # 極が枠の中に入るなら、その側は極まで取る
            px, py = tr.transform(midlon, plat)
            if np.isfinite(px) and xlim[0] <= px <= xlim[1] and ylim[0] <= py <= ylim[1]:
                ws, wn = (ws, 89) if plat > 0 else (-89, wn)
                wl, wr = -180, 180
        g["geometry"] = g.geometry.buffer(0)  # 不正ジオメトリ修復
        win = _shp_box(wl, ws, wr, wn)
        g = gpd.clip(g, win)
        g = g.to_crs(crs)
        clip_window = [round(wl, 2), round(ws, 2), round(wr, 2), round(wn, 2)]
        show_axes = False
    else:
        xlim, ylim = (w, e), (s, north)
        clip_window = None
        proj_label = "正方形図法 (plate carrée / 正距円筒)"
        show_axes = True

    print(f"Rendering ({proj_label})...")
    # ★凡例は地図軸の中に置かない。loc="upper left" だと図によって陸地に
    #   かかり、毎回手で直すことになっていた（2026-09-05）。gridspec で
    #   領域を分ければ構造上かかりようがない。
    if MAP_AXES is not None:
        fig, ax, lax = MAP_AXES(figsize=(16, 12), legend="right", ratio=0.20)
    else:                                   # lib が無い環境でも分離だけは保つ
        fig = plt.figure(figsize=(16, 12))
        gs = fig.add_gridspec(1, 2, width_ratios=[0.80, 0.20], wspace=0.02)
        ax = fig.add_subplot(gs[0])
        lax = fig.add_subplot(gs[1]); lax.set_axis_off()

    # 全データを描画してから xlim/ylim で切り出す（学び③ centroid禁止）
    g.plot(ax=ax, color=NODATA, edgecolor="#333", linewidth=0.4)
    for ci in range(n):
        sub = g[g["cls"] == ci]
        if len(sub):
            sub.plot(ax=ax, color=cols[ci], edgecolor="#333", linewidth=0.7)

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    if show_axes:
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
    else:
        ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(args.title, **fp(fontsize=16, pad=12, weight="bold"))

    u = args.unit
    leg = []
    for ci in range(n):
        lo, hi = breaks[ci], breaks[ci + 1]
        cnt = int((g["cls"] == ci).sum())
        leg.append(Patch(facecolor=cols[ci], edgecolor="#333",
                         label=f"{lo:,.1f}{u} – {hi:,.1f}{u}"))
    leg.append(Patch(facecolor=NODATA, edgecolor="#999", label="データなし"))
    # legend は fontproperties でなく prop= を取る
    # ★空いた隅を探して地図の中に置く。どの隅もデータに当たるときだけ外へ。
    #   固定の凡例帯を常に確保すると、重なっていない図まで毎回縮んで劣化した。
    if LEG_PLACE is not None:
        _lg, _where = LEG_PLACE(fig, ax, leg, geoms=g.geometry, lax=lax,
                                prop=JP_FP, fontsize=12)
        print(f"凡例の位置: {_where}")
    else:
        leg_kw = dict(prop=JP_FP) if JP_FP else {}
        ax.legend(handles=leg, loc="upper left", fontsize=12, **leg_kw)
        _where = "upper left"

    if args.source:
        if _where == "outside":
            lax.text(0.0, 0.0, args.source, transform=lax.transAxes,
                     va="bottom", ha="left", wrap=True, **fp(fontsize=9))
        else:
            ax.text(0.01, 0.01, args.source, transform=ax.transAxes,
                    **fp(fontsize=9),
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.95))
    if _where != "outside" and lax is not None:
        lax.set_visible(False)      # 中に置けた＝凡例帯は不要。地図に返す
        ax.set_position([ax.get_position().x0, ax.get_position().y0,
                         lax.get_position().x1 - ax.get_position().x0,
                         ax.get_position().height])
    fig.tight_layout()
    if LEG_FIT is not None and _where == "outside":
        LEG_FIT(fig, ax, lax)       # 外に出したときだけ帯を実寸まで詰める
    if LEG_CHECK is not None:
        LEG_CHECK(ax, lax)          # 重なっていないことを落として確かめる

    # === 出力（学び②PDFはSVG→Inkscape）===
    png = out_dir / f"{base}.png"
    svg = out_dir / f"{base}.svg"
    pdf = out_dir / f"{base}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(svg, format="svg", bbox_inches="tight")
    plt.close(fig)

    pdf_method = "none"
    try:
        subprocess.run(["inkscape", str(svg), "-o", str(pdf)],
                       check=True, capture_output=True, timeout=60)
        pdf_method = "inkscape(svg)"
        print(f"○ PDF (Inkscape): {pdf}")
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as ex:
        print(f"★  Inkscape 変換不可（{type(ex).__name__}）。PDFは未生成（SVGを使用してください）。")

    # === metadata ===
    class_counts = {str(ci): int((g["cls"] == ci).sum()) for ci in range(n)}
    n_on_map = int(g["_key"].isin(matched).sum())
    nodata_count = int((g["_key"].isin(matched) & g["value"].isna()).sum())
    # 検算: 階級ごとの国数＋値の欠損＝地図に乗った国（NE の面）の数
    assert sum(class_counts.values()) + nodata_count == n_on_map, \
        (class_counts, nodata_count, n_on_map)
    meta = {
        "recipe": "naturalearth/world_choropleth",
        "title": args.title,
        "code_kind": kind,
        "classify_n": n,
        "class_breaks": [round(float(b), 4) for b in breaks],
        "class_counts": class_counts,
        "nodata_count": nodata_count,
        "n_countries_on_map": n_on_map,
        "breaks_from": "地図に結合できた国の値のみ（未結合コードは除外）",
        "bbox": {"west": w, "east": e, "south": s, "north": north},
        "scope": (f"表示範囲 経度{w}〜{e}・緯度{s}〜{north}。色は入力CSVの国のうち地図に結合できた"
                  f"{len(matched)}件（未結合 {len(unmatched)}件は描かない）"),
        "clip_window_lonlat": clip_window,
        "projection": proj_label,
        "pdf_method": pdf_method,
        "source_dataset": NE_URL,
        "source_note": args.source,
        "unmatched_codes": unmatched,
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "png_sha256": sha256_of(png),
        "svg_sha256": sha256_of(svg),
        "pdf_sha256": sha256_of(pdf) if pdf.exists() and pdf.stat().st_size > 0 else None,
    }
    meta_path = out_dir / f"{base}_metadata.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"○ PNG: {png}")
    print(f"○ SVG: {svg}")
    print(f"○ META: {meta_path}")
    print(f"分類境界: {[round(float(b),1) for b in breaks]}  階級数={n}")


if __name__ == "__main__":
    try:
        main()
    except RenderError as e:
        print(f"× {e.kind}: {e}", file=sys.stderr)
        sys.exit(1)
