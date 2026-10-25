"""fetch.py — 気象庁 内蔵20都市 年降雪量／最深積雪 ランキング取得（etrn スクレイプ）

気象庁 etrn(annually_s.php) の各都市ページをスクレイプし、指定した寒候年の
年合計降雪量（または最深積雪）で都市をランキングして CSV + metadata.json に出力する。

使い方:
    # 2024寒候年(2023年8月〜2024年7月)の年降雪量ランキング 上位15
    python fetch.py --year 2024 --top-n 15 --output-dir ./output

    # 最深積雪でランキング
    python fetch.py --year 2024 --metric maxsnow --output-dir ./output

このレシピが扱う範囲:
- 内蔵20都市（雪国中心に手で選んだ都市。全国の順位ではない）× 単一寒候年 × 降雪量/最深積雪 ランキング（認証不要・HTMLスクレイプ）

このレシピが扱わない範囲:
- 1都市の長期時系列 → 別レシピ（未作成）
- AMeDAS 全観測点 → 別レシピ（observation point が桁違いに多い）
- 平年値 → JMA AMeDAS normals 系の別レシピ
"""
from __future__ import annotations  # py3.9 で PEP604 `X | None` 注釈を使うため

import argparse
import csv
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ETRN_URL = "https://www.data.jma.go.jp/stats/etrn/view/annually_s.php"

# 都市キー -> (block_no/WMO, prec_no, 日本語表示名)。雪国中心＋対照の大都市（手で選んだ20都市）。
# ★この20都市は全国の都市・観測点の代表ではない。順位は「内蔵20都市の中の順位」（出力の Scope に書く）。
# block_no/prec_no は 2026-10-26 に etrn の地点ページ（地点名の表示）で20都市すべて照合済み。
CITY_TABLE: dict[str, tuple[str, str, str]] = {
    "sapporo":   ("47412", "14", "札幌"),
    "asahikawa": ("47407", "12", "旭川"),
    "wakkanai":  ("47401", "11", "稚内"),
    "abashiri":  ("47409", "17", "網走"),
    "obihiro":   ("47417", "20", "帯広"),
    "kushiro":   ("47418", "19", "釧路"),
    "hakodate":  ("47430", "23", "函館"),
    "aomori":    ("47575", "31", "青森"),
    "akita":     ("47582", "32", "秋田"),  # 2026-10-26 修正: 以前は仙台の番号(47590/34)で、秋田として仙台を取っていた
    "morioka":   ("47584", "33", "盛岡"),
    "yamagata":  ("47588", "35", "山形"),
    "fukushima": ("47595", "36", "福島"),
    "sendai":    ("47590", "34", "仙台"),
    "niigata":   ("47604", "54", "新潟"),
    "toyama":    ("47607", "55", "富山"),
    "kanazawa":  ("47605", "56", "金沢"),
    "fukui":     ("47616", "57", "福井"),
    "nagano":    ("47610", "48", "長野"),
    "tokyo":     ("47662", "44", "東京"),
    "osaka":     ("47772", "62", "大阪"),
}
assert len({v[:2] for v in CITY_TABLE.values()}) == len(CITY_TABLE), "地点番号の重複"

DEFAULT_CITIES = list(CITY_TABLE.keys())
METRIC_LABEL = {"snowfall": "年降雪量合計", "maxsnow": "最深積雪"}
# 値欄の記号（気象庁「値欄の記号の説明」 https://www.data.jma.go.jp/stats/data/mdrr/man/remark.html）
#   --  該当現象、または該当現象による量等がない → 降雪なし＝0 として扱う
#   )   準正常値（資料の欠けが許容範囲）→ 正常値と同等に使う
#   ]   資料不足値 → 値は信用できない。順位から外し、外したことを出力に残す
#   ×  欠測 / ///  欠測または観測していない / 空白  観測していない → 値なし
CACHE_VERSION = 2

class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source, self.url, self.kind, self.original = source, url, kind, original


def _strip_tags(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw).replace("&nbsp;", " ").strip()


def parse_value(raw: str) -> tuple[float | None, str]:
    """セル1つを (値, 記号) にする。記号は "" / ")" / "]" / "--" / "×" / "///" / "空白" / "解析不能"。"""
    t = _strip_tags(raw).replace(",", "").strip()
    if t == "":
        return None, "空白"
    if t == "--":
        return 0.0, "--"
    if t in ("×", "///"):
        return None, t
    flag = ""
    if t[-1] in ")]":
        flag, t = t[-1], t[:-1].strip()
    try:
        return float(t), flag
    except ValueError:
        return None, "解析不能"


def header_paths(html: str) -> list[str]:
    """表の見出し（rowspan/colspan つき3段）を、<td> の列 index ごとの「親/子/孫」に展開する。

    見出しの <th> を並び順に数えた index は、<td> の列 index と一致しない（colspan があるため）。
    2026-10-26 確認: 旧版は <th> の index で最深積雪を探し、td の 22列目（降雪の日合計の最大）を読んでいた。
    """
    m = re.search(r'<table[^>]*id="tablefix1"[^>]*>(.*?)</table>', html, re.S)
    if not m:
        raise ValueError("表 tablefix1 が見つからない")
    grid: dict[tuple[int, int], str] = {}
    n_rows = 0
    for r, tr in enumerate(re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S)):
        ths = re.findall(r"<th([^>]*)>(.*?)</th>", tr, re.S)
        if not ths:
            break
        n_rows = r + 1
        c = 0
        for attrs, body in ths:
            while (r, c) in grid:
                c += 1
            rs = int((re.search(r'rowspan="?(\d+)', attrs) or [0, 1])[1])
            cs = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1])
            label = _strip_tags(body).replace("　", " ")
            for dr in range(rs):
                for dc in range(cs):
                    grid[(r + dr, c + dc)] = label
            c += cs
    n_cols = max(c for _, c in grid) + 1
    holes = [(r, c) for r in range(n_rows) for c in range(n_cols) if (r, c) not in grid]
    if holes:  # 見出しの段ごとの列数が合わない＝見出しの構造が変わった
        raise ValueError(f"見出しに欠けがある（段,列）: {holes[:5]}")
    paths = []
    for c in range(n_cols):
        parts = []
        for r in range(n_rows):
            lab = grid.get((r, c), "")
            if lab and (not parts or parts[-1] != lab):
                parts.append(lab)
        paths.append("/".join(parts))
    return paths


def find_col(paths: list[str], parent: str, tail: list[str]) -> int | None:
    """親見出しが parent で始まり、末尾の見出しが tail と一致する列の index。複数当たれば止める。

    部分一致にしない（「降雪」「合計」の部分一致だと「降雪/日合計の最大」にも当たる）。
    """
    hits = [i for i, h in enumerate(paths)
            if h.split("/")[0].startswith(parent) and h.split("/")[-len(tail):] == tail]
    if len(hits) > 1:
        raise ValueError(f"列が一意に決まらない {tail}: {[paths[i] for i in hits]}")
    return hits[0] if hits else None


def parse_city_page(html: str) -> dict:
    """annually_s.php の HTML から {"columns": {...}, "data": {year: {...}}} を抽出。

    列は見出しを展開して名前で探す。見つからなければ止める（固定 index に落とさない）。
    2026-10-26 に内蔵20都市すべてで取得し、見出しは同じ並び（td 28列、
    降雪の合計=21列目・最深積雪=23列目、親見出しは「雪(寒候年・cm)」）だった。
    """
    paths = header_paths(html)
    col_snow = find_col(paths, "雪(寒候年", ["降雪", "合計"])
    col_maxsnow = find_col(paths, "雪(寒候年", ["最深積雪"])
    if col_snow is None or col_maxsnow is None:
        raise ValueError(f"降雪の列が見つからない（見出し: {paths}）")

    out: dict[int, dict] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
        if tds and re.match(r"^\d{4}$", _strip_tags(tds[0])):
            if len(tds) != len(paths):
                raise ValueError(f"行の列数 {len(tds)} が見出しの列数 {len(paths)} と違う")
            yr = int(_strip_tags(tds[0]))
            snow, fs = parse_value(tds[col_snow])
            mx, fm = parse_value(tds[col_maxsnow])
            out[yr] = {"snowfall": snow, "snowfall_flag": fs,
                       "maxsnow": mx, "maxsnow_flag": fm}
    return {"columns": {"snowfall": [col_snow, paths[col_snow]],
                        "maxsnow": [col_maxsnow, paths[col_maxsnow]]},
            "data": out}


def station_label(html: str) -> str:
    """ページの見出し（例「秋田（秋田県)　年ごとの値　主な要素」）から地点名の部分を返す。"""
    m = re.search(r"<h3[^>]*>(.*?)</h3>", html, re.S)
    return _strip_tags(m.group(1)).split("\u3000")[0] if m else ""


def fetch_city(key: str, cache_dir: Path, retries: int = 3, refresh: bool = False) -> dict:
    """1都市分を取得（キャッシュ優先）。{"fetched_at","url","columns","data"} を返す。

    キャッシュには取得時刻・URL・列の検出結果を残す。旧形式（取得時刻なし）のキャッシュは取り直す。
    """
    cache_path = cache_dir / f"{key}.json"
    block_no, prec_no, _name = CITY_TABLE[key]
    url = f"{ETRN_URL}?prec_no={prec_no}&block_no={block_no}"
    if cache_path.exists() and not refresh:
        c = json.loads(cache_path.read_text(encoding="utf-8"))
        if c.get("cache_version") == CACHE_VERSION and c.get("url") == url:
            c["data"] = {int(k): v for k, v in c["data"].items()}
            c["from_cache"] = True
            return c
        logging.info("%s: 旧形式または別地点のキャッシュなので取り直す", key)
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as cl:
                r = cl.get(url, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
            break
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("%s retry %d/%d: %s", key, i + 1, retries, e)
    else:
        raise DataFetchError(source="JMA etrn", url=url, kind="FETCH_FAIL",
                             message=f"{key} failed after {retries} attempts",
                             original=last_err)
    label = station_label(r.text)
    if not label.startswith(_name + "（"):  # 地点番号の取り違え（旧版の秋田＝仙台）を止める
        raise DataFetchError(source="JMA etrn", url=url, kind="WRONG_STATION",
                             message=f"{key}: ページの地点は「{label}」で「{_name}」ではない")
    try:
        parsed = parse_city_page(r.text)
    except ValueError as e:
        raise DataFetchError(source="JMA etrn", url=url, kind="PARSE_FAIL",
                             message=f"{key}: {e}", original=e) from e
    rec = {"cache_version": CACHE_VERSION, "url": url, "station_label": label,
           "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
           **parsed}
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(rec, ensure_ascii=False),
                          encoding="utf-8", newline="\n")
    rec["from_cache"] = False
    return rec


def make_scope(keys: list[str], n_ranked: int, n_dropped: int) -> str:
    base = ("内蔵20都市（CITY_TABLE・雪国中心に手で選んだ都市）" if keys == DEFAULT_CITIES
            else f"指定の{len(keys)}都市")
    return (f"{base}のうち値が取れた{n_ranked}都市の中での順位"
            f"（落とした都市{n_dropped}）。全国の都市・全観測点の順位ではない")


def save_csv(ranked: list[dict], out_path: Path, *, metric: str, year: int, scope: str) -> None:
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Area", "CityKey", "Value", "Year", "Metric", "Unit", "Flag", "Scope"])
        for r in ranked:
            w.writerow([r["rank"], r["name"], r["key"], r["value"], year,
                        METRIC_LABEL[metric], "cm", r["flag"], scope])


def save_metadata(meta_path: Path, *, year: int, metric: str, top_n: int,
                  out_csv: Path, row_count: int, keys: list[str], scope: str,
                  n_ranked: int, dropped: list[dict], invalid_keys: list[str],
                  fetch_log: list[dict]) -> dict:
    import hashlib
    times = sorted(f["fetched_at"] for f in fetch_log)
    meta = {
        "task_name": f"jma_snowfall_{metric}_{year}_top{top_n}",
        "source": {"name": "気象庁 etrn (annually_s.php)", "url": ETRN_URL,
                   "single_source": True},
        "query": {"year_kansetsu": year, "metric": metric, "top_n": top_n,
                  "cities_queried": keys, "n_cities_queried": len(keys),
                  "invalid_city_keys": invalid_keys},
        "scope": scope,
        "n_ranked_cities": n_ranked,
        "dropped_cities": dropped,
        "n_dropped_cities": len(dropped),
        "units": "cm",
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_fetched_at_range": [times[0], times[-1]] if times else None,
        "per_city_fetch": fetch_log,
        "csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "row_count": row_count,
        "missing_value_treatment": (
            "気象庁の値欄の記号に従う: '--'(該当現象なし)=0、')'(準正常値)=値を使う、"
            "']'(資料不足値)・'×'・'///'・空白=順位から外し dropped_cities に記録"),
        "notes": ("降雪は寒候年（前年8月〜当年7月）の値。表の見出し「雪(寒候年・cm)」で確認。"
                  "値の単位は cm。"),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return meta


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="気象庁 内蔵20都市 降雪量ランキング取得")
    ap.add_argument("--year", type=int, default=2024,
                    help="寒候年（前年8月〜当年7月）。default 2024")
    ap.add_argument("--metric", default="snowfall", choices=["snowfall", "maxsnow"],
                    help="snowfall=年降雪量合計 / maxsnow=最深積雪")
    ap.add_argument("--top-n", type=int, default=15, help="上位N (default 15)")
    ap.add_argument("--cities", default=None,
                    help="都市キーをカンマ区切り（省略時は内蔵20都市）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / ".cache" / "jma_snow")
    ap.add_argument("--refresh", action="store_true", help="キャッシュを使わず取り直す")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="都市間の待機秒（礼儀。default 0）")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    req = ([c.strip().lower() for c in args.cities.split(",")]
           if args.cities else DEFAULT_CITIES)
    invalid = [k for k in req if k not in CITY_TABLE]
    if invalid:
        logging.error("未対応の都市キー %s。対応: %s", invalid, ", ".join(CITY_TABLE))
        return 1
    keys = req

    rows, dropped, fetch_log = [], [], []
    for key in keys:
        name = CITY_TABLE[key][2]
        try:
            c = fetch_city(key, args.cache_dir, refresh=args.refresh)
        except DataFetchError as e:
            if e.kind in ("WRONG_STATION", "PARSE_FAIL"):  # 表の誤り・ページ改修は全体を止める
                logging.error("%s", e)
                return 1
            logging.warning("取得失敗 %s: %s", key, e)
            dropped.append({"key": key, "name": name, "reason": f"{e.kind}: {e}"})
            continue
        fetch_log.append({"key": key, "url": c["url"], "fetched_at": c["fetched_at"],
                          "from_cache": c["from_cache"], "column": c["columns"][args.metric]})
        if not c["from_cache"] and args.sleep:
            time.sleep(args.sleep)
        rec = c["data"].get(args.year)
        if not rec:
            dropped.append({"key": key, "name": name, "reason": f"{args.year}年の行が無い"})
            continue
        val, flag = rec[args.metric], rec[f"{args.metric}_flag"]
        if val is None or flag == "]":
            dropped.append({"key": key, "name": name,
                            "reason": f"値なし（記号 {flag}）" if val is None
                            else f"資料不足値 ']'（{val}）"})
            continue
        rows.append({"key": key, "name": name, "value": val, "flag": flag})
    for d in dropped:
        logging.warning("順位から外した %s: %s", d["name"], d["reason"])

    if not rows:
        logging.error("%d 寒候年のデータが取得できませんでした", args.year)
        return 1

    rows.sort(key=lambda x: x["value"], reverse=True)
    ranked = [{**r, "rank": i} for i, r in enumerate(rows[:args.top_n], 1)]
    scope = make_scope(keys, len(rows), len(dropped))

    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_jma_snowfall_{args.metric}_{args.year}_top{args.top_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"
    save_csv(ranked, out_csv, metric=args.metric, year=args.year, scope=scope)
    meta = save_metadata(out_meta, year=args.year, metric=args.metric,
                         top_n=args.top_n, out_csv=out_csv, row_count=len(ranked),
                         keys=keys, scope=scope, n_ranked=len(rows), dropped=dropped,
                         invalid_keys=invalid, fetch_log=fetch_log)
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(ranked), meta["csv_sha256"][:12])

    print(f"\n== 気象庁 {METRIC_LABEL[args.metric]} {args.year}寒候年 Top {len(ranked)} ==")
    print(f"   範囲: {scope}")
    for r in ranked:
        print(f"  {r['rank']:>3}  {r['name']:<6}  {r['value']:>7.0f}cm {r['flag']}")
    if dropped:
        print("   外した都市: " + "、".join(f"{d['name']}（{d['reason']}）" for d in dropped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
