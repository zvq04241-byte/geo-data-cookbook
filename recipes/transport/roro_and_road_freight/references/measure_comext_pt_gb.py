"""recipe.md の Comext 由来の数字を取り直す（2025年・報告国→GB の輸出）。
入力: Comext TRANSPORT_HS の年計 trhs_202552.dat（eurostat/trade_by_transport_mode の fetch.py が落とす）
出力: comext_pt_gb_2025.csv（項目, 値）
"""
import sys, csv
import pandas as pd
dat = sys.argv[1] if len(sys.argv) > 1 else "./data_bulk/eurostat_comext/trhs_202552.dat"
it = pd.read_csv(dat, dtype=str, usecols=["REPORTER","PARTNER","PRODUCT","FLOW","TRANSPORT_MODE","VALUE_EUR","QUANTITY_KG"], chunksize=1_000_000)
d = pd.concat([c[c.REPORTER.isin(["FR","PT","IT"]) & (c.FLOW == "2") & (c.PARTNER == "GB")] for c in it])
d["v"] = pd.to_numeric(d.VALUE_EUR, errors="coerce").fillna(0); d["q"] = pd.to_numeric(d.QUANTITY_KG, errors="coerce").fillna(0)
out = []
t = d[d.PRODUCT == "TOTAL"]
for r in ["FR", "PT"]:
    x = t[t.REPORTER == r].groupby("TRANSPORT_MODE").v.sum(); x = x / x.sum() * 100
    out += [(f"{r}→GB 額の構成比 道路(3)", round(x.get("3", 0), 1)), (f"{r}→GB 額の構成比 鉄道(2)", round(x.get("2", 0), 1))]
p = d[(d.PRODUCT != "TOTAL") & (d.REPORTER == "PT")].copy()
p["hs2"] = p.PRODUCT.str[:2]
g = p.groupby(["hs2", "TRANSPORT_MODE"]).v.sum().unstack(fill_value=0)
for h in ["64", "61"]:
    out.append((f"PT→GB HS{h} 額に占める道路%", round(g.loc[h].get("3", 0) / g.loc[h].sum() * 100, 1)))
rd = p[p.TRANSPORT_MODE == "3"].groupby("PRODUCT")[["v", "q"]].sum().sort_values("v", ascending=False).head(5)
for k, r in rd.iterrows():
    out.append((f"PT→GB 道路 上位 HS6 {k} 額(百万EUR)/単価(EUR/kg)", f"{r.v/1e6:.1f} / {r.v/r.q:.1f}"))
for r in ["PT", "IT"]:
    x = d[(d.REPORTER == r) & (d.PRODUCT == "610910")]
    out.append((f"{r}→GB 610910 全手段の単価(EUR/kg)", round(x.v.sum() / x.q.sum(), 1)))
G = p.groupby("PRODUCT").agg(v=("v", "sum"), q=("q", "sum"))
G["road"] = p[p.TRANSPORT_MODE == "3"].groupby("PRODUCT").v.sum().reindex(G.index).fillna(0) / G.v
G = G[(G.q > 0) & (G.v >= 1e6)]; G["up"] = G.v / G.q
out.append(("PT→GB HS6（額100万EUR以上）品目数", len(G)))
out.append(("単価と道路比率の順位相関（Spearman）", round(G.up.rank().corr(G.road.rank()), 3)))
G["bin"] = pd.qcut(G.up, 4, labels=["1低", "2中低", "3中高", "4高"])
for b, x in G.groupby("bin", observed=True):
    out.append((f"単価四分位 {b} 道路%（額加重）", round((x.road * x.v).sum() / x.v.sum() * 100, 1)))
with open("comext_pt_gb_2025.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f); w.writerow(["item", "value"]); w.writerows(out)
for o in out: print(*o)
