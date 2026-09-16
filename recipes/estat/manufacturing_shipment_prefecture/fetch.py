#!/usr/bin/env python3
"""e-Stat 経済構造実態調査（製造業・地域編）から
都道府県別 × 産業中分類別 の指標（製造品出荷額等 等）を取得し、上位ランキング CSV + metadata を出力。

汎用: 食料品に限らず任意の中分類（化学/輸送用機械/鉄鋼…）・任意の指標で使える。

使い方:
  export ESTAT_APP_ID=...   # .env にあり
  python fetch.py --list-industries                    # 取得可能な中分類を列挙
  python fetch.py --industry 食料品製造業 --measure 出荷額 --top-n 12
  python fetch.py --industry 輸送用機械 --measure 出荷額 --year 2023 --output-dir ./out

勝ちパターン（重要・recipe.md 参照）:
  - 工業統計は廃止。現役は「経済構造実態調査」（毎年）。製造品出荷額の県別×中分類は地域編表。
  - 指標は cat01(表章項目)。**cdTab でなく cdCat01 で絞る**（cdTab は黙って無視され6項目混在）。
  - 都道府県は cat02 の複合分類「年_産業_地域」に埋没＋政令市が混在 → **2桁の都道府県コードのみ**に限定。
  - 調査年 ≠ 実績年（2024年調査=2023年実績）。1表に複数実績年が同居 → --year で実績年を選ぶ。
  - 検算: 47都道府県合計 == 全国計（一致しなければ抽出ミス）。
"""
import os, sys, re, csv, json, argparse, hashlib, datetime
from pathlib import Path
import httpx

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
# 経済構造実態調査 製造業 地域編「産業中分類別…製造品出荷額等」
# ★調査年が変わったら更新。探し方: getStatsList searchWord="経済構造実態調査 製造業" で
#   "地域編 産業中分類別…製造品出荷額等" の最新 SURVEY_DATE の @id を採用（recipe.md 参照）。
PREF2 = re.compile(r"^(0[1-9]|[1-4][0-9])$")   # 01-47（都道府県のみ）

# ★地理レベルで「別の表」になる（タイトルはほぼ同名で、地域粒度だけ違う）。
#   見分け方: e-Stat検索に市区町村名(例「岡崎市」)を打つと、市区町村まで持つ表が当たる。
# 注意: 表ごとに ①statsDataId ②指標cat01コード ③単位 ④cat02の並び順 が全て違う。
LEVELS = {
    "prefecture": {   # 都道府県(+政令市) 0004035171: cat02= 年_産業_地域, 出荷額=百万円
        "stats_id": "0004035171",
        "measures": {"事業所数": "000004010010", "従業者数": "000004010020", "人件費": "000004010030",
                     "原材料": "000004010040", "出荷額": "000004010050", "付加価値": "000004010060"},
        "monetary_unit": "百万円", "order": "ind_area", "area": "pref",
    },
    "municipality": {  # 全市区町村(1946地域・町村含む) 0004035178: cat02= 年_地域_産業, 出荷額=万円
        "stats_id": "0004035178",
        "measures": {"事業所数": "000004080010", "従業者数": "000004080040", "人件費": "000004080050",
                     "原材料": "000004080060", "出荷額": "000004080070", "付加価値": "000004080080"},
        "monetary_unit": "万円", "order": "area_ind", "area": "muni",
    },
}
COUNT_UNIT = {"事業所数": "事業所", "従業者数": "人"}


class DataFetchError(Exception):
    def __init__(self, source, url, kind, message):
        super().__init__(message)
        self.source, self.url, self.kind = source, url, kind


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_json(endpoint, params, retries=3, timeout=120):
    url = f"{BASE}/{endpoint}"
    last = None
    for i in range(retries):
        try:
            r = httpx.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
    raise DataFetchError("e-Stat", url, "http", f"{endpoint} failed: {last}")


def cat02_map(stats_id, app_id):
    """cat02（年_産業_地域 複合分類）の code->name と、各エントリの分解を返す。"""
    d = get_json("getMetaInfo", {"appId": app_id, "statsDataId": stats_id})
    cls = d["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    m = {}
    for c in cls:
        if c["@id"] == "cat02":
            objs = c["CLASS"]; objs = [objs] if isinstance(objs, dict) else objs
            for o in objs:
                m[o["@code"]] = o["@name"]
    return m


def parse_name(nm):
    """'2023000000_2023_09_食料品製造業_13_東京都' -> (year, ind_code, ind_name, area_code, area_name)"""
    p = nm.split("_")
    if len(p) < 6:
        return None
    return p[1], p[2], p[3], p[4], p[5]


def parse_combined(nm, order):
    """戻り: (year, ind_code, ind_name, area_code, area_name)。表ごとに並び順が違う。"""
    p = nm.split("_")
    if len(p) < 6:
        return None
    if order == "ind_area":      # 年_産業_地域 (都道府県表)
        return p[1], p[2], p[3], p[4], p[5]
    else:                         # area_ind: 年_地域_産業 (市区町村表)
        return p[1], p[4], p[5], p[2], p[3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="prefecture", choices=list(LEVELS),
                    help="prefecture=都道府県(+政令市,0004035171) / municipality=全市区町村(0004035178)")
    ap.add_argument("--industry", default="食料品製造業", help="中分類名（部分一致可）。例: 輸送用機械, 化学")
    ap.add_argument("--measure", default="出荷額",
                    choices=["事業所数", "従業者数", "人件費", "原材料", "出荷額", "付加価値"])
    ap.add_argument("--year", default=None, help="実績年（例 2023）。未指定なら表内の最新実績年")
    ap.add_argument("--top-n", type=int, default=0, help="上位N件（0=全件）")
    ap.add_argument("--stats-id", default=None, help="表IDを明示指定（既定は level に応じて自動）")
    ap.add_argument("--list-industries", action="store_true")
    ap.add_argument("--output-dir", default=".")
    a = ap.parse_args()

    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        print("ESTAT_APP_ID 未設定（.env を読み込むこと）", file=sys.stderr); return 2

    lv = LEVELS[a.level]
    stats_id = a.stats_id or lv["stats_id"]
    order = lv["order"]
    cmap = cat02_map(stats_id, app_id)
    parsed = {code: parse_combined(nm, order) for code, nm in cmap.items()}

    years = sorted({p[0] for p in parsed.values() if p})
    industries = sorted({p[2] for p in parsed.values() if p})
    if a.list_industries:
        print(f"[level={a.level} statsId={stats_id}] 利用可能 実績年:", years)
        print("利用可能 産業中分類:")
        for ind in industries:
            print("   ", ind)
        return 0

    year = a.year or years[-1]
    ind_match = [ind for ind in industries if a.industry in ind]
    if not ind_match:
        print(f"中分類 '{a.industry}' に一致なし。--list-industries で確認を。", file=sys.stderr); return 2
    ind_name = ind_match[0]
    cd_cat01 = lv["measures"][a.measure]
    is_muni = lv["area"] == "muni"

    # ★ cdCat01 で指標を絞る（cdTab は効かない）。市区町村表は大きいので limit を上げる。
    data = get_json("getStatsData", {"appId": app_id, "statsDataId": stats_id,
                                     "cdCat01": cd_cat01, "limit": "100000"})
    sd = data["GET_STATS_DATA"]["STATISTICAL_DATA"]
    vals = sd["DATA_INF"]["VALUE"]
    vals = vals if isinstance(vals, list) else [vals]

    rows, national, suppressed = [], None, 0
    for v in vals:
        pr = parsed.get(v.get("@cat02"))
        if not pr:
            continue
        yr, ind_code, name, area_code, area_name = pr
        if yr != year or name != ind_name:
            continue
        if area_code == "00" and area_name.startswith("全国"):
            try:
                national = float(v["$"])
            except (TypeError, ValueError, KeyError):
                pass
            continue
        # 地域フィルタ
        if is_muni:
            if len(area_code) != 5:                       # 5桁=市区町村（2桁=都道府県は除外）
                continue
            if area_name == "特別区部":                   # 東京集計を除外（個別の特別区を採用）
                continue
            if area_name.endswith("区") and "市" in area_name:   # 政令市の区を除外（特別区"中央区"等は残す）
                continue
        else:
            if not PREF2.match(area_code):                # 都道府県のみ（政令市5桁を除外）
                continue
        try:
            amt = float(v["$"])
        except (TypeError, ValueError, KeyError):
            suppressed += 1                               # 秘匿(X)・欠損
            continue
        rows.append((area_code, area_name, amt))
    rows.sort(key=lambda x: x[2], reverse=True)

    total = sum(x[2] for x in rows)
    # 都道府県は 47県合計=全国計 で検算。市区町村は政令市区除外・秘匿のため一致しない→件数で報告。
    verified = (not is_muni) and (national is not None) and abs(total - national) / national < 0.005

    unit = lv["monetary_unit"] if a.measure not in COUNT_UNIT else COUNT_UNIT[a.measure]
    outdir = Path(a.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")
    stem = f"{today}_estat_mfg_{a.level}_{a.measure}_{ind_name}_{year}"
    csv_path = outdir / f"{stem}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "area_code", "area", f"value_{unit}"])
        for i, (code, area, amt) in enumerate(rows, 1):
            w.writerow([i, code, area, int(amt)])

    meta = {
        "task_name": f"経済構造実態調査 製造業 {a.level} {ind_name} {a.measure}",
        "source": {"name": "総務省・経済産業省 経済構造実態調査（製造業・地域編）",
                   "via": "e-Stat API getStatsData", "stats_data_id": stats_id, "single_source": True},
        "query": {"level": a.level, "industry_mid_class": ind_name, "measure": a.measure,
                  "measure_cat01_code": cd_cat01, "reference_year": year,
                  "area": "全市区町村(政令市の区は除外/東京特別区は残す)" if is_muni
                          else "都道府県47(政令市除外)"},
        "units": unit,
        "fetched_at": datetime.datetime.now().astimezone().isoformat(),
        "csv_sha256": sha256_of(csv_path),
        "row_count_areas": len(rows), "suppressed_or_missing": suppressed,
        "national_total": national, "sum_of_areas": total,
        "verification_sum_equals_national": verified,
        "available_years": years,
        "gotchas": "指標はcdCat01(cdTab無効)。地理レベルで別表(都道府県=0004035171/市区町村=0004035178)＝"
                   "statsId・cat01コード・単位・cat02並び順が全部違う。市区町村表は市区町村名で検索すると当たる。"
                   "都道府県は47=全国で検算、市区町村は政令市区除外＋秘匿で一致しない。",
    }
    meta_path = outdir / f"{stem}_metadata.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    div = {"百万円": 100, "万円": 10000}.get(unit, 1)
    label = "億円" if unit in ("百万円", "万円") else unit
    print(f"# [{a.level}] {ind_name} {a.measure}（{year}年実績・{stats_id}）単位:{label}")
    n = a.top_n or len(rows)
    for i, (code, area, amt) in enumerate(rows[:n], 1):
        print(f"{i:2}. {area:12} {amt/div:>12,.0f}")
    if is_muni:
        print(f"対象{len(rows)}市区町村・秘匿/欠損{suppressed}・全国計={(national or 0)/div:,.0f}{label}")
    else:
        print(f"検算: 47都道府県合計={total/div:,.0f} / 全国計={(national or 0)/div:,.0f} "
              f"-> {'OK 一致' if verified else 'NG 不一致'}")
    print(f"saved: {csv_path}\n       {meta_path}")
    return 0 if (verified or is_muni) else 1


if __name__ == "__main__":
    sys.exit(main())
