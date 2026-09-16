---
id: jnto/inbound_outbound
api: jnto
task: 訪日外客数・出国日本人数の長期推移
items: [訪日外客数, 出国日本人数]
tags: [jnto, tourism, inbound, outbound, timeseries, pdf-parse, japan, no-auth]
summary: JNTOの公開PDFから訪日外客数・出国日本人数を1964年から取得（観光の長期推移グラフ用）
pattern: pdf-download + text-parse
auth_required: false
verified_at: 2026-06-13
complexity: easy
gotcha_count: 4
---

# jnto / inbound_outbound

## 何をする
日本政府観光局(JNTO)の公開PDF「年別 訪日外客数、出国日本人数の推移」から、**1964年〜最新年**の
2系列を取得しCSV化する。観光（インバウンド/アウトバウンド）の長期推移グラフ・正誤設問に使う。

## API情報 / 使い方
- 出典: JNTO 統計（無認証・公開PDF）。`https://www.jnto.go.jp/statistics/data/` の
  「年別 訪日外客数、出国日本人数の推移」リンク先PDF。
```bash
python fetch.py --output-dir ./output           # 最新URLが変わったら --url で差し替え
```
出力: `<date>_jnto_inbound_outbound.csv`（year, visitor_arrivals, japanese_overseas, 単位＝人）＋ metadata.json。

検証済み参照値（人）:
| year | 訪日 | 出国 | 大小 |
|---|---|---|---|
| 1964 | 352,832 | 127,749 | 訪日>出国 |
| 1971 | 660,715 | 961,135 | **出国>訪日へ逆転** |
| 2015 | 19,737,409 | 16,213,789 | **訪日>出国へ再逆転** |
| 2024 | 36,870,148 | 13,007,282 | 訪日>出国（出国はコロナ前2019比 未回復） |

## ハマり所
1. **二次資料（世界国勢図会等）は近年だけ**のことが多い。**長期（1964〜）はJNTO原典PDFを直接**取る。
   1985年プラザ合意後の円高で出国急増、1971/2015の逆転、コロナ前後の回復差…の物語はこれで描ける。
2. **PDFパース**: 各年ブロックは「年・和暦・訪日(カンマ区切り数)・伸率・出国(カンマ区切り数)・伸率」。
   **伸率（15.5 / △22.7）はカンマ無し → カンマを含む数だけが訪日・出国**。これで読み飛ばし判定する。
3. **年次更新でPDFファイル名（URL）が変わる**。`DEFAULT_URL` は固定なので、404時は統計ページで最新リンクを確認。
4. **コロナ後の回復は非対称**: 訪日は2024年に2019年超で回復、出国は未回復（2024<2019）。設問の誤文に使える。

## 効くケース
- 観光の長期推移（折れ線2本）、訪日↔出国の逆転、円高/ビザ緩和/LCC/オーバーツーリズム/コロナの正誤設問。
- 図はインバウンド急増で近年が巨大 → 直線目盛りだと古い年が潰れる。**起点を1980年代にする**と出国増が見える
  （実例: `sougou4_fix_p000/scripts/make_s4_fig3.py`）。

## 規約準拠
- `Path(__file__)` 基点、`encoding="utf-8"`、`newline="\n"`、`DataFetchError`、User-Agent付与、
  metadata.json（source/url/sha256/retrieved_at）、パース異常時は件数・先頭で fail。
