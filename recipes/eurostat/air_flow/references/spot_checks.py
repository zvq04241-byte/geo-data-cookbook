# spot_checks_YYYYMMDD.csv の値を取り直す（DE-EG の合計と最大ペア、トルコ国内線、DE-TR）
import json, urllib.request
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
def get(cc, y="2024"):
    d = json.loads(urllib.request.urlopen(f"{API}/avia_par_{cc}?format=JSON&lang=EN&freq=A&unit=PAS&tra_meas=PAS_CRD&time={y}", timeout=120).read())
    p2 = {v: k for k, v in d["dimension"]["airp_pr"]["category"]["index"].items()}
    return [(p2[int(p)].split("_"), v) for p, v in d["value"].items()], d.get("updated")
de, upd = get("de"); deeg = [(c, v) for c, v in de if c[0] == "DE" and c[2] == "EG"]
print("updated", upd, "DE-EG sum", sum(v for _, v in deeg), "max", max(deeg, key=lambda x: x[1]))
tr, _ = get("tr")
print("TR-TR", sum(v for c, v in tr if c[0] == c[2] == "TR"), "TR-DE", sum(v for c, v in tr if c[2] == "DE"))
