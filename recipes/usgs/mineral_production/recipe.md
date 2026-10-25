---
id: usgs/mineral_production
api: usgs
task: USGS Mineral Commodity Summaries の国別生産量（ボーキサイト・リチウム等）
items: [鉱種別 世界各国の生産量]
tags: [usgs, minerals, bauxite, lithium, production, pdf-parse, no-auth]
summary: USGS MCS の年次PDFから鉱種別の国別生産量を抽出。pdftotextで取得、e（推定値）が次行に折返す罠
pattern: pdf-download + pdftotext-layout
auth_required: false
verified_at: 2026-10-26
complexity: medium
gotcha_count: 6
---

# USGS / mineral_production（鉱産資源 国別生産量）

## 何をする
USGS Mineral Commodity Summaries（MCS）の年次PDFから、鉱種ごとの「World Mine Production」表＝国別生産量を抽出。
世界シェア図（資源の主要産出国）に使う。古い版と最新版を並べて、主要産出国の変化を見る。
例（MCS の表の値, 千t は省略）: ギニアのボーキサイト 2018年 57,000 → 2023年e 97,000（MCS2020 と MCS2024）、
中国のリチウム 2018年 7,100 → 2023年e 33,000（t, 同）。`references/mcs_measured.md`

## 取得先
- PDF: `https://pubs.usgs.gov/periodicals/mcs<YYYY>/mcs<YYYY>-<commodity>.pdf`
  - 例: `mcs2024-bauxite-alumina.pdf`（2022/2023値）、`mcs2024-lithium.pdf`、`mcs2020-...`（2018/2019値）。
- MCS<YYYY> は概ね前々年〜前年の値（MCS2024=2022/2023e、MCS2020=2018/2019e をボーキサイト・リチウムで確認）。
  年は必ず表頭で確かめる。比べたい年に合わせて版を選ぶ。

## 抽出方法
```bash
pdftotext -layout mcs2024-lithium.pdf - | sed -n '/Mine production/,/World total/{p;}' ; \
pdftotext -layout mcs2024-lithium.pdf - | grep -A3 'World total'      # ★総計の数値は次の行にある
```
- ★この `sed` は**リチウム表の見出し（"Mine production"）にしか当たらない**。ボーキサイト表の見出しは
  "Alumina production / Bauxite production" で、同じ sed では**何も出ない**（MCS2024・MCS2020 とも 2026-10-26 確認）。
  ボーキサイトは `sed -n '/World Alumina Refinery and Bauxite/,/World total/p'` で切り、総計は `grep -A3 'World total'` で別に取る。
- ★`World total` の行で止まるので、**総計の数値が次の行に折り返す版では総計を取りこぼす**（MCS2024 のリチウム・ボーキサイト）。

## ハマり所（重要）
1. **★`e`（推定値）付きの国は、数値が次の行に折り返す**（例: `China e` の次行に `22,600  33,000  3,000,000`）。
   国名行で `e` のみ → 直後の行の数値を拾う処理が要る。
   ★ボーキサイト表では `e` が列ごとに付くので、アルミナは国名と同じ行・ボーキサイトは次の行、と分かれる（MCS2024 のギニア・中国等）。
   ★MCS2020 では折り返さない。代わりに**脚注番号が数値にくっつく**（リチウム `World total 895,000 877,000` は脚注8＋95,000/77,000、
   ボーキサイト `8327,000`＝脚注8＋327,000、`Other7`）。版ごとに表の崩れ方が違う。
2. **ボーキサイト表はアルミナ生産と並んでいる**（Alumina 2022/2023 → Bauxite 2022/2023 → Reserves）。
   MCS2024 ではボーキサイトの値は数値列の3〜4列目。列の並びは版ごとに表頭で確かめる。リチウム表は Mine production 2列＋Reserves。
3. **`W`（企業秘匿）と `—`（該当なし・ゼロ）は意味が違う。混ぜない。**
   `W` は「生産はあるが公表しない」。MCS2024 では米国がリチウム・ボーキサイトとも `W` で、**World total は脚注で「米国を除く」**。
   シェアは World total（米国を除く）を分母にし、注に「米国は秘匿のため含まない」と書く。`—` は0扱いでよい。
4. **`Other countries` の行を分母から落とさない。** 国の行だけ足すと分母が縮み、各国のシェアが過大に出る。
   検算: MCS2024 のボーキサイト2023年eは 国13＋Other countries 5,600 の合計 395,200 ≒ World total（rounded）400,000。
   リチウム2023年eは 国8の合計 184,680 ≒ 180,000（Other countries は `—`）。この照合をしてからシェアを出す。
5. **版をまたいで比べるときは、両方の版の World total で各国のシェアを出す**（載る国と Other countries の中身が版で変わる）。

## 関連（特許など他系列）
- 特許の世界シェアは **WIPO PCT**（出願人の居住国別の国際出願件数）。2019年に中国 58,990 件が米国 57,840 件を上回り初めて1位
  （WIPO プレスリリース 2020年4月 https://www.wipo.int/pressroom/en/articles/2020/article_0005.html ）。受理官庁別では順位が違うので、指標を書く。

## 参照実装
- `kakomon_update_2020geoB_q2_p000`（ボーキサイト・リチウム・特許の世界シェア 旧/新）。
