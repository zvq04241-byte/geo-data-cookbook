# WPP2024_TotalPopulationBySex.csv.gz の実測（2026-10-26）

入力: ~/.cache/wpp/WPP2024_TotalPopulationBySex.csv.gz（16,980,593 B、展開 85,787,430 B）。csv.DictReader（utf-8-sig）で読んだ。

- 720,210 行 × 18列（SortOrder, LocID, Notes, ISO3_code, ISO2_code, SDMX_code, LocTypeID, LocTypeName, ParentID, Location, VarID, Variant, Time, MidPeriod, PopMale, PopFemale, PopTotal, PopDensity）。全ロード約1秒
- Variant 18種。Medium は1950–2100、Low/High/Constant fertility/Instant replacement/Zero migration/No change 等は2024–2100
- LocTypeID: 1 World / 2 Geographic region / 3 Subregion / 4 Country/Area / 5 Development group / 12 SDG region / 13 Income group・Special other / 14 Ad Hoc groups / 空欄
- 2024年 Medium の LocTypeID=4: 237件、PopTotal 空欄0、PopDensity 空欄0。合計 8,161,972.6千人＝World 8,161,972.572千人
- LocTypeID=4 に含まれる非独立の地域の例: China, Hong Kong SAR / China, Taiwan Province of China / State of Palestine / Holy See / Kosovo (under UNSC res. 1244) / Puerto Rico / Greenland
- India 2024 1,450,935.791 / 2010 1,243,481.564；China 2024 1,419,321.278 / 2010 1,351,561.514（千人）
- India > China になる最初の年: 2022（China 1,425,179.569 / India 1,425,423.212）
- Libya IMR 2010–14（Demographic_Indicators_Medium）: 14.13, 14.86, 12.80, 12.32, 12.08 → 平均 13.24
