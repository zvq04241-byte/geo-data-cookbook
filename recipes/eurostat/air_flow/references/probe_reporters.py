# 報告国の表の有無を確かめる（EU27＋EFTA＋加盟候補国＋英国。2024年と2023年）。結果は reporters_probe_YYYYMMDD.csv
# status: ok=値あり（n_values=値の数。0なら空）／HTTP404=表が無い（not available for dissemination）
import json, urllib.request, urllib.error, sys
API="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
CC="be bg cz dk de ee ie el es fr hr it cy lv lt lu hu mt nl at pl pt ro si sk fi se is li no ch me mk al rs tr ba ua md ge xk uk".split()
out=[]
for prefix,unit,meas in [("avia_par","PAS","PAS_CRD"),("avia_gor","T","FRM_LD_NLD")]:
  for cc in CC:
    for y in ["2024","2023"]:
      url=f"{API}/{prefix}_{cc}?format=JSON&lang=EN&freq=A&unit={unit}&tra_meas={meas}&time={y}"
      try:
        with urllib.request.urlopen(url,timeout=120) as r: d=json.loads(r.read()); st="ok"; n=len(d.get("value") or {})
      except urllib.error.HTTPError as e: st=f"HTTP{e.code}"; n=0
      except Exception as e: st=type(e).__name__; n=0
      out.append((prefix,cc,y,st,n)); print(prefix,cc,y,st,n,flush=True)
import csv
with open("reporters_probe_" + __import__("datetime").date.today().strftime("%Y%m%d") + ".csv","w",newline="") as f:
  w=csv.writer(f); w.writerow(["dataset","reporter","year","status","n_values"]); w.writerows(out)
