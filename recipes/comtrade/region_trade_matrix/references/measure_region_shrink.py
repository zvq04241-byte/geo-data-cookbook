#!/usr/bin/env python3
"""アフリカを「20か国」に絞った旧定義と、M49 の全54か国とで、地域間の貿易額がどれだけ違うかを測る。

データ: CEPII BACI HS22 V202601（lib.bulk_data の保管庫 cepii_baci が要る）の 2022年、全品目の合計 v（千ドル）。
地域: fetch.py の REGIONS（M49。Comtrade 用のコード例外 CODE_FIX を当てる。BACI も同じ独自コードを使う）。
旧定義のアフリカ20か国は AFRICA_OLD20（このレシピの旧版にあった一覧をそのまま残す）。
BACI は輸出入を突き合わせて組み直した値なので、Comtrade の輸入側＋鏡像（fetch.py）とは一致しない。
ここで言えるのは「同じデータで、国の範囲だけを変えるとどれだけ違うか」まで。

出力: region_shrink_baci2022.csv（流れ・旧定義・全部・捉えた割合）と、
      africa_top20_baci2022.csv（アフリカ各国の、西・南アジアとの貿易額の順位と旧定義に入っていたか）。
実行:
    python measure_region_shrink.py
"""
import sys, zipfile, itertools
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                     # fetch.py
sys.path.insert(0, str(HERE.parents[3] / "scripts"))     # lib
import pandas as pd
from lib.bulk_data import file_path
import fetch

AFRICA_OLD20 = [566, 710, 818, 12, 504, 404, 231, 288, 24, 834, 384, 788, 729, 180, 894, 800, 686, 120, 508, 434]
YEAR = 2022
zp = file_path("cepii_baci", "BACI_HS22_V202601.zip")
z = zipfile.ZipFile(zp)
codes = pd.read_csv(z.open("country_codes_V202601.csv"))
iso3 = dict(zip(codes.country_code, codes.country_iso3))
R = {r: {fetch.cc(c) for c in cs} for r, cs in fetch.REGIONS.items()}
old = dict(R); old["アフリカ"] = {fetch.cc(c) for c in AFRICA_OLD20}
for r, cs in R.items():
    miss = sorted(cs - set(codes.country_code))
    print(f"{r}: {len(cs)} か国、BACI に無いコード {miss}")
d = pd.read_csv(z.open(f"BACI_HS22_Y{YEAR}_V202601.csv"), usecols=["i", "j", "v"])
d = d.groupby(["i", "j"], as_index=False).v.sum()


def F(a, b):
    return d[d.i.isin(a) & d.j.isin(b)].v.sum() / 1e6   # 千ドル → 十億ドル


rows = []
for a, b in itertools.permutations(R, 2):
    if "アフリカ" not in (a, b):
        continue
    x, y = F(old[a], old[b]), F(R[a], R[b])
    rows.append({"flow": f"{a}->{b}", "old20_busd": round(x, 1), "all_busd": round(y, 1),
                 "captured_pct": round(x / y * 100, 1), "short_pct": round(100 - x / y * 100, 1)})
out = pd.DataFrame(rows)
out.to_csv(HERE / "region_shrink_baci2022.csv", index=False, encoding="utf-8", lineterminator="\n")
print(out.to_string(index=False))

asia = R["西アジア"] | R["南アジア"]
t = (d[d.i.isin(R["アフリカ"]) & d.j.isin(asia)].groupby("i").v.sum()
     .add(d[d.j.isin(R["アフリカ"]) & d.i.isin(asia)].groupby("j").v.sum(), fill_value=0)
     .sort_values(ascending=False) / 1e6)
rk = pd.DataFrame({"code": t.index, "iso3": [iso3.get(c) for c in t.index], "busd": t.values.round(1)})
rk["rank"] = range(1, len(rk) + 1)
rk["in_old20"] = rk.code.isin(old["アフリカ"])
rk.to_csv(HERE / "africa_top20_baci2022.csv", index=False, encoding="utf-8", lineterminator="\n")
top = rk[rk["rank"] <= 20]
print("西・南アジアとの貿易の上位20か国のうち旧定義にあった数:", int(top.in_old20.sum()))
print("上位20で旧定義に無い:", top[~top.in_old20][["iso3", "rank"]].values.tolist())
