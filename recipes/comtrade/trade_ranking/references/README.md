# references/ — trade_ranking が使う表

| ファイル | 中身 | 出典・取得 | sha256 |
|---|---|---|---|
| `comtrade_reporters.csv` | Comtrade の reporter コード一覧（255行。id・名前・注記・集計か・有効期間） | https://comtradeapi.un.org/files/v1/app/reference/Reporters.json（2026-10-26 取得。元ファイル sha256 `f2a1d78949089831c1fc7714e009996887db724a8d5a43379cdc37be9449f74b`）を CSV にしたもの | `51a7f7109930dd700e406791499b5a9d89a75c89a52babbf86f0bcaa6c3e8d9b` |
| `japan_hs1001_import_2023_top5.yml` | 採点用の期待値 | — | — |

- `fetch.py` の `check_exporters()` が、`MAJOR_EXPORTERS` の各コードがこの表にあり、期限切れでも集計でもないことを確かめる。
