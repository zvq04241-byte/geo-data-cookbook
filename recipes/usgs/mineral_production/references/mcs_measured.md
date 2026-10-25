# USGS MCS の表の実測（2026-10-26）

入力: pubs.usgs.gov/periodicals/mcs2024/mcs2024-{lithium,bauxite-alumina}.pdf、mcs2020/mcs2020-{lithium,bauxite-alumina}.pdf を取得し `pdftotext -layout` で読んだ（PDF は保存していない）。

- MCS2024 リチウム（t）: 表頭 Mine production 2022 / 2023e。米国 W/W。Argentina 6,590/9,600、Australia 74,700/86,000、Brazil 2,630/4,900、Canada 520/3,400、
  Chile 38,000/44,000、China 22,600/33,000、Portugal 380/380、Zimbabwe 1,030/3,400、Other countries —/—、World total (rounded) 146,000/180,000（脚注7: Excludes U.S. production）。
  `e` の国は数値が次行。World total の数値も次行。
- MCS2024 ボーキサイト（千t）: 2023e は Australia 98,000 / Brazil 31,000 / China 93,000 / Greece 1,200 / Guinea 97,000 / India 23,000 / Indonesia 20,000 /
  Jamaica 6,000 / Kazakhstan 4,300 / Russia 5,800 / Saudi Arabia 4,600 / Turkey 2,000 / Vietnam 3,700 / Other countries 5,600 → 計 395,200。World total (rounded) 400,000（米国除く）。
  見出しは "Alumina production / Bauxite production"。"Mine production" の sed は0行。
- MCS2020 ボーキサイト: Guinea 57,000（2018）/ 82,000（2019e）。World total は `8327,000 8370,000`（脚注8が前に付く）。
- MCS2020 リチウム: China 7,100 / 7,500。World total `895,000 877,000`（脚注8＋95,000/77,000）。`Other7`。折り返しは無い。
