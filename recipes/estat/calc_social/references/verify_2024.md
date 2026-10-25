# 検算の記録: cdTime=2024100000

- 取得日時: 2026-06-20T08:03:40+09:00（本レシピの手順で e-Stat getStatsData を2回取得したもの）
- 手元の記録: 手元の実行結果（非公開。2026-06-20 に fetch.py で出力した CSV）
  （sha256 9975748ce66304fcd60d98ec22058cacfe808f375e404a00820522eb2e3e3e5b）
- 確かめたこと（2026-10-26、pandas で要約）
  - 行数 47、Unit 列はすべて `‰`、Year 列は 2024
  - 東京都: PopIncrease 6.6 / NaturalIncrease -3.7 / Value 10.3
  - すべての行で PopIncrease − NaturalIncrease − Value の差の最大は 1.3e-15（丸め誤差のみ）
- 人口増加率 6.6‰（東京都）は、別取得の `estat/prefecture_classify/output/20260518_estat_0000010101_A192003_2024100000_class4.csv`（2026-05-18 取得）とも一致。
- 自然増加率 -3.7‰ は上の1回の取得だけで確かめている（別系統の照合はしていない）。
