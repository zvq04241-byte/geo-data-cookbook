---
id: usgs/mineral_production
api: usgs
task: USGS Mineral Commodity Summaries の国別生産量（ボーキサイト・リチウム等）
items: [鉱種別 世界各国の生産量]
tags: [usgs, minerals, bauxite, lithium, production, pdf-parse, no-auth]
summary: USGS MCS の年次PDFから鉱種別の国別生産量を抽出。pdftotextで取得、e（推定値）が次行に折返す罠
pattern: pdf-download + pdftotext-layout
auth_required: false
verified_at: 2026-06-21
complexity: medium
gotcha_count: 3
---

# USGS / mineral_production（鉱産資源 国別生産量）

## 何をする
USGS Mineral Commodity Summaries（MCS）の年次PDFから、鉱種ごとの「World Mine Production」表＝国別生産量を抽出。
世界シェア図（資源の主要産出国）に使う。原問当時 vs 最新の対比で「ギニアのボーキサイト急伸」「中国のリチウム急伸」等を可視化。

## 取得先
- PDF: `https://pubs.usgs.gov/periodicals/mcs<YYYY>/mcs<YYYY>-<commodity>.pdf`
  - 例: `mcs2024-bauxite-alumina.pdf`（2022/2023値）、`mcs2024-lithium.pdf`、`mcs2020-...`（2018/2019値）。
- MCS<YYYY> は前々年〜前年の値（MCS2024=2022/2023、MCS2020=2018/2019）。原問当時の年に合わせて版を選ぶ。

## 抽出方法
```bash
pdftotext -layout mcs2024-lithium.pdf - | sed -n '/Mine production/,/World total/p'
```

## ハマり所（重要）
1. **★`e`（推定値）付きの国は、数値が次の行に折り返す**（例: `China e` の次行に `22,600  33,000  3,000,000`）。
   国名行で `e` のみ → 直後の行の数値を拾う処理が要る。
2. **ボーキサイト表はアルミナ生産と交互配置で列がズレる**（Alumina 2022/2023 → Bauxite 2022/2023 → Reserves）。
   ボーキサイトの値は3〜4列目。リチウム表は単純（Mine production 2022/2023 のみ）で安全。
3. **`W`（企業秘匿）・`—`（該当なし）** は欠損として扱う。世界総計も末尾に折返すことがある。

## 関連（特許など他系列）
- 特許の世界シェアは **WIPO PCT**（国別出願件数。2019年に中国が米国を抜き№1）。原問「特許＝先進国が多い」の陳腐化例。

## 参照実装
- `kakomon_update_2020geoB_q2_p000`（問1 ボーキサイト・リチウム・特許の世界シェア 旧/新）。詳細 [[kakomon_data_update_pipeline]]。
