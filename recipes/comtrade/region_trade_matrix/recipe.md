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
「三角貿易フロー図」（3地域を頂点に双方向の矢印の太さで貿易額）等に使う。
既定＝アフリカ・西アジア・南アジア・ヨーロッパの4地域 × 12フロー。各地域は M49 に属する国を全部入れる（下の「範囲の検査」）。

## API情報
- 出典: UN Comtrade Public Preview API（無料・無認証）。`https://comtradeapi.un.org/public/v1/preview/C/A/HS`
- 入力: `reportercode`（M49）, `flowCode`（M=輸入/X=輸出）, `period`, `cmdCode=TOTAL`, `partnerCode`（M49カンマ列）, **`partner2Code=0` & `motCode=0`（集約強制）**
- **二面取得**: 各国の M(輸入) と X(輸出) を両方取る。有向フロー src→dst は、dst 国が輸入報告していれば
  **輸入側**、未報告なら **src の輸出X で鏡像補完**（非報告の産油国などへの流入を取りこぼさない）。

## 使い方
```bash
python fetch.py --year 2022 --output-dir ./output   # 地域は REGIONS を編集（--flow は廃止＝M+X自動）
```
出力: `<date>_region_trade_matrix.csv`（src_region,dst_region,value_usd）＋ detail.csv（method=import/mirror）＋ metadata.json（scope・coverage・non_reporting_members・mirrored_flows・pair_mirrored・reporters_both_empty・valuation_note 付き）。
範囲だけ確かめるときは `python fetch.py --check-only`（取得しない）。

## 範囲の検査（check_regions。取得の前に必ず走る）
- `M49_OF` に書いた地域の国（references/m49_overview.csv）は、**どれか1つの地域か EXCLUDE に、ちょうど1回**現れなければ止まる。
  地域を丸ごと消す・同じ国を2回書く・2地域に入れる・理由なく抜く・Comtrade コードへ写して重なる、のどれでも止まる。
  地域そのものを減らすときは `REGIONS` と `M49_OF` の両方から消す（metadata の `scope` に残る）。
- EXCLUDE の理由は2種類だけ。**「非独立」**は references/m49_sovereignty_ne.csv（Natural Earth で引いた表）で独立国でないもの、
  **「他コードに含む」**は含む側の国が REGIONS にあり、references/comtrade_partner_notes.csv の partnerNote に名前があるもの
  （例: Comtrade 251 の注記 "France, Monaco"、757 "Switzerland, Liechtenstein"、579 "Norway, Svalbard and Jan Mayen"）。
  外した件数と名前は標準出力と metadata の `scope`・`coverage` に出る（既定では14件＝非独立11・他コードに含む3）。
- M49 の表は sha256・行数で版を確かめる（`M49_SHA256`。出典は references/m49_overview.README.md）。
- 壊した入力で止まることを確かめた記録（2026-10-26）: アフリカのキーを消す／ナイジェリアを2回書く／エジプトをヨーロッパにも入れる／
  ナイジェリアを「データが少ない」「非独立」「他コードに含む」で外す／イランを南アジアに残す → いずれも止まる。

参照値（2022, v2＝輸入側＋鏡像補完, 十億ドル）。★**この表は旧い定義（アフリカ・ヨーロッパを20か国に絞った）で取った値で、
地域全体の値ではない**（ハマり所6）。全部の国での Comtrade の値は未取得（2026-10-26 の改修後は取得を回していない）。
| src→dst | 額 | | src→dst | 額 |
|---|---|---|---|---|
| ヨーロッパ→西アジア | 354 | | 西アジア→アフリカ | 119 |
| 西アジア→ヨーロッパ | 339 | | 南アジア→西アジア | 90 |
| **アフリカ→ヨーロッパ** | **320** | | ヨーロッパ→南アジア | 76 |
| 西アジア→南アジア | 226 ←原油 | | アフリカ→西アジア | 61 |
| ヨーロッパ→アフリカ | 203 | | 南アジア→アフリカ | 51 |
| 南アジア→ヨーロッパ | 191 | | アフリカ→南アジア | 50 |

※ この表では アフリカ→ヨーロッパ(320) ＞ ヨーロッパ→アフリカ(203)。全部の国で取った BACI 2022 でも
296 ＞ 218 十億ドルで向きは同じ（references/region_shrink_baci2022.csv）。品目の内訳は TOTAL では分からない。
v1（輸入側のみ・フランス欠落・打切り）ではアフリカ→ヨーロッパが 129 と過小に出ていた（後述ハマり所7〜9）。

## ハマり所（実テストで遭遇）

1. **★インドは Comtrade 独自コード 699（M49 の 356 ではない）**。356 を reporter にすると**全年 0 件**を返し、
   partner に 356 を入れても India ぶんが取れない。**これに気づかず「インドのデータが無い／地域集計が過小」と
   誤判定しがち**（西アジア→南アジアが $216B→$26B 級に化ける）。`CODE_FIX={356:699}` で吸収する。
   - 検算: インド(699)の対UAE輸入2022 ≈ $54B, 対サウジ ≈ $46B, 対イラク ≈ $39B（cmdCode=TOTAL。
     output/20260613_region_trade_matrix_detail.csv と、2026-10-26 の1回の取得で同じ値）。

2. **`partnerCode` の結果に集計値が混じる**。partner には World(0) や地域集計コードの行も返るので、
   **「地域メンバーの国コードのみ採用」**（fixed2reg に入る partner だけ加算）。全行を素朴に sum すると数倍に膨らむ。

3. **500件上限**（preview）。reporter=1国 × partner=数十国なら 500 未満で安全。多reporter×多partnerの
   一括クエリは 500 で頭打ちになるので、**reporter を1国ずつ回す**（本スクリプトの方式）。

4. **最新年は速報で欠損**。2023/2024 は主要国の未報告が多い。**2022 など1〜2年前の確定年**を使う。
   「多少古くてもデータが揃う年」を優先（ユーザー方針 2026-06-12）。

5. **`primaryValue` が None の行**がある（欠損）。`or 0` で握る。

6. **★地域は、属する国を全部入れて定義する。主要国だけで代表させない**（2026-10-26）。以前のこのレシピは
   「主要貿易国で代表させると軽い（裾の小国は誤差）」と書き、アフリカを54か国中20か国にしていた。
   CEPII BACI（HS22 V202601）の2022年で測ると、アフリカと西・南アジアの間の4本の流れは**15〜32%少なく出る**
   （アフリカ→西アジアは 54.4 対 79.5 十億ドル）。選んだ20か国は、西・南アジアとの貿易額の上位20か国でもなかった
   （上位20のうち15か国だけ。トーゴ・ギニア・マリ・コンゴ共和国・ソマリアが抜けていた）。
   測り方と結果: references/measure_region_shrink.py → region_shrink_baci2022.csv・africa_top20_baci2022.csv
   （旧定義の20か国の一覧もスクリプトに残してある。BACI は組み直した値なので、Comtrade の値とは一致しない）。
   誤差ではなく、地域の名前と中身の食い違いである。
   - 国の数が増えると呼び出しが増え、Preview の無料枠に当たる（3地域・80か国の二面取得で `403 Quota Exceeded`）。
     繰り返さず、翌日に続きを取る。範囲を絞るときは、絞ったことを**図の注記と報告に**書く（README だけにしない）。
   - 西アジアにトルコ・イスラエルを含めると「原油」の像が薄まるが、どちらも M49 の Western Asia（145）に含まれる。

7. **★フランスは Comtrade の reporter/partner コードが 251（M49 250 ではない）**。250 だと**全0件**＝
   フランスが丸ごと欠落し、対欧州フローが大幅過小になる（「アフリカが対欧州で大幅赤字」と誤った）。
   `CODE_FIX={356:699, 250:251}` で吸収。新しい欧州国を足すときは 1国 smoke して 0件でないか確認。

8. **★一部の国（France 等）は応答が partner2Code(再輸出元)×motCode(輸送モード)に分解され、500行で打切り**。
   素朴に全行 sum すると mot 別の二重計上、かつ打切りで過小化（両方向に壊れる）。
   → **全リクエストに `partner2Code=0` & `motCode=0` を付け、クリーンな国別集約だけを取得**（France←アフリカ〔旧定義の20か国〕は
   **38.4** 十億。output/20260613_region_trade_matrix_detail.csv）。コード側でも `partner2Code in (0,None) and motCode in (0,None)` で防御フィルタ。

9. **★非報告国は輸入側に出てこない**（アルジェリア12/リビア434/スーダン729/イラク368/カタール634 等は当年の自国
   imports を Comtrade に出さない）。輸入側だけだと「その国へ流入する貿易（◯◯→アフリカ等）」が消える。
   → **鏡像補完**: dst 国が未報告なら src 各国の輸出X（reporter=src, flow=X, partner=dst）で代替する。
   metadata の `non_reporting_members`/`mirrored_flows` に記録。輸入=CIF・鏡像=FOB で評価の基準が違う（差の大きさは測っていない）。
   - 輸入を報告している国でも、ある相手の行が無く、その相手が輸出X で載せていれば、**その組だけ鏡像で埋める**
     （method=mirror_pair。件数と組は metadata の `pair_mirrored`）。
   - M・X とも空の国は `reporters_both_empty` に残す。半分以上が空なら年・コード・クエリの誤りとみて止まる。
     応答に `error` があるとき、500件（上限）に達したときも止まる。

## 効くケース
- 三角貿易フロー図（3地域の双方向）、地域間貿易の比較。
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
