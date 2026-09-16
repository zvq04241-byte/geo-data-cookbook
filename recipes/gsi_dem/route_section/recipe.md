---
id: gsi_dem/route_section
api: gsi_dem
task: 道路・登山道に沿った断面図（縦断面図）を作る
items: [OSM道路取得, networkx経路探索, DEM標高サンプリング, 道路/登山道の線種分け, 地点吹き出し]
tags: [gsi, dem, osm, overpass, networkx, profile, section, hillclimb, exam]
summary: OSM(Overpass)の道路・登山道をnetworkxで経路探索し、地理院DEMで標高をサンプリングして「道路に沿った断面図」を描く。共テ地域調査の自己完結図版向け
pattern: overpass-fetch + networkx-shortest-path + dem-profile
auth_required: false
verified_at: 2026-07-03
complexity: medium
gotcha_count: 8
---

# gsi_dem / route_section

## 何をする
起点→終点の**実際の道路・登山道に沿った**断面図（距離×標高）を描く。
直線断面と違い、ヒルクライムコース・登山道の実態に合う。道路=実線／登山道=破線で区別。

**参照実装**: (非公開)
（松原スポーツ公園→田の原→剣ヶ峰 22km。データ=`data/raw/osm/20260701_*.json`）

## ★ハマり所（全て実際に踏んだ）

1. **Overpass は User-Agent 必須**: 無しだと **406** が返る。
   `requests.get(ep, params={"data":q}, headers={"User-Agent":"..."}, timeout=100)`。
   ミラー（overpass-api.de / kumi.systems / mail.ru）を順に試す。
2. **経路探索の前に連結成分を確認**: 最寄りノードへ雑にスナップすると別成分に落ちて
   `NetworkXNoPath`。**終点と同じ連結成分の中で**起点に最も近いノードへスナップする:
   `comp = nx.node_connected_component(G, end)` → `start = min(comp, key=dist)`。
3. **道路と登山道は種別を分けてグラフ化**: `highway in (path, footway, steps)`＝登山道。
   車道だけで探索→登山道だけで探索→連結、が確実（混成グラフの最短経路は林道へ迂回する）。
4. **DEMのギザつきは軽い移動平均**（5点）で均す。ただし**端点は生値を保持**し、
   山頂など公式値のある点は**公式値で固定**（剣ヶ峰=3067m）。
5. **「大会コース」と断定しない**: OSM最短経路は公式コースと厳密には一致しない。
   注記で「経路はOpenStreetMapを最短経路で結んだもの／公式コースは約XXkm」と開示し、
   公式の距離・獲得標高（主催者発表）を図中に別記する。
6. **施設の位置は実データで検証してから紐づける**: 「経路がスキー場を通る」は
   施設ポリゴン（OSM）と経路の交差判定（shapely, 距離0m）で確認してから描く。
   ※名称の同定に注意（御嶽スキー場=王滝村 vs 御岳ロープウェイ=木曽町の取り違え事故が起源）。
7. **○マーカーに文字を入れない**: 地点記号は白丸のみ、説明は引き出し線の吹き出しへ
   （ユーザーレビューで確定した作法）。吹き出しは `zorder=10`＋`annotation_clip=False` で最前面。
8. **距離換算**: 経度差は `×111320×cos(緯度)`、緯度差は `×110540`（メートル）。

## 出典表記
「経路はOpenStreetMap（○○→○○の道路＋○○登山道）、標高は国土地理院DEM10m。
横軸は地図上の経路長（公式コースは約XXkm）。」

## このレシピを使うLLMへのヒント
- 参照実装をコピーし、起点・終点・地点（ア/イ/ウ）だけ差し替える。
- 経路jsonは `data/raw/osm/YYYYMMDD_*.json` に保存（スクラッチ参照は完成ゲートで落ちる）。
