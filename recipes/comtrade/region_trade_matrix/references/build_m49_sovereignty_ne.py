#!/usr/bin/env python3
"""m49_sovereignty_ne.csv を作る（M49 の各コードが独立国かどうかを Natural Earth で引いた表）。

check_regions が EXCLUDE の「非独立」を照合するのに使う。独立国＝Natural Earth admin-0 で
TYPE が Sovereign country / Country / Sovereignty かつ SOVEREIGNT＝ADMIN の行がそのコードにある。
コードは ISO_N3_EH（無ければ ISO_N3）で M49 Code と突き合わせる。NE に行が無いコード（マヨット等、
宗主国の一部として描かれるもの）は独立国でない扱い。

実行（lib.bulk_data の保管庫にある Natural Earth 10m を使う）:
    python build_m49_sovereignty_ne.py
"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "scripts"))   # ワークスペースの scripts/（lib）
import geopandas as gpd
import pandas as pd
from lib.bulk_data import natural_earth

g = gpd.read_file(natural_earth("ne_10m_admin_0_countries"))


def n3(r):
    for k in ("ISO_N3_EH", "ISO_N3"):
        v = str(r.get(k, "-99"))
        if v not in ("-99", "nan", "None", ""):
            return int(v)
    return None


g["n3"] = g.apply(n3, axis=1)
g["sov"] = g.TYPE.isin(["Sovereign country", "Country", "Sovereignty"]) & (g.SOVEREIGNT == g.ADMIN)
t = pd.read_csv(HERE / "m49_overview.csv", keep_default_na=False, na_values=[""])   # ナミビア "NA" を欠損にしない
rows = []
for _, r in t.iterrows():
    h = g[g.n3 == r["M49 Code"]]
    s = h[h.sov]
    pick = s.iloc[0] if len(s) else (h.iloc[0] if len(h) else None)
    rows.append({"M49 Code": r["M49 Code"], "Country or Area": r["Country or Area"],
                 "ne_admin": None if pick is None else pick.ADMIN,
                 "ne_type": None if pick is None else pick.TYPE,
                 "ne_sovereignt": None if pick is None else pick.SOVEREIGNT,
                 "sovereign": bool(len(s))})
o = pd.DataFrame(rows)
o.to_csv(HERE / "m49_sovereignty_ne.csv", index=False, encoding="utf-8", lineterminator="\n")
print(o.shape, "独立国", int(o.sovereign.sum()), "NE に行なし", int(o.ne_admin.isna().sum()))
