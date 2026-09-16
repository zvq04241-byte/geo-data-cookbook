---
id: worldsteel/crude_steel
api: worldsteel
task: 国別 粗鋼生産量（百万t）と EU27 占有割合を取得
items: [粗鋼生産量, 国別粗鋼, EU27シェア]
tags: [worldsteel, crude-steel, production, country-level, eu27, pdf-parse, pdftotext-layout, no-auth]
summary: 世界鉄鋼協会(worldsteel)公式PDFから国別 粗鋼生産量を取得（Wikipedia不使用）。直近=WSIF(EU27直接)/2000=SSY2002 Table4
pattern: official-pdf-download + pdftotext-layout-columns + table-window-isolation
auth_required: false
verified_at: 2026-07-19
complexity: medium
gotcha_count: 4
---

# worldsteel / crude_steel — 世界鉄鋼協会 国別粗鋼生産量

## 何をする
worldsteel（世界鉄鋼協会）の**公式PDF**から国別の粗鋼生産量（百万t）と**EU27占有割合**を取得する。
粗鋼生産の一次出典は worldsteel。`fetch.py` は指定年・指定国の値と EU27合計を CSV + metadata.json に出す。
Wikipedia等の二次集計は**使わない**（[[feedback_no_wikipedia_data_source]]）。

## データ源
- **直近(2024)**: "World Steel in Figures 2025" PDF
  `https://worldsteel.org/wp-content/uploads/World-Steel-in-Figures-2025-3.pdf` の
  "Crude steel production by process" 表。**"European Union (27)" が直接報告**される（129.7 Mt）。
- **2000年など(1992-2001)**: "Steel Statistical Yearbook 2002" PDF
  `https://worldsteel.org/wp-content/uploads/Steel-Statistical-Yearbook-2002.pdf` の
  **Table 4 "Total Production of Crude Steel"**（千t・列=1992..2001）。EU27区分は当時無い。
- 認証不要。サイトはJS描画で WebFetch は本文を返さない → PDF直DL＋`pdftotext -layout`。

## 使い方
```bash
python fetch.py --year 2024 --output-dir ./output    # WSIF(百万t)。EU27直接
python fetch.py --year 2000 --output-dir ./output    # SSY2002 Table4(千t→百万t)。EU27=合算
```
出力: `YYYYMMDD_worldsteel_crude_<year>.csv`（国, 粗鋼百万t, EU27シェア%）＋ metadata.json。
検証値: 2024 独37.2 / 仏10.8 / 西11.9 / チェコ2.5 / **EU27 129.7**。
2000 独46.376 / 仏20.954 / 西15.874 / チェコ6.216 / **EU27 178.4**。

## ハマり所（重要）
1. **"生産"と"消費(見かけ消費)"を混同しない**: WSIF内には "Apparent steel use"(見かけ消費)表もあり、
   独26.0 / EU27 130.1 (2024) など**似た値**が並ぶ。使うのは "Crude steel production"。取り違え厳禁。
2. **同名の別テーブルを拾わない（SSY2002）**: SSYには銑鉄(pig iron)等の似た表があり、
   国名だけで最初に一致する行を採ると **銑鉄の値**（独~30k千t）を拾う。
   → "Total Production of Crude Steel" **ヘッダ以降〜次Table** の窓に限定してパースする。
   さらに**目次(TOC)行**（"Table 4 … Crude Steel … 10" のように末尾がページ番号）を除外する。
3. **列は空白区切り・`pdftotext -layout` 必須**: SSY2002は千t値が "17 972" のように空白区切りで、
   列間も詰まっている。`-layout` で列を多スペース化し `\s{2,}` 分割（[[oica/vehicle_production]]と同罠）。
4. **EU27(2000)は EU15−UK＋新規加盟国**: SSY2002の "European Union (15)" 行は**UKを含む**。
   EU27にするには **EU15 − UK ＋ 新規加盟国(チェコ/ポーランド/…)の合算**。UK控除を忘れると過大(193.6)になる。

## 関連
- 図版データ源カタログ [[zuhan_data_sources_catalog]] ⑧。自動車は [[oica/vehicle_production]]。
- 実適用: 探究6 図4（自動車×粗鋼のEU27占有割合 散布図）。
