#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — JNTO「年別 訪日外客数・出国日本人数の推移」を1964年から取得。

出典: 日本政府観光局(JNTO) の公開PDF「年別 訪日外客数、出国日本人数の推移(1964年-)」。
★『世界国勢図会』など二次資料は近年だけのことが多いが、JNTO原典は**1964年まで**揃う。
  1971年に出国>訪日へ逆転、2015年に訪日>出国へ再逆転、という長期の物語を1枚で示せる。

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
    rows, year, nums = [], None, []
    for t in toks:
        if re.fullmatch(r"(19|20)\d{2}", t) and 1964 <= int(t) <= 2100:
            if year and len(nums) >= 2:
                rows.append((year, nums[0], nums[1]))
            year, nums = int(t), []
        elif year and is_comma_num(t):
            nums.append(int(t.replace(",", "")))
    if year and len(nums) >= 2:
        rows.append((year, nums[0], nums[1]))
    rows.sort()
    if len(rows) < 30 or rows[0][0] != 1964:
        raise DataFetchError(f"パース異常（{len(rows)}行, 先頭{rows[:1]}）。PDF様式変更を確認。")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tmp = args.output_dir / "_jnto.pdf"
    try:
        req = urllib.request.Request(args.url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            tmp.write_bytes(r.read())
    except (urllib.error.URLError, TimeoutError) as e:
        raise DataFetchError(f"DL失敗: {e}（JNTO統計ページで最新URLを確認）")

    rows = parse(tmp)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    out = args.output_dir / f"{today}_jnto_inbound_outbound.csv"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f)
        w.writerow(["year", "visitor_arrivals", "japanese_overseas"])
        w.writerows(rows)
    meta = {"source": "日本政府観光局(JNTO) 年別 訪日外客数・出国日本人数の推移",
            "url": args.url, "unit": "人", "year_range": f"{rows[0][0]}-{rows[-1][0]}",
            "row_count": len(rows), "csv_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "retrieved_at": datetime.now(JST).isoformat()}
    (args.output_dir / f"{today}_jnto_inbound_outbound_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.unlink(missing_ok=True)
    cross = [y for (y, a, o), (_, a2, o2) in zip(rows, rows[1:]) if (a > o) != (a2 > o2)]
    print(f"saved: {out.name}  ({rows[0][0]}-{rows[-1][0]}, {len(rows)}行)")
    print(f"訪日↔出国の逆転年: {cross}  （1971=出国超え, 2015=訪日超え が要所）")


if __name__ == "__main__":
    main()
