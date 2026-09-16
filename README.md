# geo-data-cookbook

**41 reproducible recipes for pulling public statistics and turning them into figures.**

Each recipe is a pair:

- `recipe.md` — where the data lives, what the fields mean, and a **ハマり所
  (gotcha) section**: the traps actually hit while building it, with the wrong
  numbers they produce.
- `fetch.py` — a standalone CLI. No shared library, no framework. Copy one
  directory and it runs.

The recipes are written in Japanese. The code and the API details are not.

## Why this exists

Client libraries for statistical APIs are common. What is not written down
anywhere is **what goes wrong**. A few examples from this repository:

- FAOSTAT's `China` is not China. It is mainland China + Taiwan + Hong Kong +
  Macao. Use it alongside `China, mainland` and you count the same production
  twice. (`recipes/faostat/crops_ranking`)
- Eurostat Comext ships per-commodity rows and a `PRODUCT=TOTAL` row **in the
  same file**. Sum them all and Portugal's air freight becomes 9.9% of tonnage —
  2.35 Mt through an airport that handles about 150 kt.
  (`recipes/eurostat/trade_by_transport_mode`)
- A US BTS dataset returns HTTP 200 and an empty array. It is a chart view;
  the real data sits behind `metadata.modifyingViewUid`. Reading 200 + `[]` as
  "no data" throws away a working route. (`recipes/aviation/airport_passengers`)
- UN Comtrade uses **699 for India** and **251 for France**, not the M49 codes.
  The M49 codes return zero rows for every year — silently.
  (`recipes/comtrade/region_trade_matrix`)

There are **268 such notes** across the 41 recipes.
[`PITFALLS.md`](PITFALLS.md) groups the ones that recur across unrelated
sources into 10 families — read it before writing against a source that has no
recipe here yet.

## Sources covered

- **aquastat** — water_resources
- **aviation** — airport_passengers
- **cams** — dust_aod_map
- **comtrade** — mutual_flow_diagram, region_trade_matrix, trade_ranking
- **estat** — calc_social, census_age_sex_municipality, commerce_sales_prefecture, keizai_census_industry, manufacturing_shipment_prefecture, prefecture_classify
- **eurostat** — air_flow, trade_by_transport_mode
- **faostat** — crops_ranking
- **gsi_dem** — relief_map, route_section
- **hydrosheds** — world_basin_erosion_map
- **iea** — electricity_generation
- **ilo** — employment_by_activity, wages_ranking
- **jma** — amedas_normals, snowfall_ranking
- **jnto** — inbound_outbound
- **mlit** — n03_municipal_boundary
- **mof** — direct_investment
- **naturalearth** — japan_prefectures, world_choropleth
- **noaa_psl** — climate_maps
- **oecd** — sdmx_datasets
- **oica** — vehicle_production
- **owid** — energy_data
- **transport** — roro_and_road_freight
- **un_wpp** — population_ranking
- **un_wup** — urbanization_ranking
- **unido** — industry_output
- **unwto** — tourism_statistics
- **usgs** — mineral_production
- **who_gho** — health_indicators
- **world_bank** — country_indicator
- **worldsteel** — crude_steel

## Usage

```bash
pip install -r requirements.txt
python recipes/<source>/<task>/fetch.py --help
```

Recipes that need an API key read it from the environment (e.g. `ESTAT_APP_ID`).
Recipes that cache bulk downloads default to `./data_bulk` and take a flag to
point elsewhere.

## What is not here

This is the data-acquisition half of a larger system for producing geography
teaching material. The typesetting code, the reference corpora, and the
teaching materials themselves are not public.

## License

MIT for the code. The recipe notes describe third-party data sources; the data
itself is governed by each provider's own terms, which the recipes cite.
