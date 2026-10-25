#!/usr/bin/env python3
"""e-Stat 人口推計「都道府県別自然増減率－総人口」を取得し、都道府県のランキング CSV + metadata を出力。

使い方:
  export ESTAT_APP_ID=...   # .env にあり
  python fetch.py --list-periods                         # 表にある期間を列挙
  python fetch.py                                        # 最新期間（例 2023年10月～2024年9月）
  python fetch.py --period 2021 --output-dir ./out       # 2021年10月～2022年9月
  python fetch.py --area 沖縄県                           # 1県の全期間の推移

勝ちパターン（重要・recipe.md 参照）:
  - 期間は**暦年でなく前年10月～当年9月**。「2024年」と書くと別の数字（人口動態統計の暦年）と取り違える。
  - 単位は**‰（人口千人当たり）**。％ではない。
  - 表は**国勢調査の基準ごとに別**（令和2年基準 0003448235 は2016年10月～）。毎年4月の公表で期間が1つ増える。
  - 検算: 47都道府県がそろい、全国（00000）があること。率なので合計の検算はできない。
"""
import os, sys, csv, json, argparse, hashlib, datetime
from pathlib import Path
import httpx

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
# 人口推計 各年10月1日現在人口 令和2年国勢調査基準「都道府県別自然増減率－総人口」
# ★次の基準（令和7年国勢調査）の表が出たら差し替える。探し方は recipe.md。
STATS_ID = "0003448235"


def app_id():
    v = os.environ.get("ESTAT_APP_ID")
    if v:
        return v
    env = Path(__file__).resolve().parents[4] / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if l.startswith("ESTAT_APP_ID="):
                return l.split("=", 1)[1].strip()
    sys.exit("ESTAT_APP_ID が無い（.env か環境変数）")


def get(ep, **q):
    q["appId"] = app_id()
    r = httpx.get(f"{BASE}/{ep}", params=q, timeout=120)
    r.raise_for_status()
    return r.json()


def as_list(x):
    return x if isinstance(x, list) else [x]


def sha256_of(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default=None, help="期間の始まりの年（2023 = 2023年10月～2024年9月）。未指定なら最新")
    ap.add_argument("--area", default=None, help="1県の全期間の推移を出す（例 沖縄県）")
    ap.add_argument("--stats-id", default=STATS_ID)
    ap.add_argument("--list-periods", action="store_true")
    ap.add_argument("--output-dir", default=".")
    a = ap.parse_args()

    meta = get("getMetaInfo", statsDataId=a.stats_id)["GET_META_INFO"]["METADATA_INF"]
    cls = {c["@id"]: as_list(c["CLASS"]) for c in as_list(meta["CLASS_INF"]["CLASS_OBJ"])}
    periods = [(c["@code"], c["@name"]) for c in cls["time"]]
    areas = {c["@code"]: c["@name"] for c in cls["area"]}
    if a.list_periods:
        for code, name in periods:
            print(code, name)
        return 0

    q = {"statsDataId": a.stats_id}
    if a.area:
        hit = [k for k, v in areas.items() if a.area in v]
        if not hit:
            sys.exit(f"{a.area} が表に無い")
        q["cdArea"] = ",".join(hit)
    else:
        code = periods[-1][0] if a.period is None else next(
            (c for c, n in periods if n.startswith(f"{a.period}年10月")), None)
        if code is None:
            sys.exit(f"{a.period}年10月～ の期間が表に無い（--list-periods）")
        q["cdTime"] = code
    d = get("getStatsData", **q)["GET_STATS_DATA"]["STATISTICAL_DATA"]
    vals = as_list(d["DATA_INF"]["VALUE"])
    unit = vals[0].get("@unit", "")
    pname = dict(periods)

    outdir = Path(a.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")
    if a.area:
        rows = [(pname[v["@time"]], float(v["$"])) for v in vals]
        stem = f"{today}_estat_natural_change_{areas[q['cdArea'].split(',')[0]]}"
        header = ["period", f"natural_change_rate_{unit}"]
        verified = len(rows) == len(periods)
    else:
        rows = sorted(((v["@area"], areas[v["@area"]], float(v["$"])) for v in vals if v["@area"] != "00000"),
                      key=lambda x: x[2], reverse=True)
        national = next((float(v["$"]) for v in vals if v["@area"] == "00000"), None)
        stem = f"{today}_estat_natural_change_pref_{pname[q['cdTime']][:7]}"
        header = ["rank", "area_code", "area", f"natural_change_rate_{unit}"]
        verified = len(rows) == 47 and national is not None
    csv_path = outdir / f"{stem}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for i, r in enumerate(rows, 1):
            w.writerow(list(r) if a.area else [i, *r])

    m = {
        "task_name": "人口推計 都道府県別自然増減率",
        "source": {"name": "総務省統計局 人口推計（各年10月1日現在人口）", "via": "e-Stat API getStatsData",
                   "stats_data_id": a.stats_id, "table_title": "都道府県別自然増減率－総人口",
                   "url": f"https://www.e-stat.go.jp/dbview?sid={a.stats_id}", "single_source": True},
        "query": {"period": None if a.area else pname[q["cdTime"]], "area": a.area or "47都道府県"},
        "units": unit,
        "period_note": "期間は前年10月1日～当年9月30日（暦年ではない）",
        "fetched_at": datetime.datetime.now().astimezone().isoformat(),
        "csv_sha256": sha256_of(csv_path),
        "row_count": len(rows),
        "verification": "47都道府県と全国がそろう" if not a.area else "全期間がそろう",
        "verified": verified,
        "available_periods": [n for _, n in periods],
    }
    if not a.area:
        m["national"] = national
        m["count_positive"] = sum(1 for r in rows if r[2] > 0)
    meta_path = outdir / f"{stem}_metadata.json"
    meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    if a.area:
        print(f"# {areas[q['cdArea'].split(',')[0]]} 自然増減率（{unit}）")
        for p, v in rows:
            print(f"  {p}  {v:+.1f}")
    else:
        print(f"# 都道府県別 自然増減率 {pname[q['cdTime']]}（{unit}）  全国 {national:+.1f}")
        for i, (code, area, v) in enumerate(rows, 1):
            print(f"{i:2}. {area:5} {v:+.1f}")
        print(f"プラスの都道府県 {m['count_positive']} / 47")
    print(f"検算: {'OK' if verified else 'NG'}（{m['verification']}）\nsaved: {csv_path}\n       {meta_path}")
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())
