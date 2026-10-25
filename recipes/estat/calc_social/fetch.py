"""fetch.py — e-Stat 都道府県別 社会増加率（人口増加率 − 自然増加率）取得

e-Stat 社会・人口統計体系から、都道府県別の「人口増加率(A192003)」と
「自然増加率(A4401)」を取得し、その差＝社会増加率（≒人口の社会移動）を計算して
降順ランキングを CSV + metadata.json に出力する。

社会増加率 = 人口増加率 − 自然増加率
（自然増加＝出生−死亡、社会増加＝転入−転出。正なら転入超過＝人口流入）

使い方:
    export ESTAT_APP_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    python fetch.py --time 2024100000 --output-dir ./output

このレシピが扱う範囲:
- 都道府県別 社会増加率（2指標差分）の計算とランキング（要 ESTAT_APP_ID）

このレシピが扱わない範囲:
- 単一指標の取得・階級分類 → 別レシピ `estat/prefecture_classify`
- 統計表検索 → 別レシピ `estat/search`
- 市区町村レベル → 本レシピは都道府県のみ
"""
import argparse
import csv as _csv
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ESTAT_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
STATS_ID = "0000010101"          # 社会・人口統計体系
CAT_POP = "A192003"              # 人口増加率
CAT_NATURAL = "A4401"            # 自然増加率


class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source, self.url, self.kind, self.original = source, url, kind, original


def load_api_key() -> str:
    """環境変数 ESTAT_APP_ID → ~/.env の順で読む。"""
    key = os.environ.get("ESTAT_APP_ID", "")
    if key:
        return key
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ESTAT_APP_ID="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise DataFetchError(
        source="e-Stat", url="(env)", kind="MISSING_KEY",
        message="ESTAT_APP_ID が未設定。環境変数または ~/.env に設定してください。")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_estat(api_key: str, cd_cat01: str, cd_time: str,
                *, retries: int = 3, timeout: int = 60) -> dict:
    """getStatsData を叩いて STATISTICAL_DATA を返す。appId はログに出さない。"""
    params = {
        "appId": api_key, "statsDataId": STATS_ID,
        "metaGetFlg": "Y", "cntGetFlg": "N", "replaceSpChars": "2",
        "cdCat01": cd_cat01, "limit": "20000",
    }
    if cd_time:
        params["cdTime"] = cd_time
    url = f"{ESTAT_BASE}/getStatsData"
    safe_url = url + f"?statsDataId={STATS_ID}&cdCat01={cd_cat01}&cdTime={cd_time}&appId=***"
    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout) as cl:
                r = cl.get(url, params=params)
                r.raise_for_status()
                data = r.json().get("GET_STATS_DATA", {})
                status = data.get("RESULT", {}).get("STATUS")
                if status != 0:
                    raise DataFetchError(
                        source="e-Stat", url=safe_url, kind="API_ERROR",
                        message=str(data.get("RESULT", {}).get("ERROR_MSG", "unknown")))
                sd = data.get("STATISTICAL_DATA", {})
                # limit 超過時は RESULT_INF.NEXT_KEY が付き、残りは返らない。黙って欠けないよう止める
                ri = sd.get("RESULT_INF", {}) or {}
                if ri.get("NEXT_KEY"):
                    raise DataFetchError(
                        source="e-Stat", url=safe_url, kind="TRUNCATED",
                        message=f"limit 超過（TOTAL_NUMBER={ri.get('TOTAL_NUMBER')}）。取得が途中で切れている")
                return sd
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("fetch retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError(source="e-Stat", url=safe_url, kind="HTTP_FAIL",
                         message=f"failed after {retries} attempts", original=last_err)


def build_area_map(sd: dict) -> dict:
    """CLASS_INF から area code → 都道府県名。名前先頭の【番号】を除去。"""
    area_map = {}
    for obj in sd.get("CLASS_INF", {}).get("CLASS_OBJ", []) or []:
        if isinstance(obj, dict) and obj.get("@id") == "area":
            cls = obj.get("CLASS", [])
            if isinstance(cls, dict):
                cls = [cls]
            for c in cls:
                area_map[c.get("@code", "")] = re.sub(
                    r"^【\d+】", "", c.get("@name", "")).strip()
            break
    return area_map


def is_prefecture(code: str) -> bool:
    """5桁・末尾000・全国(00000)でない＝都道府県。"""
    return len(code) == 5 and code.endswith("000") and code != "00000"


def values_by_pref(sd: dict) -> tuple[dict, str, list]:
    """都道府県別 {area code: value}・単位・数値化できなかった area code を返す。
    突き合わせは名前でなく area code で行う（表記ゆれで黙って落ちないように）。"""
    values = sd.get("DATA_INF", {}).get("VALUE", [])
    if isinstance(values, dict):
        values = [values]
    out, unit, non_numeric = {}, "", []
    for v in values:
        code = v.get("@area", "")
        if not is_prefecture(code):
            continue
        try:
            num = float(str(v.get("$", "")).replace(",", ""))
        except (ValueError, TypeError):
            non_numeric.append(code)
            continue
        out[code] = num
        unit = v.get("@unit", "") or unit
    return out, unit, non_numeric


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="e-Stat 都道府県 社会増加率（人口増加率−自然増加率）")
    ap.add_argument("--time", default="2024100000", help="cdTime (default 2024100000)")
    ap.add_argument("--top-n", type=int, default=0, help="上位N (0=全47都道府県)")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    # httpx は INFO で appId 入り URL を出すため抑止
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        api_key = load_api_key()
        logging.info("人口増加率(A192003) 取得")
        sd_pop = fetch_estat(api_key, CAT_POP, args.time)
        logging.info("自然増加率(A4401) 取得")
        sd_nat = fetch_estat(api_key, CAT_NATURAL, args.time)
    except DataFetchError as e:
        logging.error("取得失敗: %s", e)
        return 1

    area_map = {**build_area_map(sd_nat), **build_area_map(sd_pop)}
    pop, unit, nn_pop = values_by_pref(sd_pop)
    nat, unit_nat, nn_nat = values_by_pref(sd_nat)
    if unit and unit_nat and unit != unit_nat:
        logging.error("2指標の単位が違う: 人口増加率=%s / 自然増加率=%s", unit, unit_nat)
        return 1

    # 両指標が揃う都道府県のみ社会増加率を計算（area code で突き合わせる）
    rows = []
    for code in sorted(pop):
        if code in nat:
            rows.append({"code": code, "area": area_map.get(code, code),
                         "social": round(pop[code] - nat[code], 2),
                         "pop": pop[code], "natural": nat[code]})
    # 片方しか無い・数値でない県は落とすが、数と名前を残す
    dropped = sorted((set(pop) ^ set(nat)) | set(nn_pop) | set(nn_nat))
    dropped_names = [area_map.get(c, c) for c in dropped]
    n_computed = len(rows)
    if not rows:
        logging.error("両指標が揃う都道府県がありません（time=%s を確認）", args.time)
        return 1
    if n_computed != 47:
        logging.warning("計算できた都道府県は %d 件（47ではない）。落とした県: %s",
                        n_computed, "、".join(dropped_names) or "なし")
    rows.sort(key=lambda r: r["social"], reverse=True)
    if args.top_n > 0:
        rows = rows[:args.top_n]
        scope = f"計算できた{n_computed}都道府県の中での上位{len(rows)}件のみ"
    else:
        scope = f"計算できた{n_computed}都道府県すべて" + ("" if n_computed == 47 else "（47に満たない）")

    year = args.time[:4]
    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_estat_social_increase_{year}" + (f"_top{args.top_n}" if args.top_n > 0 else "")
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    with open(out_csv, "w", encoding="utf-8", newline="\n") as f:
        w = _csv.writer(f)
        w.writerow(["Rank", "Area", "Value", "PopIncrease", "NaturalIncrease",
                    "Year", "Unit"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["area"], r["social"], r["pop"], r["natural"],
                        year, unit])

    meta = {
        "task_name": f"estat_social_increase_{year}",
        "source": {"name": "e-Stat 社会・人口統計体系",
                   "api_endpoint": f"{ESTAT_BASE}/getStatsData",
                   "stats_data_id": STATS_ID, "single_source": True},
        "query": {"cd_cat01_pop": CAT_POP, "cd_cat01_natural": CAT_NATURAL,
                  "cd_time": args.time, "top_n": args.top_n},
        "formula": "社会増加率 = 人口増加率(A192003) − 自然増加率(A4401)",
        "units": unit,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "row_count": len(rows),
        "scope": scope,
        "pref_expected": 47,
        "pref_computed": n_computed,
        "dropped_prefectures": dropped_names,
        "notes": ("社会増加率＝人口増加率−自然増加率の差（転入超過の目安。転入−転出の統計値そのものではない）。"
                  "都道府県のみ(area 5桁末尾000)。2指標は area code で突き合わせ、"
                  "片方が欠ける県は除外して dropped_prefectures に記録。"
                  "appId はログ・metadata に出さない。"),
    }
    out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    logging.info("出力: %s (%d都道府県, sha256=%s…)",
                 out_csv.name, len(rows), meta["csv_sha256"][:12])

    print(f"\n== 都道府県 社会増加率 {year} (人口増加率−自然増加率) Top/Bottom ==")
    for r in rows[:5]:
        print(f"  {r['area']:<6}  社会{r['social']:>6.2f}{unit}  "
              f"(人口{r['pop']:+.2f} − 自然{r['natural']:+.2f})")
    print("  …")
    for r in rows[-3:]:
        print(f"  {r['area']:<6}  社会{r['social']:>6.2f}{unit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
