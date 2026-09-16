"""fetch.py — e-Stat 都道府県統計 + 階級分類取得

e-Stat REST API から特定の統計データを取得し、都道府県別の値を
N階級分類した結果を CSV + metadata.json に保存する。

使い方:
    # 環境変数または .env に ESTAT_APP_ID を設定してから実行
    export ESTAT_APP_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

    # 人口増加率 2024年度 4階級分類
    python fetch.py \\
        --stats-id 0000010101 --cat01 A192003 --time 2024100000 \\
        --classify-n 4 --output-dir ./output

このレシピが扱う範囲:
- 都道府県別データの取得（mode=get 相当）
- N階級分類（教科書の階級区分図用）
- area code → 都道府県名のマッピング（CLASS_INF メタから取得）

このレシピが扱わない範囲:
- 統計表検索（mode=search）→ 別レシピ `estat/search`（未作成）
- 複合計算（人口増加率 - 自然増加率 = 社会増加率）→ 別レシピ `estat/calc_social`（未作成）
- 市区町村レベル → `--city-only` フラグで部分対応、別途専用レシピ推奨
"""
import argparse
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


class DataFetchError(Exception):
    """データ取得失敗時の構造化例外。"""

    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source = source
        self.url = url
        self.kind = kind
        self.original = original


def load_api_key() -> str:
    """環境変数 ESTAT_APP_ID → ~/.env の順で読む。"""
    key = os.environ.get("ESTAT_APP_ID", "")
    if key:
        return key
    # .env フォールバック
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ESTAT_APP_ID="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise DataFetchError(
        source="e-Stat", url="(env)", kind="MISSING_KEY",
        message=(
            "ESTAT_APP_ID が未設定。環境変数または ~/.env に設定してください。"
            " 取得: https://www.e-stat.go.jp/api/api-info/api-guide"
        ),
    )


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_estat(
    api_key: str, stats_data_id: str,
    *, cd_cat01: str = "", cd_cat02: str = "", cd_cat03: str = "",
    cd_tab: str = "", cd_area: str = "", cd_time: str = "",
    limit: int = 20000, retries: int = 3, timeout: int = 60,
) -> tuple[dict, str]:
    """e-Stat getStatsData を叩いて raw JSON を返す。

    Returns:
        (raw_data, request_url)
    """
    params = {
        "appId": api_key, "statsDataId": stats_data_id,
        "metaGetFlg": "Y", "cntGetFlg": "N",
        "explanationGetFlg": "N", "annotationGetFlg": "N",
        "replaceSpChars": "2", "limit": str(limit),
    }
    if cd_cat01: params["cdCat01"] = cd_cat01
    if cd_cat02: params["cdCat02"] = cd_cat02
    if cd_cat03: params["cdCat03"] = cd_cat03
    if cd_tab:   params["cdTab"]   = cd_tab
    if cd_area:  params["cdArea"]  = cd_area
    if cd_time:  params["cdTime"]  = cd_time

    url = f"{ESTAT_BASE}/getStatsData"
    # ログ用URL（appId はマスク）
    safe_url = url + "?" + "&".join(
        f"{k}={v if k != 'appId' else '***'}" for k, v in params.items()
    )

    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout) as cl:
                r = cl.get(url, params=params)
                r.raise_for_status()
                data = r.json().get("GET_STATS_DATA", {})
                result_info = data.get("RESULT", {})
                if result_info.get("STATUS") != 0:
                    raise DataFetchError(
                        source="e-Stat", url=safe_url, kind="API_ERROR",
                        message=str(result_info.get("ERROR_MSG", "unknown")),
                    )
                return data, safe_url
        except httpx.HTTPError as e:
            last_err = e
            logging.warning("fetch retry %d/%d: %s", i + 1, retries, e)

    raise DataFetchError(
        source="e-Stat", url=safe_url, kind="HTTP_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def build_area_map(sd: dict) -> dict:
    """CLASS_INF から area code → 都道府県名 のマッピングを構築。

    e-Stat の area code は5桁（例: 13000=東京都, 13101=千代田区）。
    名前先頭に【番号】が付くので除去。
    """
    area_map = {}
    for obj in sd.get("CLASS_INF", {}).get("CLASS_OBJ", []) or []:
        if not isinstance(obj, dict):
            continue
        if obj.get("@id") == "area":
            cls = obj.get("CLASS", [])
            if isinstance(cls, dict):
                cls = [cls]
            for c in cls:
                name = re.sub(r"^【\d+】", "", c.get("@name", "")).strip()
                area_map[c.get("@code", "")] = name
            break
    return area_map


def is_prefecture(code: str) -> bool:
    """都道府県コードか判定。5桁で末尾000で、かつ"00000"でない。"""
    if len(code) != 5 or not code.endswith("000"):
        return False
    if code == "00000":  # 全国
        return False
    return True


def is_city(code: str) -> bool:
    """市区町村レベルコード判定。
    5桁・末尾000でない・全国でない・東京都23区個別除外。
    """
    if len(code) != 5 or code.endswith("000") or code == "00000":
        return False
    if "13101" <= code <= "13123":  # 東京23区は市区町村ではない
        return False
    return True


def classify_into_n(values: list[tuple[str, float, str]], n_classes: int) -> list[dict]:
    """値を降順ソートし、N階級にほぼ均等分割する。

    Args:
        values: [(area_name, value, unit), ...]
        n_classes: 階級数（例: 4）

    Returns:
        [{class: 1, range_hi: ..., range_lo: ..., members: [...]}, ...]
    """
    sorted_vals = sorted(values, key=lambda x: x[1], reverse=True)
    n_total = len(sorted_vals)
    size = n_total // n_classes
    classes = []
    for i in range(n_classes):
        start = i * size
        end = start + size if i < n_classes - 1 else n_total
        group = sorted_vals[start:end]
        if not group:
            continue
        classes.append({
            "class": i + 1,
            "range_hi": group[0][1],
            "range_lo": group[-1][1],
            "count": len(group),
            "members": [
                {"area": name, "value": val, "unit": unit}
                for name, val, unit in group
            ],
        })
    return classes


def to_csv_rows(classes: list[dict]) -> list[dict]:
    """階級分類結果をフラットな CSV 行に展開。"""
    rows = []
    for cls in classes:
        for m in cls["members"]:
            rows.append({
                "class": cls["class"],
                "class_range_hi": cls["range_hi"],
                "class_range_lo": cls["range_lo"],
                "area": m["area"],
                "value": m["value"],
                "unit": m["unit"],
            })
    return rows


def save_csv(rows: list[dict], out_path: Path) -> None:
    import csv as _csv
    fieldnames = ["class", "class_range_hi", "class_range_lo", "area", "value", "unit"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def save_metadata(
    meta_path: Path, *, stats_data_id: str, cd_cat01: str, cd_time: str,
    classify_n: int, title: str, units: str, request_url: str,
    out_csv: Path, row_count: int, class_count: int,
) -> dict:
    meta = {
        "task_name": f"estat_{stats_data_id}_{cd_cat01}_{cd_time}_classify{classify_n}",
        "source": {
            "name": "e-Stat 政府統計の総合窓口",
            "url": "https://www.e-stat.go.jp/api/",
            "api_endpoint": f"{ESTAT_BASE}/getStatsData",
            "single_source": True,
        },
        "query": {
            "stats_data_id": stats_data_id,
            "cd_cat01": cd_cat01,
            "cd_time": cd_time,
            "classify_n": classify_n,
            "table_title": title,
            "request_url": request_url,
        },
        "units": units,
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "class_count": class_count,
        "missing_value_treatment": "公表値なしは行スキップ（推測補完なし）",
        "notes": (
            "都道府県別データを N階級分類（教材階級区分図用）。"
            "area code 5桁・末尾000のみ抽出（市区町村は --city-only オプション）。"
        ),
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(
        description="e-Stat 都道府県統計 + 階級分類取得",
    )
    ap.add_argument("--stats-id", required=True,
                    help="統計表ID (例: 0000010101=社会人口統計体系)")
    ap.add_argument("--cat01", default="", help="cdCat01 (例: A192003=人口増加率)")
    ap.add_argument("--cat02", default="", help="cdCat02")
    ap.add_argument("--cat03", default="", help="cdCat03")
    ap.add_argument("--tab", default="", help="cdTab")
    ap.add_argument("--area", default="", help="cdArea")
    ap.add_argument("--time", default="", help="cdTime (例: 2024100000)")
    ap.add_argument("--classify-n", type=int, default=4,
                    help="階級分類数 (default: 4, 0=分類しない)")
    ap.add_argument("--city-only", action="store_true",
                    help="市区町村レベルのみ取得（都道府県除外）")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"),
                    help="出力ディレクトリ")
    args = ap.parse_args()

    # Win cmd.exe (CP932) 対策
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    # httpx は INFO で URL（appId 含む）をフル出力するので抑止
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ─── APIキー読み込み ───
    try:
        api_key = load_api_key()
    except DataFetchError as e:
        logging.error("%s", e)
        return 1

    # ─── 取得 ───
    logging.info(
        "e-Stat取得: stats_id=%s cat01=%s time=%s classify_n=%d",
        args.stats_id, args.cat01, args.time, args.classify_n,
    )
    try:
        data, request_url = fetch_estat(
            api_key, args.stats_id,
            cd_cat01=args.cat01, cd_cat02=args.cat02, cd_cat03=args.cat03,
            cd_tab=args.tab, cd_area=args.area, cd_time=args.time,
        )
    except DataFetchError as e:
        logging.error("取得失敗: %s", e)
        return 1

    sd = data.get("STATISTICAL_DATA", {})
    area_map = build_area_map(sd)
    tbl_info = sd.get("TABLE_INF", {})
    title_obj = tbl_info.get("TITLE", {})
    title = title_obj.get("$", "") if isinstance(title_obj, dict) else str(title_obj)

    values = sd.get("DATA_INF", {}).get("VALUE", [])
    if isinstance(values, dict):
        values = [values]
    if not values:
        logging.error("データなし: %s", title)
        return 1

    # ─── area filter ───
    filter_fn = is_city if args.city_only else is_prefecture
    rows: list[tuple[str, float, str]] = []
    unit = ""
    for v in values:
        area_code = v.get("@area", "")
        if not filter_fn(area_code):
            continue
        try:
            num = float(str(v.get("$", "")).replace(",", ""))
        except (ValueError, TypeError):
            continue
        name = area_map.get(area_code, area_code)
        u = v.get("@unit", "")
        if u:
            unit = u
        rows.append((name, num, u))

    if not rows:
        logging.error(
            "フィルタ後データなし（city_only=%s, area_count=%d）",
            args.city_only, len(area_map),
        )
        return 1

    logging.info("対象エリア数: %d", len(rows))

    # ─── 階級分類 ───
    if args.classify_n > 0:
        classes = classify_into_n(rows, args.classify_n)
    else:
        # 分類しない: 全件を1クラスに
        classes = [{
            "class": 1, "range_hi": max(r[1] for r in rows),
            "range_lo": min(r[1] for r in rows), "count": len(rows),
            "members": [{"area": n, "value": v, "unit": u} for n, v, u in rows],
        }]

    csv_rows = to_csv_rows(classes)

    # ─── 出力 ───
    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_estat_{args.stats_id}_{args.cat01 or 'all'}_{args.time or 'latest'}_class{args.classify_n}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    save_csv(csv_rows, out_csv)
    meta = save_metadata(
        out_meta,
        stats_data_id=args.stats_id, cd_cat01=args.cat01, cd_time=args.time,
        classify_n=args.classify_n, title=title, units=unit,
        request_url=request_url, out_csv=out_csv,
        row_count=len(csv_rows), class_count=len(classes),
    )
    logging.info("出力: %s (%d rows, %d classes, sha256=%s…)",
                 out_csv, len(csv_rows), len(classes), meta["csv_sha256"][:12])
    logging.info("metadata: %s", out_meta)

    # ─── サマリ表示 ───
    print(f"\n== e-Stat: {title} ==")
    print(f"  対象数: {len(rows)} エリア / 階級数: {len(classes)}")
    print()
    for cls in classes:
        print(f"  【第{cls['class']}階級】 {cls['range_lo']:.1f} 〜 "
              f"{cls['range_hi']:.1f} {unit}  ({cls['count']}件)")
        for m in cls["members"][:5]:
            print(f"    {m['area']:<10}  {m['value']:>8.1f} {m['unit']}")
        if cls["count"] > 5:
            print(f"    ... 他 {cls['count'] - 5} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
