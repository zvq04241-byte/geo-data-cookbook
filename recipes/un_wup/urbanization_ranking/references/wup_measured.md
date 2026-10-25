# WUP 2025 Degree of Urbanization の実測（2026-10-26）

入力: ./cache/.wup_cache/WUP2025-F02-...percPop_by_category.xlsx（1,077,514 B）、同 F01（1,704,537 B）。
fetch.py（--cache）と openpyxl で読んだ。

- シート: F02 = info / Rural / Towns / Cities / Cities and Towns / NOTES。F01 は加えて Total。
- info の表題: F01 "(thousands)"、F02 "(per cent)"。収録 1950-2050。推計の開始年の記載は無い。
- 見出し（F01・F02 共通）: 0 Index / 1 Location / 2 Notes / 3 LocID / 4 ISO3_Code / 5 ISO2_Code / 6 SDMX_Code / 7 LocType / 8 LocTypeName / 9 ParentID / 10〜 1950…2050
- LocType の内訳（Cities and Towns シート）: 4:237, 14:23, 3:21, 13:16, 12:10, 5:7, 2:7, 25:5, 1:1
- 2025年 Cities and Towns %、LocType==4 の上位: Gibraltar 100 / Holy See 100 / Monaco 100 / Singapore 99.9 /
  China, Macao SAR 99.9 / China, Hong Kong SAR 99.6 / Bermuda 98.5 / Bangladesh 98.0 / Bahrain 98.0 / Egypt 97.5 …（Japan 91.4）
- 値なし（None）: 0件（2025年）
- 従来定義との比較: 保管庫 WDI_CSV.zip の SP.URB.TOTL.IN.ZS は 2024年 BGD 32.68 / EGY 42.80
