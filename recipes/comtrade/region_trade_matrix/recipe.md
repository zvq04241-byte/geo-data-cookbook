---
id: comtrade/region_trade_matrix
api: comtrade
task: 地域間 貿易マトリクス（複数地域の双方向貿易額）
items: [TOTAL（全品目）]
tags: [comtrade, trade, region, matrix, bilateral, flow, triangle, no-auth, rest-api]
summary: UN Comtrade から、国の集合で定義した「地域」どうしの双方向の輸出/輸入額を取得（三角貿易フロー図用）
pattern: live-rest-api + region-aggregation + import-side + mirror-fill + aggregate-filter + code-exception
auth_required: false
verified_at: 2026-06-13
complexity: medium
gotcha_count: 9
---

# comtrade / region_trade_matrix

## 何をする
複数の「地域」（＝国 M49 コードの集合）を定義し、**地域ペアの双方向の貿易額**を取得する。
2009年本試 地理B 型の「三角貿易フロー図」（3地域を頂点に双方向の矢印の太さで貿易額）等に使う。
既定＝アフリカ・西アジア・南アジアの3地域 × 6フロー。

## API情報
- 出典: UN Comtrade Public Preview API（無料・無認証）。`https://comtradeapi.un.org/public/v1/preview/C/A/HS`
- 入力: `reportercode`（M49）, `flowCode`（M=輸入/X=輸出）, `period`, `cmdCode=TOTAL`, `partnerCode`（M49カンマ列）, **`partner2Code=0` & `motCode=0`（集約強制）**
- **二面取得**: 各国の M(輸入) と X(輸出) を両方取る。有向フロー src→dst は、dst 国が輸入報告していれば
  **輸入側**、未報告なら **src の輸出X で鏡像補完**（非報告の産油国などへの流入を取りこぼさない）。

## 使い方
```bash
python fetch.py --year 2022 --output-dir ./output   # 地域は REGIONS を編集（--flow は廃止＝M+X自動）
```
出力: `<date>_region_trade_matrix.csv`（src_region,dst_region,value_usd）＋ detail.csv（method=import/mirror）＋ metadata.json（non_reporting_members・mirrored_flows・valuation_note 付き）。

検証済み参照値（2022, v2＝輸入側＋鏡像補完, 十億ドル）:
| src→dst | 額 | | src→dst | 額 |
|---|---|---|---|---|
| ヨーロッパ→西アジア | 354 | | 西アジア→アフリカ | 119 |
| 西アジア→ヨーロッパ | 339 | | 南アジア→西アジア | 90 |
| **アフリカ→ヨーロッパ** | **320** | | ヨーロッパ→南アジア | 76 |
| 西アジア→南アジア | 226 ←原油 | | アフリカ→西アジア | 61 |
| ヨーロッパ→アフリカ | 203 | | 南アジア→アフリカ | 51 |
| 南アジア→ヨーロッパ | 191 | | アフリカ→南アジア | 50 |

※ **アフリカ→ヨーロッパ(320) ＞ ヨーロッパ→アフリカ(203)** ＝アフリカは対欧州で黒字（原油・天然ガス・金・鉱産資源）。
v1（輸入側のみ・フランス欠落・打切り）では 129 と過小で「アフリカ大幅赤字」に化けていた（後述ハマり所7〜9）。

## ハマり所（実テストで遭遇）

1. **★インドは Comtrade 独自コード 699（M49 の 356 ではない）**。356 を reporter にすると**全年 0 件**を返し、
   partner に 356 を入れても India ぶんが取れない。**これに気づかず「インドのデータが無い／地域集計が過小」と
   誤判定しがち**（西アジア→南アジアが $216B→$26B 級に化ける）。`CODE_FIX={356:699}` で吸収する。
   - 検算: インド(699)の対UAE輸入2022 ≈ $54B, 対サウジ ≈ $46B, 対イラク ≈ $39B（いずれも原油）。

2. **`partnerCode` の結果に集計値が混じる**。partner には World(0) や地域集計コードの行も返るので、
   **「地域メンバーの国コードのみ採用」**（fixed2reg に入る partner だけ加算）。全行を素朴に sum すると数倍に膨らむ。

3. **500件上限**（preview）。reporter=1国 × partner=数十国なら 500 未満で安全。多reporter×多partnerの
   一括クエリは 500 で頭打ちになるので、**reporter を1国ずつ回す**（本スクリプトの方式）。

4. **最新年は速報で欠損**。2023/2024 は主要国の未報告が多い。**2022 など1〜2年前の確定年**を使う。
   「多少古くてもデータが揃う年」を優先（ユーザー方針 2026-06-12）。

5. **`primaryValue` が None の行**がある（欠損）。`or 0` で握る。

6. **地域定義は主要貿易国で代表**させると軽い（裾の小国は誤差）。西アジアにトルコ・イスラエルを含めると
   「原油」の像が薄まるが、地域区分としては正しい。判別図では最大フロー（西ア→南ア＝原油）が支配的なので成立。

7. **★フランスは Comtrade の reporter/partner コードが 251（M49 250 ではない）**。250 だと**全0件**＝
   フランスが丸ごと欠落し、対欧州フローが大幅過小になる（探究6で「アフリカが対欧州で大幅赤字」と誤った）。
   `CODE_FIX={356:699, 250:251}` で吸収。新しい欧州国を足すときは 1国 smoke して 0件でないか確認。

8. **★一部の国（France 等）は応答が partner2Code(再輸出元)×motCode(輸送モード)に分解され、500行で打切り**。
   素朴に全行 sum すると mot 別の二重計上、かつ打切りで過小化（両方向に壊れる）。
   → **全リクエストに `partner2Code=0` & `motCode=0` を付け、クリーンな国別集約だけを取得**（France←アフリカが
   21.2→**38.4** 十億に是正）。コード側でも `partner2Code in (0,None) and motCode in (0,None)` で防御フィルタ。

9. **★非報告国は輸入側に出てこない**（アルジェリア12/リビア434/スーダン729/イラク368/カタール887 等は当年の自国
   imports を Comtrade に出さない）。輸入側だけだと「その国へ流入する貿易（◯◯→アフリカ等）」が消える。
   → **鏡像補完**: dst 国が未報告なら src 各国の輸出X（reporter=src, flow=X, partner=dst）で代替する。
   metadata の `non_reporting_members`/`mirrored_flows` に記録。輸入=CIF・鏡像=FOB の数%差は許容。

## 効くケース
- 三角貿易フロー図（3地域の双方向）、地域間貿易の判別問題。
- 「原油を出す西アジア」「人口大国で輸入する南アジア」「原材料のアフリカ」の非対称を可視化。

## 効かないケース（別レシピ）
- 国×品目の細目 → `comtrade/trade_ranking`。
- 完全な世界全域マトリクス・欠損補完が要る → IMF DOTS / UNCTAD（ただし無料で地域集計は要コードリスト）。

## 規約準拠
- `Path(__file__)` 基点／`encoding="utf-8"`／`newline="\n"`／`DataFetchError`＋リトライ4／
  metadata.json（source/SHA256/non_reporting_members/mirrored_flows/retrieved_at）／`sys.stdout` を utf-8 化。User-Agent 付与。
- **fail-loud**: ネットワーク失敗が続けば `DataFetchError`。空応答(200で data=[])は「その国が未報告」として
  鏡像に回す（黙ってスキップしない）。CLAUDE.md「黙って失敗してリトライを繰り返さない」準拠。

## このレシピを使うLLMへのヒント
- **まず CODE_FIX に インド699・フランス251**。新しい地域・国を足すときは 1国 smoke して 0件返りでないか確認。
- **検算**: 双方向の和が片方向の数倍になっていないか（partner2/mot 二重計上の兆候）。フランス等は
  `partner2Code=0&motCode=0` を付けないと壊れる。
- **対称性チェック**: src→dst が異常に小さいとき、dst が非報告国でないか metadata を見る（鏡像で埋まっているか）。
  産油国（アルジェリア/リビア/イラク/カタール）は輸入を出さないことが多い＝鏡像必須。
