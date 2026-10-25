# 構成比の合計・World と国の和の測定（2026-10-26）

対象: `https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv` を 2026-10-26 に取得（9,229,369 bytes / 23,377 行 / 130 列 / 1900〜2025年）。

測り方（pandas）:
```python
src = ["coal", "oil", "gas", "nuclear", "renewables"]
c = [s + "_share_energy" for s in src]
full = d.dropna(subset=c); tot = full[c].sum(axis=1)          # 5源がそろう行
isc = d.iso_code.notna() & ~d.iso_code.astype(str).str.startswith("OWID")   # 国
part = d[d[c].notna().any(axis=1) & d[c].isna().any(axis=1)]  # 一部だけ欠ける行
```

| 項目 | 結果 |
|---|---|
| 5源がそろう行 | 6,379（国 4,459・集計 1,920） |
| その合計 | 最小 99.998% / 最大 100.002%（98〜102% の外は0、99〜101% の外も0） |
| 一部だけ欠ける行 | 0 |
| World 2023 renewables の内訳 | 13.943 = hydro 6.084 + wind 3.317 + solar 2.357 + other_renewables 1.412 + biofuel 0.772 |
| 5源の `*_consumption` の和 ÷ `primary_energy_consumption` | 95.6〜102.9%（中央値 99.6%） |
| 2023年 World ÷ 国の和（primary） | 172,239 / 171,277 TWh |
| 2023年 World ÷ 国の和（coal） | 45,319 / 44,611 TWh |
| `iso_code` が空か OWID_ で始まる国名 | 94 |
