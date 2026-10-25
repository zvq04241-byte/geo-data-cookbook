# 順位の母集団と集計地域の確認（2026-10-26、World Bank API）

- `/v2/country?per_page=1000`: 296件。region.value が `Aggregates` は79、残り217（国・地域）。
- `country/all/indicator/NY.GDP.MKTP.CD?mrv=1`: 266件。うち5件は countryiso3code が空
  （High income / Low income / Lower middle income / Not classified / Upper middle income）。
- `--all-countries` の GDP 上位30（各国の最新非null年、2024〜2025）: 30位がアラブ首長国連邦。
  `references/gdp_ranking_top30.yml` の must_include_in_top5（India）は不合格: 2025年の値で India は6位（5位 United Kingdom）。
  既定49か国で取っても同じ（上位は49か国に入っている国だけ）。
- 1人当たりGDP（NY.GDP.PCAP.CD）: 既定49か国の1位は Ireland。世界の順位とは別物（既定に入っていない小国が上位に来る指標）。
- IS.AIR.PSGR 2023年（集計地域を除く全ての国・地域、値のある168）: 1 United States 941,557,000 / 2 China 619,215,886 / 3 Ireland 192,528,432。
- 既定49か国＋TWN の一括（mrv=10）: HTTP 200・total 490（TWN は0件）。TWN 単独: page=0/total=0。
