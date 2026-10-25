"""fetch.py — World Bank Indicators API 国別指標取得

World Bank Indicators API V2 から、指定インジケータを指定国群について
取得し、最新値ランキング or 時系列を CSV + metadata.json に保存する。

使い方:
    # GDP (current US$) の上位30か国ランキング（集計地域を除く全ての国・地域の中で）
    python fetch.py --indicator NY.GDP.MKTP.CD --mode ranking --top-n 30 \\
        --all-countries --output-dir ./output

    # 日本/韓国/中国の人口時系列 (2000-2023)
    python fetch.py --indicator SP.POP.TOTL --mode trend \\
        --countries JPN,KOR,CHN --year-from 2000 --output-dir ./output

このレシピが扱う範囲:
- 単一インジケータ × 国群 × ranking or trend
- 既定は手で並べた49か国（世界順位ではない）。--all-countries で集計地域を除く全ての国・地域
- ranking では集計地域（WLD・EUU・所得階層など。国メタデータの region が Aggregates）を必ず除く
- 認証不要（公開API）

このレシピが扱わない範囲:
- 複数インジケータ同時取得 → 別レシピ
- 地域・所得階級別の集計 → 別レシピ
- "country" に Region/IncomeGroup を含む → 本レシピは個別国のみ
"""
import argparse
import csv
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


# ─── 定数 ───
WB_BASE = "https://api.worldbank.org/v2"

# ranking モード時のデフォルト国群（手で並べた 49 か国、ISO3）。**世界順位ではない**。
# 世界順位が要るときは --all-countries。どちらで並べたかは出力の scope に出る。
# TWN（台湾）は値が返らない（page=0/total=0）ので外している。2026-05-23 に TWN を含む一括で
# 4xx を観測したが、2026-10-26 の再試行では 200 OK で再現しなかった（recipe.md ハマり所11）。
DEFAULT_COUNTRIES = [
    "USA", "CHN", "JPN", "DEU", "IND", "GBR", "FRA", "ITA", "CAN", "BRA",
    "RUS", "KOR", "AUS", "ESP", "MEX", "IDN", "NLD", "TUR", "CHE", "SAU",
    "POL", "ARG", "SWE", "BEL", "THA", "IRL", "ISR", "NOR", "AUT",
    "EGY", "ZAF", "PHL", "DNK", "BGD", "VNM", "MYS", "SGP", "HKG", "ARE",
    "COL", "PAK", "CHL", "FIN", "ROU", "CZE", "PRT", "GRC", "NZL", "KEN",
]


class DataFetchError(Exception):
    def __init__(self, source: str, url: str, kind: str, message: str, original=None):
        super().__init__(f"[{source}] {kind}: {message}")
        self.source = source
        self.url = url
        self.kind = kind
        self.original = original


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_wb_indicator(
    indicator: str, countries: list[str],
    *, mrv: int = 10, retries: int = 3, timeout: int = 60,
) -> tuple[list, str]:
    """World Bank Indicators API を叩いて値配列を返す。

    Returns:
        (data_rows, request_url)
        data_rows: [{"countryiso3code": "JPN", "date": "2023", "value": 4.2e12, ...}, ...]

    World Bank API の特殊な仕様:
    - レスポンスは **2要素配列** `[meta, data]`
    - data[0] = メタデータ（page, total等）
    - data[1] = 実際の値配列
    - 1要素しか無い場合はエラー（指標 or 国コード誤り）
    """
    cc_str = ";".join(countries)
    url = f"{WB_BASE}/country/{cc_str}/indicator/{indicator}"

    def _get_page(cl, page):
        # per_page は上限側に大きく取り、さらに pages を辿って全ページ結合する
        params = {"format": "json", "mrv": str(mrv), "per_page": "1000", "page": str(page)}
        r = cl.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or len(data) < 2:
            raise DataFetchError(
                source="World Bank", url=url, kind="UNEXPECTED_RESPONSE",
                message=f"expected [meta, data] but got: {str(data)[:200]}",
            )
        return data[0] or {}, (data[1] or [])

    last_err = None
    for i in range(retries):
        try:
            with httpx.Client(timeout=timeout) as cl:
                meta, rows = _get_page(cl, 1)
                pages = int(meta.get("pages") or 1)
                for p in range(2, pages + 1):        # ★2ページ目以降も取得（500件超の欠落防止）
                    _m, more = _get_page(cl, p)
                    rows.extend(more)
            # ★完全性チェック: 取得件数が API メタの total 未満なら黙って欠落させず失敗させる
            total = int(meta.get("total") or len(rows))
            if len(rows) < total:
                raise DataFetchError(
                    source="World Bank", url=url, kind="INCOMPLETE_PAGING",
                    message=f"ページング未完: 取得 {len(rows)} 件 < total {total} 件",
                )
            return rows, url
        except (httpx.HTTPError, DataFetchError) as e:
            # WB は 200 でエラーボディ(id=120)を一時的に返すことがある＝リトライで回復する。
            last_err = e
            logging.warning("fetch retry %d/%d: %s", i + 1, retries, e)

    # リトライ尽き: DataFetchError は実際の種別のまま再送出（HTTP_FAIL で覆い隠さない）
    if isinstance(last_err, DataFetchError):
        raise last_err
    raise DataFetchError(
        source="World Bank", url=url, kind="HTTP_FAIL",
        message=f"failed after {retries} attempts", original=last_err,
    )


def fetch_aggregate_codes(*, retries: int = 3, timeout: int = 60) -> tuple[set[str], int, str]:
    """World Bank の国メタデータから集計地域（region が Aggregates）の ISO3 を返す。

    Returns: (集計地域の ISO3 集合, 集計でない国・地域の数, request_url)
    取れなければ DataFetchError（集計地域を除けないまま順位を出さない）。
    """
    url = f"{WB_BASE}/country"
    last_err = None
    for i in range(retries):
        try:
            r = httpx.get(url, params={"format": "json", "per_page": "1000"}, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or len(data) < 2 or not data[1]:
                raise DataFetchError("World Bank", url, "UNEXPECTED_RESPONSE", str(data)[:200])
            meta, rows = data
            if int(meta.get("total") or 0) != len(rows):
                raise DataFetchError("World Bank", url, "INCOMPLETE_PAGING",
                                     f"国メタデータ {len(rows)} 件 < total {meta.get('total')}")
            agg = {c["id"] for c in rows if (c.get("region") or {}).get("value", "").strip() == "Aggregates"}
            return agg, len(rows) - len(agg), url
        except (httpx.HTTPError, DataFetchError, ValueError) as e:
            last_err = e
            logging.warning("country metadata retry %d/%d: %s", i + 1, retries, e)
    raise DataFetchError("World Bank", url, "HTTP_FAIL",
                         f"国メタデータを取得できない（集計地域を除けない）: {last_err}")


def latest_per_country(rows: list[dict]) -> dict[str, dict]:
    """各国の最新非null値を抽出。

    返る順序には頼らない（null も混じる）。国ごとに年を比べて最新の非null を取る。
    """
    by_cc: dict[str, dict] = {}
    for r in rows:
        if r.get("value") is None:
            continue
        cc = r.get("countryiso3code", "")
        if not cc:
            continue
        yr = int(r.get("date", "0"))
        if cc not in by_cc or yr > int(by_cc[cc].get("date", "0")):
            by_cc[cc] = r
    return by_cc


def build_ranking(
    by_cc: dict[str, dict], top_n: int, indicator_name: str, scope: str = "",
) -> list[dict]:
    rows = []
    sorted_items = sorted(
        by_cc.values(), key=lambda r: float(r.get("value", 0) or 0),
        reverse=True,
    )
    for rank, r in enumerate(sorted_items[:top_n], 1):
        country = r.get("country", {}) if isinstance(r.get("country"), dict) else {}
        rows.append({
            "rank": rank,
            "iso3": r.get("countryiso3code", ""),
            "country": country.get("value", "") if country else r.get("country", ""),
            "year": r.get("date", ""),
            "value": r.get("value"),
            "indicator": r.get("indicator", {}).get("id", "") if isinstance(r.get("indicator"), dict) else indicator_name,
            "scope": scope,
        })
    return rows


def build_trend(
    raw_rows: list[dict], year_from: int,
) -> list[dict]:
    """時系列モード: 国×年 で1行ずつ展開。"""
    out = []
    for r in raw_rows:
        if r.get("value") is None:
            continue
        try:
            yr = int(r.get("date", "0"))
        except ValueError:
            continue
        if yr < year_from:
            continue
        country = r.get("country", {}) if isinstance(r.get("country"), dict) else {}
        out.append({
            "iso3": r.get("countryiso3code", ""),
            "country": country.get("value", "") if country else "",
            "year": yr,
            "value": r.get("value"),
        })
    out.sort(key=lambda x: (x["iso3"], x["year"]))
    return out


def save_csv(rows: list[dict], out_path: Path) -> None:
    if not rows:
        return
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


def save_metadata(
    meta_path: Path, *, indicator: str, mode: str, countries: list[str],
    mrv: int, request_url: str, out_csv: Path, row_count: int,
    extra: dict | None = None,
) -> dict:
    meta = {
        "task_name": f"wb_{indicator}_{mode}_{datetime.now().strftime('%Y%m%d')}",
        "source": {
            "name": "World Bank Indicators API V2",
            "url": WB_BASE,
            "request_url": request_url,
            "single_source": True,
        },
        "query": {
            "indicator": indicator,
            "mode": mode,
            "countries": countries,
            "country_count": len(countries),
            "mrv": mrv,
        },
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "csv_sha256": sha256_of(out_csv),
        "csv_size_bytes": out_csv.stat().st_size,
        "row_count": row_count,
        "missing_value_treatment": "value=null は除外（推測補完なし）",
        "notes": (
            "World Bank API は data[1] が値配列、data[0] はメタ。"
            "ranking は各国の最新非null年の値で並べる。国ごとに年が違うことがある"
            "（year_min / year_max と CSV の year 列を確認）。"
        ),
    }
    if extra:
        meta.update(extra)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(
        description="World Bank Indicators 国別取得",
    )
    ap.add_argument("--indicator", required=True,
                    help="WB インジケータコード (例: NY.GDP.MKTP.CD=GDP, SP.POP.TOTL=人口)")
    ap.add_argument("--mode", default="ranking", choices=["ranking", "trend"],
                    help="ranking=最新値順位 / trend=国×年時系列")
    ap.add_argument("--countries", default="",
                    help="ISO3 カンマ区切り (例: JPN,USA,CHN). 省略時は既定49か国（世界順位ではない）")
    ap.add_argument("--all-countries", action="store_true",
                    help="集計地域を除く全ての国・地域で取る（ranking を世界順位にするとき）")
    ap.add_argument("--top-n", type=int, default=30,
                    help="ranking モードの上位N (default: 30)")
    ap.add_argument("--year-from", type=int, default=2000,
                    help="trend モードの開始年 (default: 2000)")
    ap.add_argument("--mrv", type=int, default=10,
                    help="Most Recent Values の取得年数 (default: 10)。trend では --year-from から今年までの年数に自動で広げる")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"),
                    help="出力ディレクトリ")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.all_countries and args.countries:
        ap.error("--all-countries と --countries は同時に使えない")
    if args.all_countries:
        countries = ["all"]
        scope_kind = "all"
    elif args.countries:
        countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
        scope_kind = "given"
    else:
        countries = DEFAULT_COUNTRIES
        scope_kind = "default"
    mrv = max(args.mrv, (datetime.now().year - args.year_from + 1)
              if args.mode == "trend" else args.mrv)

    logging.info(
        "WB取得: indicator=%s mode=%s countries=%d mrv=%d",
        args.indicator, args.mode, len(countries), mrv,
    )
    try:
        raw_rows, request_url = fetch_wb_indicator(
            args.indicator, countries, mrv=mrv,
        )
    except DataFetchError as e:
        logging.error("取得失敗: %s", e)
        return 1

    if not raw_rows:
        logging.error(
            "データなし。インジケータコード or 国コードを確認してください。",
        )
        return 1
    logging.info("生レコード: %d 件", len(raw_rows))

    extra: dict = {}
    if args.mode == "ranking":
        try:
            agg_codes, n_economies, _u = fetch_aggregate_codes()
        except DataFetchError as e:
            logging.error("取得失敗: %s", e)
            return 1
        by_cc = latest_per_country(raw_rows)
        # ISO3 が空の行（所得階層の集計 High income 等は countryiso3code="" で返る）は順位に入らない。数を残す
        no_iso3 = sorted({(r.get("country") or {}).get("value", "?") for r in raw_rows
                          if not r.get("countryiso3code")})
        if no_iso3:
            logging.warning("ISO3 が空の行（集計）を除外: %s", no_iso3)
        dropped = sorted(cc for cc in by_cc if cc in agg_codes)
        for cc in dropped:
            del by_cc[cc]
        if dropped:
            logging.warning("集計地域を順位から除外: %d 件 %s", len(dropped),
                            dropped if len(dropped) <= 20 else dropped[:20] + ["…"])
        n = len(by_cc)
        if scope_kind == "all":
            scope = f"集計地域を除く全{n_economies}か国・地域の中での順位（値のある{n}か国・地域）"
        elif scope_kind == "default":
            scope = f"既定{len(DEFAULT_COUNTRIES)}か国の中での順位（世界順位ではない。値のある{n}か国）"
        else:
            scope = f"指定した{len(countries)}か国の中での順位（値のある{n}か国）"
        no_value = sorted(set(countries) - set(by_cc) - set(dropped)) if scope_kind != "all" else []
        if args.top_n > n:
            logging.warning("--top-n %d は母集団 %d か国より大きい（出力は %d 行）", args.top_n, n, n)
        out_rows = build_ranking(by_cc, args.top_n, args.indicator, scope=scope)
        years = [int(r["year"]) for r in out_rows]
        extra = {
            "scope": scope,
            "n_ranked": n,
            "dropped_aggregates": dropped,
            "dropped_rows_without_iso3": no_iso3,
            "countries_without_value": no_value,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
        }
        logging.info("各国最新値: %d か国（%s）", n, scope)
        if years and min(years) != max(years):
            logging.warning("順位の中で年が揃っていない: %d〜%d 年", min(years), max(years))
    else:  # trend
        out_rows = build_trend(raw_rows, args.year_from)
        logging.info("時系列レコード: %d 行", len(out_rows))

    if not out_rows:
        logging.error("出力データなし")
        return 1

    today = datetime.now().strftime("%Y%m%d")
    slug = f"{today}_wb_{args.indicator.replace('.', '_')}_{args.mode}"
    out_csv = args.output_dir / f"{slug}.csv"
    out_meta = args.output_dir / f"{slug}_metadata.json"

    save_csv(out_rows, out_csv)
    meta = save_metadata(
        out_meta, indicator=args.indicator, mode=args.mode, countries=countries,
        mrv=mrv, request_url=request_url, out_csv=out_csv,
        row_count=len(out_rows), extra=extra,
    )
    logging.info("出力: %s (%d rows, sha256=%s…)",
                 out_csv, len(out_rows), meta["csv_sha256"][:12])

    # サマリ表示
    if args.mode == "ranking":
        print(f"\n== World Bank {args.indicator} Top {min(args.top_n, len(out_rows))} — {extra['scope']} ==")
        for r in out_rows[:min(20, len(out_rows))]:
            val = r["value"]
            v_str = f"{val:>18,.0f}" if val and val > 100 else f"{val:>18.3f}"
            print(f"  {r['rank']:>3}  {r['iso3']:<4} {r['country']:<25}  "
                  f"{v_str}  ({r['year']})")
    else:
        print(f"\n== World Bank {args.indicator} trend (since {args.year_from}) ==")
        # 国別に最初の3点だけ表示
        from collections import defaultdict
        by_country = defaultdict(list)
        for r in out_rows:
            by_country[r["iso3"]].append(r)
        for cc, rows in by_country.items():
            print(f"  [{cc}] {rows[0]['country']}: {len(rows)} 年分")
            for r in rows[:3]:
                print(f"    {r['year']}: {r['value']:,.0f}" if r['value'] else f"    {r['year']}: -")
            if len(rows) > 3:
                print(f"    ... (他 {len(rows)-3} 年)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
