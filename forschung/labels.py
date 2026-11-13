"""Labels je 15m-Einstieg: TP vor Liquidation? fuer Long/Short und mehrere (Hebel, TP)-Paare, Pfad auf 1m."""
import sys, time, numpy as np, pandas as pd
from numba import njit
SYM = sys.argv[1]
B = "kerzen"
OUT = "labels"
CONF = [(20, 0.025), (20, 0.05), (20, 0.10), (10, 0.05), (10, 0.10)]
BS = 512
t0 = time.time()
m1 = pd.read_parquet(f"{B}/ohlcv_1m/{SYM}.parquet", columns=["open_time", "open", "high", "low"])
t1 = m1.open_time.values.astype(np.int64); O = m1.open.values.astype(np.float64)
Hh = m1.high.values.astype(np.float64); Ll = m1.low.values.astype(np.float64)
del m1
m15 = pd.read_parquet(f"{B}/ohlcv_15m/{SYM}.parquet", columns=["open_time"])
t15 = m15.open_time.values.astype(np.int64)
ent = np.searchsorted(t1, t15 + 15*60_000)          # erster 1m-Bar nach 15m-Schluss
nb = (len(Hh) + BS - 1)//BS
bmax = np.array([Hh[i*BS:(i+1)*BS].max() for i in range(nb)])
bmin = np.array([Ll[i*BS:(i+1)*BS].min() for i in range(nb)])

@njit(cache=True)
def first_up(H, bmax, s, lvl, BS):
    n = len(H); b = s//BS; e = min((b+1)*BS, n)
    for j in range(s, e):
        if H[j] >= lvl: return j
    for bb in range(b+1, len(bmax)):
        if bmax[bb] >= lvl:
            for j in range(bb*BS, min((bb+1)*BS, n)):
                if H[j] >= lvl: return j
    return -1

@njit(cache=True)
def first_dn(L, bmin, s, lvl, BS):
    n = len(L); b = s//BS; e = min((b+1)*BS, n)
    for j in range(s, e):
        if L[j] <= lvl: return j
    for bb in range(b+1, len(bmin)):
        if bmin[bb] <= lvl:
            for j in range(bb*BS, min((bb+1)*BS, n)):
                if L[j] <= lvl: return j
    return -1

@njit(cache=True)
def label(ent, O, H, L, bmax, bmin, tp, liq, side, BS):
    n = len(ent); win = np.full(n, -1, np.int8); ex = np.full(n, -1, np.int64)
    for k in range(n):
        s = ent[k]
        if s >= len(O): continue
        px = O[s]
        if side > 0:
            a = first_up(H, bmax, s, px*(1+tp), BS); b = first_dn(L, bmin, s, px*(1-liq), BS)
        else:
            a = first_dn(L, bmin, s, px*(1-tp), BS); b = first_up(H, bmax, s, px*(1+liq), BS)
        if a == -1 and b == -1: continue
        if b != -1 and (a == -1 or b <= a): win[k] = 0; ex[k] = b
        else: win[k] = 1; ex[k] = a
    return win, ex

res = {"t15": t15}
for lev, tp in CONF:
    liq = 1/lev - 0.005
    for side in (1, -1):
        w, x = label(ent, O, Hh, Ll, bmax, bmin, tp, liq, side, BS)
        key = f"L{lev}_T{int(tp*1000)}_{'L' if side > 0 else 'S'}"
        xt = np.where(x >= 0, t1[np.clip(x, 0, None)], -1)
        res["w_"+key] = w; res["x_"+key] = xt
np.savez_compressed(f"{OUT}/{SYM}.npz", **res)
print(f"{SYM} fertig in {time.time()-t0:.0f}s, {len(t15)} Einstiege", flush=True)
