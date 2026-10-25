"""FancyArrowPatch の矢じりの先端が目標からどれだけ手前に落ちるかを画素で測る（2026-10-26）。
条件: 図幅13.2インチ・BBOX(-95,-58,180,78)・ax_rect(0.012,0.085,0.976,0.845)・lw=8・dpi=100・
起点(117,-22)→目標(118,33)。目標にいちばん近い濃い画素までの距離（度）を出す。
結果（matplotlib 3.x, 2026-10-26）:
  mutation_scale=27.9 shrinkB=2(既定)  2.73度
  mutation_scale=27.9 shrinkB=0        1.88度
  mutation_scale=27.9 shrinkB=-10      5.87度  ← 負にしても届かない（むしろ遠のいた）
"""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np
from matplotlib.patches import FancyArrowPatch
BBOX = (-95, -58, 180, 78)
for ms, shB in ((27.9, 2), (27.9, 0), (27.9, -10)):
    h = 13.2 * (BBOX[3]-BBOX[1]) / (BBOX[2]-BBOX[0]) / 0.976 * 0.845
    fig = plt.figure(figsize=(13.2, h), dpi=100)
    ax = fig.add_axes((0.012, 0.085, 0.976, 0.845)); ax.set_xlim(BBOX[0], BBOX[2]); ax.set_ylim(BBOX[1], BBOX[3]); ax.axis("off")
    A, B = (117, -22), (118, 33)
    ax.add_patch(FancyArrowPatch(A, B, arrowstyle="-|>", mutation_scale=ms, shrinkA=0, shrinkB=shB, lw=8, color="k"))
    fig.canvas.draw(); a = np.asarray(fig.canvas.buffer_rgba())[:, :, 0]
    yy, xx = np.where(a < 128); pts = ax.transData.inverted().transform(np.c_[xx, a.shape[0]-yy])
    print(ms, shB, round(float(np.hypot(pts[:, 0]-B[0], pts[:, 1]-B[1]).min()), 2)); plt.close(fig)
