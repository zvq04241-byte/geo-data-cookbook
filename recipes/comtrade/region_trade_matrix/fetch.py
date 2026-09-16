#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — UN Comtrade から「地域間 貿易マトリクス」（複数地域の双方向 輸出/輸入額）を取得。

地域＝国（M49コード）の集合として定義し、地域ペアの貿易額を合算する。
三角貿易フロー図（2009本試地理B型）等に使う。

★この v2 は v1 の3つの致命バグを修正（2026-06-13, 探究6で実害判明）:
  (A) **フランスは Comtrade の reporter/partner コードが 251**（M49 250 では全0件→フランスが丸ごと欠落）。
      → CODE_FIX に 250:251。
  (B) **France 等は応答が partner2Code(再輸出元)×motCode(輸送モード)に分解され、500行で打切り**。
      素朴に全行 sum すると二重計上 or 打切り過小になる。
      → 全リクエストに **partner2Code=0 & motCode=0** を付け、クリーンな国別集約だけを得る。
  (C) **非報告国（アルジェリア/リビア/スーダン等）は輸入側に出てこない**ので、輸入側のみだと
      「その国へ流入する貿易（=◯◯→アフリカ等）」が過小になる（アフリカが見かけ上の大幅赤字に化ける）。
      → **二面取得**（輸入M＋輸出X）。各 dst 国が報告していれば輸入側、未報告なら **鏡像（src の輸出X）** で補完。

出力: <date>_region_trade_matrix.csv （src_region,dst_region,value_usd）＋ detail.csv ＋ _metadata.json

使い方:
    python fetch.py --year 2022 --output-dir ./output
    # 地域定義は REGIONS（下）を編集。既定＝アフリカ/西アジア/南アジア/ヨーロッパ。
"""
import argparse, json, sys, io, csv, hashlib, time, itertools
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

# ★ M49→Comtrade のコード例外（ここに無い国は M49 のまま）
CODE_FIX = {356: 699,   # インド: M49 356 → Comtrade 699
            250: 251}   # フランス: M49 250 → Comtrade 251（モナコ込み。250は全0件）

# 地域定義（M49。主要貿易国で代表させると軽い＝長い裾は誤差）
REGIONS = {
    "南アジア": [356, 586, 50, 144, 524, 4, 462, 64],
    "西アジア": [682, 784, 634, 414, 48, 512, 368, 364, 400, 422, 760, 887, 376, 792],
    "アフリカ": [566, 710, 818, 12, 504, 404, 231, 288, 24, 834, 384, 788, 729, 180, 894, 800, 686, 120, 508, 434],
    "ヨーロッパ": [276, 250, 380, 528, 724, 56, 826, 616, 752, 40, 756, 372, 203, 620, 300, 208, 246, 348, 578, 642],
}


class DataFetchError(Exception):
    pass


def cc(code):
    return CODE_FIX.get(code, code)


def fetch(reporter, flow, partner_codes, year, retries=4):
    """reporter の flow(M=輸入/X=輸出) を partner_codes に絞って取得。
    partner2Code=0 & motCode=0 でクリーンな国別集約だけを得る（再輸出/モード分解と500打切りを回避）。
    - 正常な空応答（その国が当年を未報告）→ [] を返す（非報告として扱う。エラーではない）。
    - ネットワーク失敗が retries 回続いたら DataFetchError（黙って欠損させない＝fail-loud）。
    """
    p = {"reportercode": str(cc(reporter)), "flowCode": flow, "period": str(year),
         "cmdCode": "TOTAL", "partner2Code": "0", "motCode": "0",
         "partnerCode": ",".join(str(cc(c)) for c in partner_codes)}
    url = BASE + "?" + "&".join(f"{k}={v}" for k, v in p.items())
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (region-trade)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read()).get("data", [])
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2.0 * (i + 1))
    raise DataFetchError(f"reporter={reporter} flow={flow}: {last}")


def clean_rows(data, valid_partners):
    """国別集約のみ（partner2=0,mot=0）を {partner_cc: value} に。地域メンバーの相手だけ残す。"""
    out = {}
    for d in data:
        if d.get("partner2Code") not in (0, None):
            continue
        if d.get("motCode") not in (0, None):
            continue
        pc = d.get("partnerCode")
        if pc in valid_partners:
            out[pc] = out.get(pc, 0.0) + (d.get("primaryValue") or 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="2022")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    reg_of = {cc(c): r for r, cs in REGIONS.items() for c in cs}   # Comtradeコード→地域
    all_members = sorted({cc(c) for cs in REGIONS.values() for c in cs})

    # 2面取得: M=各国の輸入, X=各国の輸出（鏡像補完用）
    imports, exports = {}, {}        # reporter_cc -> {partner_cc: value}
    reported_M, reported_X = set(), set()
    for reg, codes in REGIONS.items():
        for c in set(codes):
            rc = cc(c)
            mi = clean_rows(fetch(rc, "M", all_members, args.year), set(all_members))
            imports[rc] = mi
            if mi:
                reported_M.add(rc)
            time.sleep(0.25)
            xe = clean_rows(fetch(rc, "X", all_members, args.year), set(all_members))
            exports[rc] = xe
            if xe:
                reported_X.add(rc)
            time.sleep(0.25)

    # 有向フロー src→dst: dst国が輸入報告していれば輸入側、未報告なら src の輸出X で鏡像補完
    flows, detail, mirrored = {}, [], {}
    for src, dst in itertools.permutations(REGIONS, 2):
        total, mir = 0.0, []
        for d in REGIONS[dst]:
            dcc = cc(d)
            if dcc in reported_M:
                for s in REGIONS[src]:
                    scc = cc(s)
                    v = imports[dcc].get(scc, 0.0)
                    if v:
                        total += v
                        detail.append({"src_iso": scc, "src_region": src, "dst_iso": dcc,
                                       "dst_region": dst, "value_usd": round(v), "method": "import"})
            else:  # 非報告国 → 鏡像（src 各国の対 d 輸出）
                mir.append(dcc)
                for s in REGIONS[src]:
                    scc = cc(s)
                    v = exports.get(scc, {}).get(dcc, 0.0)
                    if v:
                        total += v
                        detail.append({"src_iso": scc, "src_region": src, "dst_iso": dcc,
                                       "dst_region": dst, "value_usd": round(v), "method": "mirror"})
        flows[(src, dst)] = total
        if mir:
            mirrored[f"{src}->{dst}"] = mir

    rows = [{"src_region": s, "dst_region": d, "value_usd": round(flows.get((s, d), 0))}
            for s, d in itertools.permutations(REGIONS, 2)]
    if not any(r["value_usd"] for r in rows):
        raise DataFetchError("全フロー0。CODE_FIX（インド699/フランス251）や年次を確認。")

    nonrep = sorted(set(all_members) - reported_M)
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).strftime("%Y%m%d")
    out = args.output_dir / f"{today}_region_trade_matrix.csv"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=["src_region", "dst_region", "value_usd"])
        w.writeheader(); w.writerows(rows)
    meta = {"source": "UN Comtrade Public Preview（M=輸入側＋X=鏡像補完, partner2=0&mot=0集約）",
            "year": args.year, "regions": {r: cs for r, cs in REGIONS.items()},
            "code_fix": CODE_FIX,
            "non_reporting_members": nonrep,
            "mirrored_flows": mirrored,
            "valuation_note": "輸入側=CIF, 鏡像(輸出側)=FOB。非報告国のみ鏡像で補完（CIF/FOBで数%差）。",
            "csv_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "retrieved_at": datetime.now(JST).isoformat()}
    (args.output_dir / f"{today}_region_trade_matrix_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    detail.sort(key=lambda r: -r["value_usd"])
    det = args.output_dir / f"{today}_region_trade_matrix_detail.csv"
    with open(det, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=["src_iso", "src_region", "dst_iso", "dst_region", "value_usd", "method"])
        w.writeheader(); w.writerows(detail)
    print(f"saved: {out.name} + {det.name}  (detail rows={len(detail)})")
    print(f"非報告国(鏡像補完した dst)={nonrep}")
    if mirrored:
        print(f"鏡像補完したフロー: {mirrored}")
    for r in sorted(rows, key=lambda x: -x["value_usd"]):
        print(f"  {r['src_region']}→{r['dst_region']}: {r['value_usd']/1e9:6.1f} 十億$")


if __name__ == "__main__":
    main()
