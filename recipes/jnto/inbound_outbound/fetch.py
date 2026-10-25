#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py ― JNTO「年別 訪日外客数・出国日本人数の推移」を1964年から取得。

出典: 日本政府観光局(JNTO) の公開PDF「年別 訪日外客数、出国日本人数の推移(1964年-)」。
★二次資料は収録期間が短いことがある。JNTO原典PDFは**1964年から**（2025-08版で1964〜2024年の61年）。
  大小の入れ替わりは 1971（出国>訪日）・2015（訪日>出国）・2021・2022（コロナ期）。

出力: <date>_jnto_inbound_outbound.csv （year, visitor_arrivals, japanese_overseas）＋ metadata.json

使い方:
    python fetch.py --output-dir ./output
    # PDF URL は JNTO 統計ページで毎年更新される。--url で差し替え可。
"""
import argparse, json, sys, io, csv, re, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request, urllib.error
import fitz  # PyMuPDF

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
# 年次更新でファイル名が変わる。最新URLは https://www.jnto.go.jp/statistics/data/ の
# 「年別 訪日外客数、出国日本人数の推移」リンクから取得すること。
DEFAULT_URL = "https://www.jnto.go.jp/statistics/data/_files/20250820_1615-8.pdf"


class DataFetchError(Exception):
    pass


def parse(pdf_path):
    """PDFテキストから year→(訪日, 出国) を抽出。
    ★各年ブロックは 年・和暦・訪日(カンマ数)・伸率・出国(カンマ数)・伸率 の順。
      伸率(15.5/△22.7 等)はカンマ無し → **カンマを含む数が訪日・出国**。和暦/伸率は読み飛ばす。"""
    text = "\n".join(p.get_text() for p in fitz.open(pdf_path))
    toks = [t.strip() for t in text.split("\n") if t.strip()]
    is_comma_num = lambda t: re.fullmatch(r"\d{1,3}(,\d{3})+", t)
    # ★単位: 見出しに「人」「persons」があること（千人・万人の版に変わったら止める）
    head = toks[:toks.index("1964")] if "1964" in toks else toks
    if "人" not in head or "persons" not in head:
        raise DataFetchError("見出しに単位「人」「persons」が無い。PDF様式・単位の変更を確認。")
    blocks, year, nums = [], None, []
    for t in toks:
        if re.fullmatch(r"(19|20)\d{2}", t) and 1964 <= int(t) <= 2100:
            if year:
                blocks.append((year, nums))
            year, nums = int(t), []
        elif year and is_comma_num(t):
            nums.append(int(t.replace(",", "")))
    if year:
        blocks.append((year, nums))
    # ★各年の「カンマを含む数」はちょうど2つ（訪日・出国）。違う年は黙って捨てずに止める
    odd = [(y, len(n)) for y, n in blocks if len(n) != 2]
    if odd:
        raise DataFetchError(f"カンマ付きの数が2つでない年がある {odd}（年, 個数）。PDF様式変更を確認。")
    rows = sorted((y, n[0], n[1]) for y, n in blocks)
    ys = [r[0] for r in rows]
    if len(ys) != len(set(ys)):
        raise DataFetchError(f"同じ年が2回出た: {sorted({y for y in ys if ys.count(y) > 1})}")
    gaps = sorted(set(range(1964, ys[-1] + 1)) - set(ys)) if ys else []
    if len(rows) < 30 or rows[0][0] != 1964 or gaps:
        raise DataFetchError(f"パース異常（{len(rows)}行, 先頭{rows[:1]}, 欠けた年{gaps}）。PDF様式変更を確認。")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    today = now.strftime("%Y%m%d")
    # 読み取り元のPDFは消さずに残す（あとから検算できるように）
    tmp = args.output_dir / f"{today}_jnto_inbound_outbound_source.pdf"
    try:
        req = urllib.request.Request(args.url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            tmp.write_bytes(r.read())
    except (urllib.error.URLError, TimeoutError) as e:
        raise DataFetchError(f"DL失敗: {e}（JNTO統計ページで最新URLを確認）")

    rows = parse(tmp)
    out = args.output_dir / f"{today}_jnto_inbound_outbound.csv"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["year", "visitor_arrivals", "japanese_overseas"])
        w.writerows(rows)
    meta = {"source": "日本政府観光局(JNTO) 年別 訪日外客数・出国日本人数の推移",
            "url": args.url, "unit": "人（PDF見出しの「人」「persons」を確認済み）",
            "year_range": f"{rows[0][0]}-{rows[-1][0]}",
            "scope": f"全国の年計・{rows[0][0]}〜{rows[-1][0]}年の全年（欠けた年なし）",
            "row_count": len(rows), "csv_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "source_pdf": tmp.name, "source_pdf_sha256": hashlib.sha256(tmp.read_bytes()).hexdigest(),
            "retrieved_at": now.isoformat()}
    (args.output_dir / f"{today}_jnto_inbound_outbound_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    # 大小が前年と入れ替わった年（入れ替わった後の年を出す）。同数の年は無い（1964〜2024で確認）
    cross = [y2 for (y, a, o), (y2, a2, o2) in zip(rows, rows[1:]) if (a > o) != (a2 > o2)]
    print(f"saved: {out.name}  ({rows[0][0]}-{rows[-1][0]}, {len(rows)}行)")
    print(f"訪日⇔出国の大小が入れ替わった年: {cross}  （1964〜2024 では 1971・2015・2021・2022）")


if __name__ == "__main__":
    main()
