---
id: worldsteel/crude_steel
api: worldsteel
task: 国別 粗鋼生産量（百万t）と EU27 占有割合を取得
items: [粗鋼生産量, 国別粗鋼, EU27シェア]
tags: [worldsteel, crude-steel, production, country-level, eu27, pdf-parse, pdftotext-layout, no-auth]
summary: 世界鉄鋼協会(worldsteel)公式PDFから国別 粗鋼生産量を取得（Wikipedia不使用）。直近=WSIF(EU27直接)/2000=SSY2002 Table4
pattern: official-pdf-download + pdftotext-layout-columns + table-window-isolation
auth_required: false
verified_at: 2026-10-26
complexity: medium
gotcha_count: 5
---

# worldsteel / crude_steel — 世界鉄鋼協会 国別粗鋼生産量

## 何をする
worldsteel（世界鉄鋼協会）の**公式PDF**から国別の粗鋼生産量（百万t）と**EU27占有割合**を取得する。
粗鋼生産の一次出典は worldsteel。`fetch.py` は指定年・指定国の値と EU27合計を CSV + metadata.json に出す。
Wikipedia等の二次集計は**使わない**（[[feedback_no_wikipedia_data_source]]）。

## データ源
- **直近(2024)**: "World Steel in Figures 2025" PDF
  `https://worldsteel.org/wp-content/uploads/World-Steel-in-Figures-2025-3.pdf` の
  "Crude steel production by process" 表。**"European Union (27)" の行がある**（129.7 Mt）。fetch.py はこのラベルを完全一致で取る。
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
★`--countries` の既定は独・仏・西・チェコの**4か国の抜粋**。CSV に出るのは指定国と EU27 の行だけで、EU 加盟国の全部ではない。
metadata の `scope` にそう書く。EU27 の内訳全部が要るなら `--countries` に全加盟国を渡す。
検証値（2026-10-26 に fetch.py を実行して再現）: 2024 独37.2 / 仏10.8 / 西11.9 / チェコ2.5 / **EU27 129.7**（WSIF 2025 の "Crude steel production by process" 表。
EU27 行より前に並ぶ加盟国20行の合計 129.6 と照合）。
2000 独46.376 / 仏20.954 / 西15.874 / チェコ6.216 / **EU27 178.4**（SSY2002 Table 4。EU15 163,357 − UK 15,155 ＋ 新規加盟9か国 30,195 ＋ エストニア・リトアニア 1 千t）。

## ハマり所（重要）
1. **"生産"と"消費(見かけ消費)"を混同しない**: WSIF内には "Apparent steel use"(見かけ消費)表もあり、
   独26.0 / EU27 130.1 (2024) など**似た値**が並ぶ（WSIF 2025 の Apparent steel use 表で確認）。使うのは "Crude steel production"。取り違え厳禁。
2. **同名の別テーブルを拾わない（SSY2002）**: SSYには銑鉄(pig iron)等の似た表があり、
   国名だけで最初に一致する行を採ると **銑鉄の値**（Table 1 "Total Production of Pig Iron"、F.R. Germany 2000年 30,845千t）を拾う。
   → "Total Production of Crude Steel" **ヘッダ以降〜次Table** の窓に限定してパースする。
   さらに**目次(TOC)行**（"Table 4 … Crude Steel … 10" のように末尾がページ番号）を除外する。
3. **列は空白区切り・`pdftotext -layout` 必須**: SSY2002は千t値が "17 972" のように空白区切りで、
   列間も詰まっている。`-layout` で列を多スペース化し `\s{2,}` 分割（[[oica/vehicle_production]]と同罠）。
4. **EU27(2000)は EU15−UK＋新規加盟国**: SSY2002の "European Union (15)" 行は**UKを含む**
   （EU15 の15か国の行の合計 163,357千t が EU15 行と一致することで確認）。
   EU27 は **EU15 − UK（14か国）＋ 2004年以降の加盟13か国**。13か国のうち、
   - チェコ・ポーランド・ハンガリー・スロバキア・スロベニア・ルーマニア・ブルガリア・ラトビア・クロアチアの9か国は Table 4 に行がある
   - エストニア・リトアニアは年の欄が欠けて行として読めない → "Baltic States" − Latvia を足す（2000年 1千t）
   - キプロス・マルタは Table 4 に行が無い（粗鋼生産なし）
   fetch.py は見つからない加盟国があれば止まり、内訳を metadata の `eu27_check` に書く。UK控除を忘れると過大(193.6)になる。
5. **EU の行は完全一致で取る**: "EUROPEAN UNION" の前方一致だと (15) と (27) の両方に当たり得る。前方一致が複数に当たれば fetch.py は止まる。

## 関連
- 図版データ源カタログ [[zuhan_data_sources_catalog]] ⑧。自動車は [[oica/vehicle_production]]。
- 使いどころ: 自動車×粗鋼のEU27占有割合の散布図など。
