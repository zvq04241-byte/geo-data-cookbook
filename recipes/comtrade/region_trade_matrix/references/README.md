# references/ — region_trade_matrix が使う表と、測った記録

| ファイル | 中身 | 出典・取得 | sha256 |
|---|---|---|---|
| `m49_overview.csv` | 国連の地域区分（M49）。248行・15列 | UN Statistics Division "Standard country or area codes for statistical use (M49)" Overview（https://unstats.un.org/unsd/methodology/m49/overview/ の英語の表 id=downloadTableEN を CSV にしたもの）。2026-10-26 01:40 JST 取得 | `ccfd0a7b9b406b7b75bdfb4725af35adcca88e6102898401c46e29a796656037` |
| `m49_sovereignty_ne.csv` | M49 の各コードが独立国か（`sovereign`）。EXCLUDE の「非独立」の照合に使う | Natural Earth 10m admin-0 countries（v5.1.1）から `build_m49_sovereignty_ne.py` で作成。2026-10-26 | `5ac2164736bcb33467b19e20fad21ef194c2c0107f7fd42317158b893e4e58a5` |
| `comtrade_partner_notes.csv` | Comtrade の相手国コードの名前と注記（CODE_FIX と EXCLUDE に関わる15コードだけ） | https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json（2026-10-26 取得。元ファイル sha256 `2da5667693b5a7f8b203028964a431cdb46356d3a377c7369bb9736c59f03733`）から抜き出し | — |
| `region_shrink_baci2022.csv` | アフリカを旧定義の20か国にしたときと、M49 の54か国のときの地域間貿易額（十億ドル） | CEPII BACI HS22 V202601 の2022年から `measure_region_shrink.py` で作成 | — |
| `africa_top20_baci2022.csv` | アフリカ各国の、西・南アジアとの貿易額の順位と、旧定義の20か国に入っていたか | 同上 | — |
| `regions4_2022.yml` | 採点用の不変条件（12フロー・4地域・桁） | — | — |

- `fetch.py` の `check_regions` は `m49_overview.csv` の sha256 と行数を確かめる。表を差し替えたら、この README と
  `fetch.py` の `M49_SHA256`・`M49_ROWS` を一緒に直す。
- `m49_sovereignty_ne.csv` の「独立国」は Natural Earth の判断（TYPE と SOVEREIGNT）による。国連加盟国の一覧ではない。
- BACI は輸出入を突き合わせて組み直した値で、Comtrade の輸入側＋鏡像（fetch.py）とは一致しない。
  `region_shrink_baci2022.csv` で言えるのは「同じデータで国の範囲だけを変えるとどれだけ違うか」まで。
- この表ではナミビア（516）の ISO-alpha2 が空欄になっている（作成時に "NA" が欠損として読まれたとみられる）。照合は M49 Code だけで行うので check_regions には影響しない。ISO2 で引くときは注意。fetch.py は `keep_default_na=False` で読む。
