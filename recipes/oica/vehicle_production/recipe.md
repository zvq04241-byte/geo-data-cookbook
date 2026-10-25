---
id: oica/vehicle_production
api: oica
task: 国別 自動車生産台数（乗用車/全車種）と EU27 占有割合を取得
items: [自動車生産台数, 乗用車生産, 全車種生産, EU27シェア]
tags: [oica, motor-vehicle, production, country-level, eu27, pdf-parse, pdftotext-layout, archive-org, no-auth]
summary: OICA公式PDFから国別 自動車生産台数を取得（Wikipedia不使用）。現行サイトは6年窓のみ・古い年はarchive.org公式。pdftotext -layoutで列分割
pattern: official-pdf-download + pdftotext-layout-columns + archive-org-fallback
auth_required: false
verified_at: 2026-10-26
complexity: medium
gotcha_count: 5
---

# oica / vehicle_production — OICA 国別自動車生産台数

## 何をする
OICA（国際自動車工業連合会）の**公式PDF**から、国別の自動車生産台数（全車種 cars+CV／または乗用車のみ）と
**EU27占有割合**を取得する。世界の自動車生産の一次出典は OICA。`fetch.py` は指定年・指定国の値と
EU27合計を CSV + metadata.json に出力する。Wikipedia等の二次集計は**使わない**（[[feedback_no_wikipedia_data_source]]）。

## データ源
- **直近(2019/2021/2022/2023/2024)**: `https://oica.net/wp-content/uploads/2025/10/By-country-region-2024.pdf`
  （全車種）／`Passenger-Cars-2024.pdf`（乗用車）。1ファイルに直近6年を収録。
- **2000年**: 現行サイトに無い → **archive.org のOICA当時の公式PDF**
  `http://web.archive.org/web/20011202143429id_/http://www.oica.net/htdocs/statistics/tableaux2000/worldprod_country.PDF`
  （`id_` = 原本rawを返す修飾子。無いとツールバー付きHTMLが返る）。
- 認証不要。curl/urllib で直DL可。

## 使い方
```bash
python fetch.py --year 2024 --measure all  --output-dir ./output   # 全車種(cars+CV)
python fetch.py --year 2024 --measure cars --output-dir ./output   # 乗用車のみ
python fetch.py --year 2000 --measure all  --output-dir ./output   # archive.orgの2000年公式
```
出力: `YYYYMMDD_oica_<measure>_<year>.csv`（国, 一致した行ラベル, 台数, EU27シェア%, flag＝行ラベルの注記, scope）＋ metadata.json（`scope`・`eu27_detail`）。
2026-10-26 に fetch.py で取った値（PDFの行をそのまま読んだもの。別の統計とは照らしていない）:
2024全車種 独4,069,222（cars only）/ 仏1,357,701（cars and LCV only）/ 西2,376,504 / チェコ1,458,892 / **EU27 13,402,753**（公式行 EU27+UK − UK）。
2000全車種 独5,526,615 / 仏3,348,351 / 西3,032,874 / チェコ455,481 / **EU27 16,757,407**（自己合算。下の4）。
（旧版の 2000 EU27 16,757,461 は、空欄を詰めて読む誤りでデンマーク18台と二重計上72台を取り違えていた。）

## ハマり所（重要）
1. **現行サイトはJS描画・DLは6年窓のみ**: `oica.net/production-statistics/` は jet-engine(Google Charts)で、
   HTMLに埋め込まれるのは各年 **top10 だけ**。公式DL PDFも直近6年窓(2019-2024)しか無い。
   → 2000年など古い年は **archive.org の当時のOICA公式PDF**（`id_`付き）を使う。
2. **数値が空白区切り千位で列間も単一スペース**: 生テキストは "4 663 749" のように千位も空白、
   隣の列との間も同じ単一空白で**語彙的に切れない**。pypdf/naive split は数字を連結してしまう。
   → **`pdftotext -layout`** で列を多スペース化し、**見出しの年の位置に値を割り当てる**。
   空欄の列を左に詰めて読むと、片方の年しか値の無い行（2000年版のデンマーク・一部の二重計上）が隣の年に化ける。
3. **直近の全車種PDFは国によって車種の範囲が違う**: 行ラベルに注記がある（2026-10-26 確認）。
   独・フィンランド `cars only`、仏 `cars and LCV only`、蘭・スウェーデン `yearly only`。独は全車種PDFの値＝乗用車PDFの値（4,069,222）。
   PDF末尾の注記は「CARS: Audi, BMW, JLR, Mercedes not reported」。なぜ商用車が無いかの理由は PDF に書かれていない。
   EU27 合計もこの混じった値の和なので、同じ年の EU27 シェアでも独・仏などは範囲が狭い。注記は CSV の `flag` 列と metadata に出る。
   2000(全車種)との**年跨ぎ比較は特に要注意**。
4. **EU27の単一公式行があるのは直近PDFだけ**（このレシピが読む2つのPDFについて）: 直近は "EUROPEAN UNION 27 countries + UK" 行があり
   EU27 = その行 − UK。2000年版（上の archive.org のPDF）は "- EUROPEAN UNION"（EU15＋英国）行しか無く、
   **表にある加盟国の合算 − 両方がEU27の Double Countings** で構成する。
   ★2000年の EU27 は照らす相手の無い自己合算。代わりに、同じ作り方で EU15 を組んで "EUROPEAN UNION" 行と一致するかを確かめ、合わなければ止める（2000年は全車種・乗用車とも一致）。
   直近も、公式行と「表の加盟国＋英国」の和を照らす。全車種の 2019・2021〜2023年は EU15 小計が内訳の和より 11,900〜21,000台小さい（OICA の表のまま）。
   差が0.2%以内なら公式行の値を使って差を metadata に記録し、超えたら止める。
   ★**EU27 は表に行がある国だけの和**: 表に無い加盟国（ブルガリア・クロアチア・ギリシャ・アイルランドなど11か国）は含まれない。
   metadata の `eu27_detail.eu27_countries_not_in_table` と `scope` に出る。国名は完全一致で照合する（前方一致はやめた）。
5. **脚注参照と相手先名の混入**: "GERMANY(2)" "FRANCE (1)" の脚注 `(n)` や、行末の統計元
   （VDA/ANFAC/Autosap等）がラベル/数値列に紛れる。`(n)` を除去し、%以降・非数値セルで打切る。

## 関連
- 図版データ源カタログ [[zuhan_data_sources_catalog]] ⑧ に取得先を集約。
- 2000年の EU27 は [[worldsteel/crude_steel]] と同様、当時区分が無いので現27か国で構成する（上の4）。
- 実適用: 自動車×粗鋼のEU27占有割合の散布図。
