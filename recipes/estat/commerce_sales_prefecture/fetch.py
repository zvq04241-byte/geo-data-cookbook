#!/usr/bin/env python3
"""e-Stat 経済センサス活動調査（卸売業・小売業）から
都道府県別 × 産業分類別 の指標（年間商品販売額 等）を取得し、上位ランキング CSV + metadata を出力。

汎用: 飲食料品に限らず任意の産業（各種商品/織物衣服/機械器具/飲食料品…）・卸売/小売で使える。
姉妹レシピ: estat/manufacturing_shipment_prefecture（製造業側）。

使い方:
  export ESTAT_APP_ID=...   # .env にあり
  python fetch.py --list-industries                      # 取得可能な産業分類(コード:名称)を列挙
  python fetch.py --industry 52 --measure 販売額 --top-n 12      # 飲食料品卸売業
  python fetch.py --industry 58 --measure 販売額                  # 飲食料品小売業
  python fetch.py --industry 飲食料品小売 --measure 売場面積       # 名称部分一致も可

勝ちパターン（recipe.md 参照）:
  - 商業統計は廃止。卸売/小売の構造データは「経済センサス活動調査」（5年ごと: 2012/2016/2021）。
  - 指標は **tab（表章項目）**。cdTab=703-2021 等で絞る（製造業表は cat01 だが商業表は tab）。
  - 産業は cat01（卸小売の細分類）。中分類は 52飲食料品卸売 / 58飲食料品小売 等のコードで直接指定可。
  - 従業者規模は cat02。**合計=0** を指定（規模別の重複を避ける）。
  - 都道府県は area（5桁・末尾000: 01000〜47000）。00000=全国、政令市(01100等)は除外。
  - **1件だけ返ると VALUE が list でなく dict** になる（e-Stat定番罠）→ 正規化。
  - 検算: 47都道府県合計 == 全国計。
  - 調査年(2021)と販売額の実績年(2020)はズレる（年間商品販売額=2020暦年）。
"""
import os, sys, csv, json, argparse, hashlib, datetime
from pathlib import Path
import httpx

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
# 経済センサス活動調査2021「都道府県別…産業分類細分類別…年間商品販売額及び売場面積」
# ★調査年(census)が変わったら更新。探し方は recipe.md。tab/コードも census 年依存。
CENSUS_YEAR = "2021"
SALES_REFERENCE_YEAR = "2020"
MEASURES = {   # エイリアス -> tab コード（2021センサス共通）
    "事業所数":   "701-2021",
    "従業者数":   "723-2021",
    "販売額":     "703-2021",   # 年間商品販売額【百万円】
    "売場面積":   "704-2021",   # 小売業のみ有意
}
MEASURE_UNIT = {"事業所数": "事業所", "従業者数": "人", "販売額": "百万円", "売場面積": "m2"}

# ★地理レベルで別表。製造業と同じ罠（タイトル類似・市区町村名で検索すると当たる）。
# prefecture: cat02(従業者規模)あり→0を指定 / municipality: cat02なし。
LEVELS = {
    "prefecture":   {"stats_id": "0004003257", "has_size": True},   # 全国+47+政令市(area70)
    "municipality": {"stats_id": "0004003263", "has_size": False},  # 全市区町村(area1137・町村含む)
}


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
    for _ in range(retries):
        try:
            r = httpx.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
    raise DataFetchError("e-Stat", url, "http", f"{endpoint} failed: {last}")


def vlist(sd):
    """VALUE は1件だと dict, 複数だと list になる（e-Stat定番罠）。常に list に正規化。"""
    v = sd["DATA_INF"]["VALUE"]
    return v if isinstance(v, list) else [v]


def industry_map(stats_id, app_id):
    d = get_json("getMetaInfo", {"appId": app_id, "statsDataId": stats_id})
    for c in d["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]:
        if c["@id"] == "cat01":
            objs = c["CLASS"]; objs = [objs] if isinstance(objs, dict) else objs
            return [(o["@code"], o["@name"]) for o in objs]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="prefecture", choices=list(LEVELS),
                    help="prefecture=都道府県(+政令市,0004003257) / municipality=全市区町村(0004003263)")
    ap.add_argument("--industry", default="52",
                    help="産業分類コード(例 52飲食料品卸売/58飲食料品小売/I1卸売業計) または名称部分一致")
    ap.add_argument("--measure", default="販売額", choices=list(MEASURES))
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
    is_muni = (a.level == "municipality")

    inds = industry_map(stats_id, app_id)
    if a.list_industries:
        print(f"[level={a.level} statsId={stats_id}] 利用可能 産業分類（{len(inds)}件, コード:名称）:")
        for code, name in inds:
            print(f"   {code}\t{name}")
        return 0

    code = None
    for c, n in inds:
        if c == a.industry:
            code, ind_name = c, n; break
    if code is None:
        for c, n in inds:
            if a.industry in n:
                code, ind_name = c, n; break
    if code is None:
        print(f"産業 '{a.industry}' に一致なし。--list-industries で確認を。", file=sys.stderr); return 2

    cd_tab = MEASURES[a.measure]
    # ★ tab=指標, cat01=産業。都道府県表は cat02(規模)=0 を指定、市区町村表は cat02 なし。
    params = {"appId": app_id, "statsDataId": stats_id, "cdTab": cd_tab, "cdCat01": code, "limit": "3000"}
    if lv["has_size"]:
        params["cdCat02"] = "0"
    sd = get_json("getStatsData", params)["GET_STATS_DATA"]["STATISTICAL_DATA"]

    amap = {}
    for c in sd["CLASS_INF"]["CLASS_OBJ"]:
        if c["@id"] == "area":
            objs = c["CLASS"]; objs = [objs] if isinstance(objs, dict) else objs
            amap = {o["@code"]: o["@name"] for o in objs}

    rows, national, suppressed = [], None, 0
    for v in vlist(sd):
        area = v.get("@area", "")
        name = amap.get(area, area)
        try:
            amt = float(v["$"])
        except (TypeError, ValueError, KeyError):
            if area.isdigit() and len(area) == 5:
                suppressed += 1
            continue
        if area == "00000":
            national = amt; continue
        if not (area.isdigit() and len(area) == 5):   # 英字集計(区部/市部/郡部 等)を除外
            continue
        if is_muni:
            if area.endswith("000"):                  # 都道府県計を除外
                continue
            if name == "特別区部":                    # 東京集計を除外（個別の特別区を採用）
                continue
            if name.endswith("区") and "市" in name:   # 政令市の区を除外（"○○市△区"。特別区"中央区"等は残す）
                continue
        else:
            if not (area.endswith("000") and 1 <= int(area[:2]) <= 47):  # 都道府県のみ
                continue
        rows.append((area, name, amt))
    rows.sort(key=lambda x: x[2], reverse=True)

    total = sum(x[2] for x in rows)
    verified = (not is_muni) and (national is not None) and abs(total - national) / national < 0.005
    unit = MEASURE_UNIT[a.measure]

    outdir = Path(a.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")
    yr = SALES_REFERENCE_YEAR if a.measure == "販売額" else CENSUS_YEAR
    stem = f"{today}_estat_commerce_{a.level}_{a.measure}_{ind_name}_{yr}"
    csv_path = outdir / f"{stem}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "area_code", "area", f"value_{unit}"])
        for i, (acode, name, amt) in enumerate(rows, 1):
            w.writerow([i, acode, name, int(amt)])

    meta = {
        "task_name": f"経済センサス活動調査 商業 {a.level} {ind_name} {a.measure}",
        "source": {"name": "総務省・経済産業省 経済センサス‐活動調査（卸売業・小売業）",
                   "via": "e-Stat API getStatsData", "stats_data_id": stats_id, "single_source": True},
        "query": {"level": a.level, "industry": f"{code} {ind_name}", "measure": a.measure, "tab_code": cd_tab,
                  "size_class": "合計(cat02=0)" if lv["has_size"] else "なし", "census_year": CENSUS_YEAR,
                  "sales_reference_year": yr,
                  "area": "全市区町村(政令市の区は除外/東京特別区は残す)" if is_muni else "都道府県47(政令市除外)"},
        "units": unit, "fetched_at": datetime.datetime.now().astimezone().isoformat(),
        "csv_sha256": sha256_of(csv_path),
        "row_count_areas": len(rows), "suppressed_or_missing": suppressed,
        "national_total": national, "sum_of_areas": total,
        "verification_sum_equals_national": verified,
        "gotchas": "指標はtab(cdTab)。産業はcat01。都道府県表はcat02=0(規模合計)・市区町村表はcat02なし。"
                   "地理レベルで別表(都道府県0004003257/市区町村0004003263)＝市区町村名で検索すると当たる。"
                   "市区町村は政令市区除外＋秘匿で47=全国検算は不成立。VALUE単一はdict→list正規化。調査年2021≠販売額実績2020。",
    }
    meta_path = outdir / f"{stem}_metadata.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    div = 100 if unit == "百万円" else 1
    label = "億円" if unit == "百万円" else unit
    print(f"# [{a.level}] {ind_name} {a.measure}（{yr}年・経済センサス活動調査{CENSUS_YEAR} {stats_id}）単位:{label}")
    n = a.top_n or len(rows)
    for i, (acode, name, amt) in enumerate(rows[:n], 1):
        print(f"{i:2}. {name:12} {amt/div:>12,.0f}")
    if is_muni:
        print(f"対象{len(rows)}市区町村・秘匿/欠損{suppressed}・全国計={(national or 0)/div:,.0f}{label}")
    else:
        print(f"検算: 47都道府県合計={total/div:,.0f} / 全国計={(national or 0)/div:,.0f} "
              f"-> {'OK 一致' if verified else 'NG 不一致'}")
    print(f"saved: {csv_path}\n       {meta_path}")
    return 0 if (verified or is_muni) else 1


if __name__ == "__main__":
    sys.exit(main())
