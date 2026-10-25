#!/usr/bin/env python3
"""国勢調査 小地域集計（町丁・字等別）を1市区町村ぶん取り、末端の地域だけの CSV + metadata を出力。境界も取れる。

使い方:
  python fetch.py --find 産業 --pref 愛知県                                      # ファイル番号を探す（要 ESTAT_APP_ID）
  python fetch.py --stat-inf-id 000032210330 --city 23214 --boundary            # 第11表（産業大分類）愛知県 → 蒲郡市
  python fetch.py --stat-inf-id 000032210330 --city 23214 --cols 0_総数,R1_,R2_,R3_,T_
  python fetch.py --stat-inf-id 000032210330 --list-cols                        # 表の列見出しを列挙

勝ちパターン（重要・recipe.md 参照）:
  - 小地域集計は統計表の検索（getStatsList）に出てこない。**都道府県×表ごとのファイル**を statInfId で直接落とす（cp932）。
    番号は**データカタログの検索（getDataCatalog）なら出る**（--find）。
  - 1つの地域に **総数・男・女の3行**がある。男女の列で「総数」だけを取る。
  - **地域階層レベル3は、レベル4（字・丁目）の合計**。末端＝レベル2（丁目の無い町）＋レベル4。全部足すと二重になる。
  - 秘匿地域（X）の人数は**隣の地域に合算済み**。推測で埋めない。末端の合計＝市区町村の計で検算できる。
    ★**合算先がレベル3（親）のことがある**（丁目がすべて秘匿のとき）。その親の行を落とすと計が合わない。
  - 列は**見出しのコード（0_総数・R1_ 等）で選ぶ**。位置は表ごとに違う。
  - 境界は KEY_CODE＝市区町村コード＋町丁字コード。**同じ KEY_CODE が2行（飛び地）**あるので dissolve。HCODE 8154 は水面。
"""
import os, sys, csv, json, time, argparse, hashlib, datetime, zipfile, io
from pathlib import Path
import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_URL = "https://www.e-stat.go.jp/stat-search/file-download?statInfId={sid}&fileKind=1"
# 令和2年国勢調査 町丁・字等別境界データ（世界測地系緯度経度・Shapefile）。平成27年は A002005212015
SHP_URL = ("https://www.e-stat.go.jp/gis/statmap-search/data?dlserveyId={survey}"
           "&code={city}&coordSys=1&format=shape&downloadType=5")
# 列の並び（ファイルの4行目の見出し）
C_SEX, C_CITY, C_CODE, C_LEVEL, C_SECRET, C_TARGET, C_MERGED = 1, 2, 3, 4, 5, 6, 7
C_CITYNAME, C_OAZA, C_AZA = 9, 10, 11


CATALOG = "https://api.e-stat.go.jp/rest/3.0/app/json/getDataCatalog"


class DataFetchError(Exception):
    pass


def app_id():
    v = os.environ.get("ESTAT_APP_ID")
    if v:
        return v
    env = Path(__file__).resolve().parents[4] / ".env"
    if env.exists():
        for l in env.read_text(encoding="utf-8").splitlines():
            if l.startswith("ESTAT_APP_ID="):
                return l.split("=", 1)[1].strip()
    sys.exit("ESTAT_APP_ID が無い（.env か環境変数）。--find だけに要る")


def as_list(x):
    return x if isinstance(x, list) else [x]


def find(word, pref, year):
    """データカタログを「小地域 AND 語 AND 都道府県」で引き、ファイル番号と表題を並べる。"""
    q = {"appId": app_id(), "statsCode": "00200521", "surveyYears": year, "limit": "100",
         "searchWord": " AND ".join(w for w in ("小地域", word, pref) if w)}
    r = httpx.get(CATALOG, params=q, timeout=120).json()["GET_DATA_CATALOG"]
    # ★キーの認証に失敗しても応答は返り、件数が無いだけになる。黙って「0件」と出していた
    #   （2026-10-25 配布物の試験で、仮のキーのまま試した AI が見つけた）。STATUS を見て止める
    res = r.get("RESULT", {})
    if str(res.get("STATUS", "0")) != "0":
        raise DataFetchError(f"e-Stat API がエラーを返した（STATUS {res.get('STATUS')}）: {res.get('ERROR_MSG')}。"
                             "ESTAT_APP_ID が正しいか確かめる。ファイル番号が分かっていれば --stat-inf-id で先に進める")
    hits = []
    for c in as_list(r.get("DATA_CATALOG_LIST_INF", {}).get("DATA_CATALOG_INF", [])):
        for x in as_list(c["RESOURCES"]["RESOURCE"]):
            t = x["TITLE"]
            name = t.get("NAME", "") if isinstance(t, dict) else str(t)
            sid = x.get("URL", "").split("statInfId=")[-1].split("&")[0]
            hits.append((sid, name))
    return hits


def download(url):
    for i in range(3):
        try:
            r = httpx.get(url, timeout=180, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return r.content
        except httpx.HTTPError as e:
            if i == 2:
                raise DataFetchError(f"取得に失敗: {url} ({e})")
            time.sleep(3 * (i + 1))


def num(v):
    """'-' は0、'X' は秘匿（None）、空欄も None。0と秘匿を区別する。"""
    v = v.strip()
    if v == "-":
        return 0
    if v in ("X", ""):
        return None
    try:
        return int(v.replace(",", ""))
    except ValueError:
        return float(v.replace(",", "")) if _is_float(v) else _bad(v)


def _is_float(v):
    try:
        float(v.replace(",", ""))
        return True
    except ValueError:
        return False


def _bad(v):
    raise ValueError(f"数値でない値 {v!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat-inf-id", help="都道府県×表のファイル番号（--find で探す）")
    ap.add_argument("--find", help="表題の語でファイル番号を探す（例 産業・年齢・世帯）")
    ap.add_argument("--pref", help="--find の都道府県（例 愛知県）")
    ap.add_argument("--year", default="2020", help="--find の調査年")
    ap.add_argument("--city", help="市区町村コード5桁（例 23214 蒲郡市）")
    ap.add_argument("--cols", default=None, help="取る列の見出しコードの頭（カンマ区切り）。未指定なら全列")
    ap.add_argument("--list-cols", action="store_true")
    ap.add_argument("--boundary", action="store_true", help="境界 Shapefile も取る")
    ap.add_argument("--survey", default="A002005212020", help="境界の調査ID（令和2年＝A002005212020）")
    ap.add_argument("--output-dir", default=".")
    ap.add_argument("--raw-dir", default=None,
                    help="落とした都道府県のファイルをそのまま残す場所（例 data/raw/estat）。約束「取ったデータは data に置く」用")
    a = ap.parse_args()

    if a.find:
        hits = find(a.find, a.pref, a.year)
        for sid, name in hits:
            print(sid, name)
        print(f"{len(hits)}件" + ("（0件なら語を短くする。表題は「男女，産業（大分類）別…」の形）" if not hits else ""))
        return 0
    if not a.stat_inf_id:
        sys.exit("--stat-inf-id が要る（番号は --find で探す）")

    raw = download(CSV_URL.format(sid=a.stat_inf_id))
    # ★元のファイルを残す（2026-10-25 配布物の試験で、2体とも自分で手直しして足していた）
    if a.raw_dir:
        rd = Path(a.raw_dir); rd.mkdir(parents=True, exist_ok=True)
        rp = rd / f"{datetime.datetime.now():%Y%m%d}_estat_{a.stat_inf_id}_raw.csv"
        if rp.exists() and rp.read_bytes() != raw:   # 同じ日に中身の違うファイルを上書きしない
            rp = rp.with_name(f"{datetime.datetime.now():%Y%m%d_%H%M%S}_estat_{a.stat_inf_id}_raw.csv")
        if not rp.exists():
            rp.write_bytes(raw)
    rows = list(csv.reader(raw.decode("cp932", errors="replace").splitlines()))
    title = rows[1][1].strip() if len(rows) > 1 else ""
    hi = next((i for i, r in enumerate(rows) if len(r) > C_CODE and r[C_CODE] == "町丁字コード"), None)
    if hi is None:
        raise DataFetchError("見出しの行（町丁字コード）が見つからない。小地域集計のファイルか確かめる")
    head = rows[hi]
    first = head.index(next(h for h in head[C_AZA + 1:] if h))
    if a.list_cols:
        print(title)
        for j in range(first, len(head)):
            print(f"  {head[j]}")
        return 0
    if not a.city:
        sys.exit("--city が要る（--list-cols 以外）")

    if a.cols:
        want = [p.strip() for p in a.cols.split(",") if p.strip()]
        cols = []
        for p in want:
            hit = [j for j in range(first, len(head)) if head[j].startswith(p)]
            if len(hit) != 1:
                sys.exit(f"列 {p} が {len(hit)} 本当たる（--list-cols で見出しを確かめる）")
            cols.append(hit[0])
    else:
        cols = list(range(first, len(head)))
    names = [head[j] for j in cols]

    body = [r for r in rows[hi + 1:] if len(r) == len(head) and r[C_CITY] == a.city and r[C_SEX] == "総数"]
    if not body:
        raise DataFetchError(f"市区町村 {a.city} の行が無い（都道府県が違うファイルかもしれない）")
    city = [r for r in body if r[C_LEVEL] == "1"]
    if len(city) != 1:
        raise DataFetchError(f"市区町村の計（レベル1）が {len(city)} 行")
    city = city[0]
    leaf = [r for r in body if r[C_LEVEL] in ("2", "4")]
    # ★秘匿の合算先がレベル3（親）のことがある。丁目がすべて秘匿だと、人数は親の行にだけ残る
    #   （新潟市中央区の美咲町：一・二丁目がともに X、1,200人は「美咲町」の行）。その親は末端と並べて取る。
    targets = {r[C_TARGET] for r in leaf if r[C_SECRET] == "秘匿地域"}
    parents = [r for r in body if r[C_LEVEL] == "3" and r[C_CODE] in targets]

    out = []
    for r in leaf + parents:
        v = []
        for j in cols:
            try:
                v.append(num(r[j]))
            except ValueError as e:
                raise DataFetchError(f"列「{head[j]}」の地域 {r[C_CODE]} に{e}。人数でない列（平均など）は --cols で外す")
        if any(isinstance(x, float) for x in v):
            bad = [head[j] for j, x in zip(cols, v) if isinstance(x, float)]
            raise DataFetchError(f"小数の値がある列: {bad}（人数の列ではない。--list-cols で確かめ --cols で外す）")
        if r[C_LEVEL] == "3":
            status = "merged_parent"
            covers = ";".join(a.city + x[C_CODE] for x in leaf if x[C_TARGET] == r[C_CODE])
        else:
            xs = [r[j].strip() == "X" for j in cols]
            # 先頭の列だけで秘匿を決めない。全列 X＝secret、一部の列だけ X＝partial_secret（X の列は空欄で合計から外れる）
            status = "secret" if all(xs) else ("partial_secret" if any(xs) else "ok")
            covers = ""
        out.append([a.city + r[C_CODE], r[C_LEVEL], r[C_OAZA], r[C_AZA], status,
                    r[C_TARGET] if status == "secret" else "", covers, *("" if x is None else x for x in v)])

    # 検算: 末端（秘匿を除く）の合計 ＝ 市区町村の計。秘匿の人数は合算先に入っているので一致するはず
    checks = {}
    for k, j in enumerate(cols):
        total = num(city[j])
        s = sum(o[7 + k] for o in out if o[4] in ("ok", "partial_secret", "merged_parent") and o[7 + k] != "")
        checks[names[k]] = {"city": total, "sum_of_leaves": s, "match": total == s}
    verified = all(c["match"] for c in checks.values())

    outdir = Path(a.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now().strftime("%Y%m%d")
    stem = f"{today}_estat_small_area_{a.stat_inf_id}_{a.city}"
    csv_path = outdir / f"{stem}.csv"
    # 境界は CSV・metadata を書く前に取る（境界で落ちたとき、境界の無い成果物だけが残らないように）
    shp = None
    if a.boundary:
        z = download(SHP_URL.format(survey=a.survey, city=a.city))
        bad = zipfile.ZipFile(io.BytesIO(z)).testzip()
        if bad:
            raise DataFetchError(f"境界の zip が壊れている（{bad}）")
        shp = (Path(a.raw_dir) if a.raw_dir else outdir) / f"{today}_estat_boundary_{a.city}.zip"
        shp.parent.mkdir(parents=True, exist_ok=True)
        shp.write_bytes(z)
    with csv_path.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["key_code", "level", "oaza", "aza", "status", "secret_merged_into", "merged_parent_covers", *names])
        w.writerows(out)

    m = {
        "task_name": "国勢調査 小地域集計（町丁・字等別）",
        "source": {"name": "総務省統計局 国勢調査 小地域集計", "table_title": title,
                   "stat_inf_id": a.stat_inf_id, "url": CSV_URL.format(sid=a.stat_inf_id), "single_source": True},
        "query": {"city": a.city, "city_name": city[C_CITYNAME], "columns": names},
        "units": "人（表による）",
        "leaf_rule": "地域階層レベル2（丁目の無い町）＋レベル4（字・丁目）。レベル3はレベル4の合計なので除く。"
                     "ただし秘匿の合算先になったレベル3は status=merged_parent として残す（merged_parent_covers の地域の人数を含む）",
        "fetched_at": datetime.datetime.now().astimezone().isoformat(),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "row_count": len(out),
        "n_secret": sum(1 for o in out if o[4] == "secret"),
        "n_partial_secret": sum(1 for o in out if o[4] == "partial_secret"),
        "n_merged_parent": len(parents),
        "missing_value_treatment": "'-' は0、'X'（秘匿）は空欄。秘匿の人数は secret_merged_into の地域に合算済み",
        "verification": checks,
        "verified": verified,
        "boundary": None if shp is None else {"file": shp.name, "url": SHP_URL.format(survey=a.survey, city=a.city),
                                             "note": "KEY_CODE で dissolve（飛び地）。HCODE 8154 は水面"},
    }
    meta_path = outdir / f"{stem}_metadata.json"
    meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"# {city[C_CITYNAME]}  {title}")
    print(f"末端 {len(out)}地域（レベル2={sum(1 for o in out if o[1]=='2')}・レベル4={sum(1 for o in out if o[1]=='4')}）"
          f" / 秘匿 {m['n_secret']}" + (f" / 親に合算 {len(parents)}" if parents else ""))
    for n, c in checks.items():
        print(f"  {n:24} 市計 {c['city']:>8,} / 末端の合計 {c['sum_of_leaves']:>8,}  {'OK' if c['match'] else 'NG'}")
    print(f"検算: {'OK' if verified else 'NG'}\nsaved: {csv_path}\n       {meta_path}" + (f"\n       {shp}" if shp else ""))
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())
