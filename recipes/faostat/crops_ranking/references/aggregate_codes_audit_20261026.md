# 集計地域の判定を名前から Area Code に替えたときの照合（2026-10-26）

対象: 保管庫の `Production_Crops_Livestock_E_All_Data_(Normalized).zip`（ZIP 内ファイルの日付 2025-12-23）。
同梱の `Production_Crops_Livestock_E_AreaCodes.csv`（244行）を、旧方式（名前の完全一致リスト `AGG_AREAS`）と
新方式（Area Code >= 5000 または lib.bulk_data.FAOSTAT_AGGREGATE_AREAS）で突き合わせた。

| 項目 | 件数 |
|---|---|
| Area Code で集計と判定（>=5000 と 351） | 35 |
| そのうち旧方式の名前リストで漏れるもの | 0（この版では） |
| 旧方式だけが落としていた Area Code < 5000 の地域 | 7 |

旧方式だけが落としていた7件は、集計ではなく**解体前の国**（期間中は唯一の値で、後継国と年が重ならない）:
Belgium-Luxembourg(15)・Czechoslovakia(51)・Ethiopia PDR(62)・Serbia and Montenegro(186)・Sudan (former)(206)・USSR(228)・Yugoslav SFR(248)。
旧方式では 1985年の小麦で USSR（7,320万t・第2位）が黙って消えていた。新方式では残る。

確かめた動き（同日）:
- Wheat 2023 上位10 = China, mainland → India → Russian Federation → … → Ukraine（`wheat_2023_top10.yml` と一致）
- 壊した入力（Area Code 5999 の改称した地域集計・China 351 を入れた CSV）→ 両方とも順位から落ちた
- 作物生産量（Element=Production）2023年・Area Code<5000 の 20,989 行の Flag: A 8,948 / I 6,298 / E 4,279 / X 1,119 / M 345
