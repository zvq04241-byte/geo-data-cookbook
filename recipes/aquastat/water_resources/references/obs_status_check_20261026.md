# Data360 FAO_AS の OBS_STATUS と指標一覧の確認（2026-10-26）

取得: `GET https://data360api.worldbank.org/data360/data?DATABASE_ID=FAO_AS&INDICATOR=<code>&skip=<n>`（REF_AREA 無しで全件、1,000件ずつ）

| 指標 | 行数 | 国・地域 | OBS_STATUS |
|---|---|---|---|
| FAO_AS_4188（TRWR） | 11,033 | 189 | すべて A |
| FAO_AS_4157（IRWR） | 10,527 | 181 | すべて A |

- 2026-06-12 の出力（`output/20260612_aquastat_water_resources.csv`）では EGY・SAU・PAK・NGA の TRWR が I だった。値は同じ（EGY 57.5）。
- REF_AREA はすべて英字3文字（集計らしいコードなし）。
- 指標一覧 `/data360/indicators?datasetId=FAO_AS` は112本。`FAO_AS_4104`（総人口）・`FAO_AS_4174` は一覧に無く、値0件。
- `FAO_AS_4190`（1人当たり TRWR, m3/inhab/yr）2022年: EGY 510.6 / SAU 74.6 / PAK 1012.7 / NGA 1282.5
  （以前の 4188÷4104 の算出値 511 / 75 / 1013 / 1283 と一致）
- `FAO_AS_4192`（依存率 %）2022年: EGY 98.26 / SAU 0 / PAK 77.71 / NGA 22.78（(TRWR−IRWR)/TRWR と一致）
- urllib で User-Agent を付けないと HTTP 403（同日確認）
