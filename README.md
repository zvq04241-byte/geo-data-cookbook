# geo-data-cookbook

**Public statistics go wrong quietly.** The request succeeds, the numbers look
plausible, and the figure is already printed before anyone notices.

Client libraries for statistical APIs are common. **What goes wrong is not
written down anywhere.** This repository is that missing half — 168 traps
across 41 data sources, each with the wrong number it produces.

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


## Point your coding agent at it

**This repository is written for AI agents as much as for people.**

`AGENTS.md` at the root is an index of all 254 traps — 5,000 tokens, small
enough to sit in an agent's context. Most AI CLIs (Codex, Claude Code, Cursor,
Gemini CLI, Copilot CLI, Antigravity) read a root `AGENTS.md` automatically.

```bash
git clone https://github.com/zvq04241-byte/geo-data-cookbook
cd geo-data-cookbook          # or place it beside your own project
codex   # claude / agy / copilot — any of them
```

Then ask for what you actually want:

```
FAOSTAT から 2023年の米の生産量 上位5か国を出す Python を書いてください。
```

The agent reads the index, opens the one recipe that matches, and writes the
aggregate-region exclusion without being told:

```python
# 国ではない集計地域。完全一致で除外する（表記が変わると漏れる）。
# China は mainland+Taiwan+HK+Macao の合計なので、教材では China, mainland を残す。
AGG_AREAS = {"World", "Africa", "Asia", ...}
```

That is the point of the repository. **The traps are knowledge no model has;
the code is knowledge every model has.**

## What this is

**41 reproducible recipes for pulling public statistics and turning them into figures.**

Each recipe is a pair:

- `recipe.md` — where the data lives, what the fields mean, and a **ハマり所
  (gotcha) section**: the traps actually hit while building it, with the wrong
  numbers they produce.
- `fetch.py` — a standalone CLI. No shared library, no framework. Copy one
  directory and it runs.

The recipes are written in Japanese. The code and the API details are not.

## Found a trap we don't have?

**Please open an issue — the trap alone is enough. No code required.**

Three lines is a complete report:

- what you asked the API for
- what you got instead
- the wrong number it produced

See [CONTRIBUTING.md](CONTRIBUTING.md). Japanese or English, either is fine.

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
