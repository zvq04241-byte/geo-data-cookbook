# UN Tourism 一括 zip の実測（2026-10-26）

入力: 保管庫 ./data_bulk/other_primary/unwto/UN_Tourism_bulk_05_2026.zip（8,910,727 B）。各 xlsx の "Data" シートを pandas で読んだ。

| ドメイン | 行 | 報告国・地域 | 年 | 単位 | 指標数 | 相手先 |
|---|---|---|---|---|---|---|
| domestic_trips | 2,547 | 103 | 1995–2024 | thousand trips | 3 | なし |
| domestic_accommodation | 6,835 | 126 | 1995–2024 | thousand guests / overnights | 4 | なし |
| inbound_arrivals | 13,900 | 215 | 1995–2024 | thousand trips | 4 | World |
| inbound_expenditure | 13,987 | 214 | 1995–2024 | million US dollars (nominal values) | 3 | World |
| inbound_by_region | 33,839 | 213 | 1995–2024 | thousand trips | 3 | 7地域＋World |
| inbound_by_purpose | 12,031 | 187 | 1995–2024 | thousand trips | 3 | World |
| inbound_by_transport | 14,573 | 195 | 1995–2024 | thousand trips | 4 | World |
| inbound_accommodation | 10,214 | 188 | 1995–2024 | thousand guests / overnights | 4 | World |
| outbound_departures | 4,251 | 142 | 1995–2024 | thousand trips | 3 | World |
| outbound_expenditure | 14,279 | 204 | 1995–2024 | million US dollars (nominal values) | 3 | World |
| accommodation_hotels | 18,594 | 214 | 1995–2024 | overnights / percent / units | 6 | なし |
| macroeconomic | 1,771 | 154 | 2008–2024 | PERCENT | 1 | なし |
| employment | 24,775 | 168 | 2008–2024 | number of persons | 107 | なし |
| sdgs | 7,588 | 176 | 2008–2024 | NUMBER | 3 | なし |

観光収入（inbound_expenditure, World）:
- total − travel − passenger transport の差: 3,995組で最大 0.208
- 年別の報告国・地域数: 1995 184 / 2005 201 / 2015 202 / 2019 193 / 2020 193 / 2023 167 / 2024 121
- 報告国・地域ごとの最終年: 2024 121 / 2023 47 / 2022 15 / 2021 7 / 2020 4 …
- 中国まわりのラベル: China / Taiwan Province of China / China, Hong Kong Special Administrative Region / China, Macao Special Administrative Region

WDI（保管庫 WDI_CSV.zip, ST.INT.RCPT.CD）: CHN 8点 1997–2004 / WLD 1995–2019 / FRA 1995–2020 / JPN 1995–2020。最終年の分布 2020:129, 2019:46, 2018:25。
