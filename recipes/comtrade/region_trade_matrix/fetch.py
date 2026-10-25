#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — UN Comtrade から「地域間 貿易マトリクス」（複数地域の双方向 輸出/輸入額）を取得。

地域＝国（M49コード）の集合として定義し、地域ペアの貿易額を合算する。
三角貿易フロー図（3地域を頂点に双方向の矢印）等に使う。

★この v2 は v1 の3つの致命バグを修正（2026-06-13, 実テストで判明）:
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
            250: 251,   # フランス: M49 250 → Comtrade 251（モナコ込み。250は全0件）
            578: 579,   # ノルウェー: M49 578 → Comtrade 579
            756: 757}   # スイス: M49 756 → Comtrade 757（リヒテンシュタイン込み）

# 地域定義（M49）。★地域に属する国を全部入れる。主要国だけで代表させない（2026-10-26）。
#   アフリカを20か国にすると、アフリカと西・南アジアの間の流れが少なく出る
#   （2022年 BACI で測った値は references/region_shrink_baci2022.csv。測り方は references/measure_region_shrink.py）。
#   範囲を絞るなら、絞ったことを図の注記と報告に書く。
#   南アジアは M49 だとイランを含む（references/m49_overview.csv で Sub-region Code=34）が、
#   日本の地理の慣習に合わせてイランは西アジアに入れる。
REGIONS = {
    # 南アジア 8か国（M49 からイランを除く）
    "南アジア": [4, 50, 64, 144, 356, 462, 524, 586],
    # 西アジア 19か国（M49 の18か国＋イラン）
    "西アジア": [31, 48, 51, 196, 268, 275, 364, 368, 376, 400, 414, 422, 512, 634, 682, 760, 784, 792, 887],
    # アフリカ 54か国（M49 のアフリカの独立国。島国のモーリシャス 480・セーシェル 690 を落とさない）
    "アフリカ": [12, 24, 72, 108, 120, 132, 140, 148, 174, 178, 180, 204, 226, 231, 232, 262, 266, 270, 288,
                 324, 384, 404, 426, 430, 434, 450, 454, 466, 478, 480, 504, 508, 516, 562, 566, 624, 646,
                 678, 686, 690, 694, 706, 710, 716, 728, 729, 748, 768, 788, 800, 818, 834, 854, 894],
    # ヨーロッパ 43か国（M49 のヨーロッパの独立国。ロシア・バチカンを含む。モナコ・リヒテンシュタインは
    #   Comtrade の 251・757 に含まれるので EXCLUDE に「他コードに含む」で書く）
    "ヨーロッパ": [8, 20, 40, 56, 70, 100, 112, 191, 203, 208, 233, 246, 250, 276, 292, 300, 336, 348, 352, 372,
                   380, 428, 440, 442, 470, 498, 499, 528, 578, 616, 620, 642, 643, 674, 688, 703, 705, 724,
                   752, 756, 804, 807, 826],
}


# ★範囲の検査（2026-10-26）。REGIONS を国連の地域区分（M49。references/m49_overview.csv）と突き合わせる。
#   M49_OF に書いた地域の国は、どれか1つの地域か EXCLUDE に「ちょうど1回」現れなければ止める
#   （地域ごと消す・同じ国を2回書く・2地域に入れる・理由なく抜く、のどれでも止まる）。
#   結果は metadata の scope と coverage に残す。
M49_OF = {"アフリカ": ("Region Code", 2), "ヨーロッパ": ("Region Code", 150),
          "西アジア": ("Sub-region Code", 145), "南アジア": ("Sub-region Code", 34)}
MOVED = {364: ("南アジア", "西アジア")}   # イラン: M49 は南アジア。日本の地理の慣習で西アジアに入れる
# M49 の表の版。表を差し替えたら references/README.md と一緒にここを書き換える。
M49_SHA256 = "ccfd0a7b9b406b7b75bdfb4725af35adcca88e6102898401c46e29a796656037"
M49_ROWS = 248
# M49 にあるが REGIONS に入れないもの。理由は次の2種類だけ（それ以外は止まる）:
#   "非独立"        : 独立国でない地域（属領・海外県・自治領・国連の非自治地域）。
#                     references/m49_sovereignty_ne.csv（Natural Earth で引いた表）で sovereign=False のものだけ
#   "他コードに含む": Comtrade では別の国のコードに含まれる。含む側（M49）を書き、
#                     references/comtrade_partner_notes.csv の partnerNote に名前があることを確かめる
EXCLUDE_KINDS = ("非独立", "他コードに含む")
EXCLUDE = {   # code: (種類, 含む側の M49 か None, 説明)
    732: ("非独立", None, "西サハラ: 国連の非自治地域（Comtrade には相手国コード 732 がある）"),
    86: ("非独立", None, "英領インド洋地域: 英の属領"),
    260: ("非独立", None, "仏領南方・南極地域: 仏の属領（定住人口なし）"),
    175: ("非独立", None, "マヨット: 仏の海外県"),
    638: ("非独立", None, "レユニオン: 仏の海外県"),
    654: ("非独立", None, "セントヘレナ: 英の属領"),
    248: ("非独立", None, "オーランド: フィンランドの自治領"),
    234: ("非独立", None, "フェロー諸島: デンマークの自治領"),
    831: ("非独立", None, "ガーンジー: 英王室属領"),
    833: ("非独立", None, "マン島: 英王室属領"),
    832: ("非独立", None, "ジャージー: 英王室属領"),
    744: ("他コードに含む", 578, "スヴァールバル・ヤンマイエン: Comtrade のノルウェー 579 に含まれる"),
    438: ("他コードに含む", 756, "リヒテンシュタイン: Comtrade のスイス 757 に含まれる"),
    492: ("他コードに含む", 250, "モナコ: Comtrade のフランス 251 に含まれる（Comtrade の 492 は Europe EU, nes で別物）"),
}
# 「他コードに含む」の照合に使う名前（partnerNote に現れる英語名）
EXCLUDE_NOTE_NAME = {744: "Svalbard", 438: "Liechtenstein", 492: "Monaco"}


def _ref(name):
    return Path(__file__).resolve().parent / "references" / name


def load_m49():
    """M49 の表を読み、版（sha256・行数・列・コードの一意）を確かめる。"""
    import pandas as pd
    p = _ref("m49_overview.csv")
    h = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()   # 改行は LF にそろえて測る（Windows の自動変換対策）
    if h != M49_SHA256:
        raise SystemExit(f"★M49 の表が記録した版と違う（sha256 {h[:16]}…）。差し替えたなら README と M49_SHA256 を直す")
    # ★ナミビアの ISO-alpha2 "NA" を欠損にしない（照合は M49 Code だけだが、表を他の列で使うときのため）
    t = pd.read_csv(p, keep_default_na=False, na_values=[""])
    need = {"M49 Code", "Country or Area", "Region Code", "Sub-region Code"}
    if not need <= set(t.columns) or len(t) != M49_ROWS or not t["M49 Code"].is_unique:
        raise SystemExit(f"★M49 の表の形が違う（行 {len(t)}／期待 {M49_ROWS}、列 {sorted(need - set(t.columns))} が無い、または重複）")
    return t


def check_regions():
    import pandas as pd
    t = load_m49()
    name = dict(zip(t["M49 Code"].astype(int), t["Country or Area"]))
    problems = []
    # 1) 地域の名前: REGIONS と M49_OF は同じ地域の集まりでなければならない（地域ごと消す・足すを止める）
    for reg in REGIONS:
        if reg not in M49_OF:
            problems.append(f"{reg}: M49 との対応（M49_OF）が無い。地域を足すなら対応を書く")
    for reg in M49_OF:
        if reg not in REGIONS:
            problems.append(f"{reg}: M49_OF にあるのに REGIONS に無い。地域を外すなら M49_OF からも外す（出力の scope に残る）")
    # 2) 各地域の期待集合（M49。MOVED を当てたもの）
    expect = {}
    for reg, (col, val) in M49_OF.items():
        m = set(t.loc[t[col] == val, "M49 Code"].astype(int))
        expect[reg] = {c for c in m if MOVED.get(c, (None,))[0] != reg} | {c for c, (a, b) in MOVED.items() if b == reg}
    universe = set().union(*expect.values()) if expect else set()
    # 3) EXCLUDE の理由の種類と、含む側の照合
    import csv as _csv
    notes = {int(r["id"]): r["partnerNote"] for r in _csv.DictReader(open(_ref("comtrade_partner_notes.csv"), encoding="utf-8"))}
    sov = {int(r["M49 Code"]): r["sovereign"] == "True"
           for r in _csv.DictReader(open(_ref("m49_sovereignty_ne.csv"), encoding="utf-8"))}
    in_regions = {c for cs in REGIONS.values() for c in cs}
    used_ex = {c: v for c, v in EXCLUDE.items() if c in universe}   # 選んだ地域に関わる EXCLUDE だけ数える
    for c, v in used_ex.items():
        kind, host, _ = v
        if kind not in EXCLUDE_KINDS:
            problems.append(f"EXCLUDE {c}: 理由の種類「{kind}」は使えない（{EXCLUDE_KINDS} のどれか）")
        if kind == "非独立" and sov.get(c, True):
            problems.append(f"EXCLUDE {c} {name.get(c)}: 「非独立」としたが m49_sovereignty_ne.csv では独立国")
        if kind == "他コードに含む":
            nm = EXCLUDE_NOTE_NAME.get(c)
            if host not in in_regions:
                problems.append(f"EXCLUDE {c}: 含む側 {host} が REGIONS に無い")
            elif not nm or nm not in notes.get(cc(host), ""):
                problems.append(f"EXCLUDE {c}: Comtrade {cc(host)} の partnerNote に {nm} が無い（含まれると確かめられない）")
        elif host is not None:
            problems.append(f"EXCLUDE {c}: 「{kind}」に含む側は書かない")
    # 4) M49 の側から: universe の各国が、どれか1地域か EXCLUDE にちょうど1回
    count = {}
    for reg, cs in REGIONS.items():
        for c in cs:
            count.setdefault(c, []).append(reg)
    for c in used_ex:
        count.setdefault(c, []).append("EXCLUDE")
    for c in sorted(universe):
        where = count.get(c, [])
        if len(where) == 0:
            problems.append(f"{c} {name.get(c)}: どの地域にも EXCLUDE にも無い")
        elif len(where) > 1:
            problems.append(f"{c} {name.get(c)}: {len(where)} 回現れる {where}")
    # 5) 各地域の側から: 入れた国は、その地域の M49 にある
    for reg, cs in REGIONS.items():
        if reg in expect:
            extra = sorted(set(cs) - expect[reg])
            if extra:
                problems.append(f"{reg}: M49 のこの地域に無いのに入っている {[(c, name.get(c)) for c in extra]}")
    # 6) Comtrade コードへ写したあとも重複しない（CODE_FIX の衝突）
    ccs = [cc(c) for cs in REGIONS.values() for c in cs]
    if len(ccs) != len(set(ccs)):
        problems.append(f"Comtrade コードへ写すと重複する {sorted({x for x in ccs if ccs.count(x) > 1})}")
    if problems:
        raise SystemExit("★地域の範囲が国連の区分と合わない。主要国だけで代表させない:\n  " + "\n  ".join(problems))
    cover = {}
    for reg, cs in REGIONS.items():
        col, val = M49_OF[reg]
        ex = {c: f"{EXCLUDE[c][0]}: {EXCLUDE[c][2]}" for c in sorted(expect[reg] & set(EXCLUDE))}
        cover[reg] = {"入れた": len(cs), "M49の数（区分どおり）": int((t[col] == val).sum()),
                      "M49の数（MOVED後）": len(expect[reg]), "外したもの": ex}
        print(f"  範囲 {reg}: {len(cs)}/{len(expect[reg])}（外した {len(ex)}: {'、'.join(v.split(': ')[1] for v in ex.values()) or 'なし'}）")
    kinds = {k: sum(1 for v in used_ex.values() if v[0] == k) for k in EXCLUDE_KINDS}
    scope = ("M49 の" + "・".join(REGIONS) + "に属する国を全部（イランは西アジアへ移す）。外したもの "
             + f"{len(used_ex)} 件（" + "、".join(f"{k} {n}" for k, n in kinds.items()) + "）")
    return scope, cover


class DataFetchError(Exception):
    pass


def cc(code):
    return CODE_FIX.get(code, code)


def fetch(reporter, flow, partner_codes, year, retries=4):
    """reporter の flow(M=輸入/X=輸出) を partner_codes に絞って取得。
    partner2Code=0 & motCode=0 でクリーンな国別集約だけを得る（再輸出/モード分解と500打切りを回避）。
    - 正常な空応答（その国が当年を未報告）→ [] を返す（非報告として扱う）。ただし応答に error があれば止める。
      全 reporter の半分以上が M・X とも空なら、クエリ自体の誤りとみて main が止める。
    - 500件（Preview の上限）に達した応答は打切りの恐れがあるので止める。
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
                js = json.loads(r.read())
            break
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2.0 * (i + 1))
    else:
        raise DataFetchError(f"reporter={reporter} flow={flow}: {last}")
    if js.get("error"):
        raise DataFetchError(f"reporter={reporter} flow={flow}: 応答に error: {js.get('error')}")
    data = js.get("data") or []
    if len(data) >= 500:
        raise DataFetchError(f"reporter={reporter} flow={flow}: {len(data)} 件＝上限に達した（打切りの恐れ）")
    return data


def clean_rows(data, valid_partners):
    """国別集約のみ（partner2=0,mot=0）を {partner_cc: value} に。地域メンバーの相手だけ残す。"""
    out, seen = {}, {}
    for d in data:
        if d.get("partner2Code") not in (0, None):
            continue
        if d.get("motCode") not in (0, None):
            continue
        pc = d.get("partnerCode")
        if pc in valid_partners:
            # ★同じ（報告国, 相手国）が2行返ったら止める（2026-10-26）。2026-06 の取得では南アフリカ等5か国の輸入が
            #   2行ずつ返り、足し込んで2倍に数えていた（インド→南アフリカ 166.7億ドル。今は1行で 83.3億ドル）。
            key = (d.get("reporterCode"), pc)
            if key in seen:
                raise DataFetchError(f"同じ組が2行: reporter={key[0]} partner={pc} "
                                     f"({seen[key]} と {d.get('classificationCode')}/{d.get('customsCode')})。足すと二重計上になる")
            seen[key] = f"{d.get('classificationCode')}/{d.get('customsCode')}"
            out[pc] = out.get(pc, 0.0) + (d.get("primaryValue") or 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="2022")
    ap.add_argument("--output-dir", type=Path, default=Path("./output"))
    ap.add_argument("--check-only", action="store_true", help="範囲の検査（check_regions）だけ行い、取得しない")
    args = ap.parse_args()
    scope, coverage = check_regions()
    print(f"  scope: {scope}")
    if args.check_only:
        return
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
    # M・X とも空の国（未報告か、コードの誤り）。半分以上なら、クエリ自体の誤りとみて止める
    both_empty = sorted(set(imports) - reported_M - reported_X)
    if len(both_empty) * 2 >= len(imports):
        raise DataFetchError(f"M・X とも空の国が {len(both_empty)}/{len(imports)}。年・コード・クエリを確認: {both_empty}")

    # 有向フロー src→dst: dst国が輸入報告していれば輸入側、未報告なら src の輸出X で鏡像補完
    flows, detail, mirrored, pair_mirrored = {}, [], {}, []
    for src, dst in itertools.permutations(REGIONS, 2):
        total, mir = 0.0, []
        for d in REGIONS[dst]:
            dcc = cc(d)
            if dcc in reported_M:
                for s in REGIONS[src]:
                    scc = cc(s)
                    v = imports[dcc].get(scc, 0.0)
                    method = "import"
                    if not v:
                        # dst は輸入を報告しているが、この相手が無い → 相手の輸出X があれば相手ごとに鏡像で埋める
                        v = exports.get(scc, {}).get(dcc, 0.0)
                        method = "mirror_pair"
                        if v:
                            pair_mirrored.append(f"{scc}->{dcc}")
                    if v:
                        total += v
                        detail.append({"src_iso": scc, "src_region": src, "dst_iso": dcc,
                                       "dst_region": dst, "value_usd": round(v), "method": method})
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

    # detail と地域間の合計が一致するか（丸め誤差だけ許す）
    for (s_, d_), v in flows.items():
        dv = sum(r["value_usd"] for r in detail if r["src_region"] == s_ and r["dst_region"] == d_)
        if abs(dv - v) > len(detail) + 1:
            raise DataFetchError(f"{s_}->{d_}: detail の合計 {dv} と集計 {v} が合わない")
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
            "scope": scope,
            "coverage": coverage,
            "code_fix": CODE_FIX,
            "non_reporting_members": nonrep,
            "mirrored_flows": mirrored,
            "pair_mirrored": {"count": len(pair_mirrored), "pairs": pair_mirrored},
            "reporters_both_empty": both_empty,
            "valuation_note": "輸入側=CIF, 鏡像(輸出側)=FOB で評価の基準が違う。非報告国（と、報告国が載せていない相手）だけ鏡像で補完。差の大きさは測っていない。",
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
    print(f"相手ごとに鏡像で埋めた組: {len(pair_mirrored)}  M・X とも空の国: {both_empty}")
    for r in sorted(rows, key=lambda x: -x["value_usd"]):
        print(f"  {r['src_region']}→{r['dst_region']}: {r['value_usd']/1e9:6.1f} 十億$")


if __name__ == "__main__":
    main()
