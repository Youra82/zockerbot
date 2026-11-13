import time, itertools, numpy as np, pandas as pd
from numba import njit
from features import build
B = "kerzen"
D = "."
COINS = ["XRPUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT", "AVAXUSDT", "ARBUSDT"]
CONF = [(20, 0.025), (20, 0.05), (20, 0.10), (10, 0.05), (10, 0.10)]
CUT = int(pd.Timestamp("2024-01-01").value//10**6)
t0 = time.time()
masks = None; coin = []; tent = []; Wl = [[] for _ in CONF]; Ws = [[] for _ in CONF]; Xl = [[] for _ in CONF]; Xs = [[] for _ in CONF]
for ci, s in enumerate(COINS):
    df = pd.read_parquet(f"{B}/ohlcv_15m/{s}.parquet")
    C = build(df)
    z = np.load(f"{D}/labels/{s}.npz")
    assert len(z["t15"]) == len(df)
    if masks is None: names = list(C); masks = {k: ([], []) for k in names}
    for k in names: masks[k][0].append(C[k][0]); masks[k][1].append(C[k][1])
    coin.append(np.full(len(df), ci, np.int16)); tent.append(z["t15"] + 15*60_000)
    for j, (lev, tp) in enumerate(CONF):
        key = f"L{lev}_T{int(tp*1000)}"
        Wl[j].append(z[f"w_{key}_L"]); Ws[j].append(z[f"w_{key}_S"]); Xl[j].append(z[f"x_{key}_L"]); Xs[j].append(z[f"x_{key}_S"])
    print("Features", s, f"{time.time()-t0:.0f}s", flush=True)
names = list(masks)
ML = np.stack([np.concatenate(masks[k][0]) for k in names]); MS = np.stack([np.concatenate(masks[k][1]) for k in names]); del masks
coin = np.concatenate(coin); tent = np.concatenate(tent)
W = np.stack([np.stack([np.concatenate(Wl[j]), np.concatenate(Ws[j])]) for j in range(len(CONF))])
X = np.stack([np.stack([np.concatenate(Xl[j]), np.concatenate(Xs[j])]) for j in range(len(CONF))])
del Wl, Ws, Xl, Xs
TPs = np.array([c[1] for c in CONF]); LEVs = np.array([c[0] for c in CONF], np.float64)
FG = np.array([0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.075, 0.09, 0.1, 0.125, 0.15, 0.175, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0])
DAYS_TR = (CUT - tent.min())/86400000.0; DAYS_TE = (tent.max() - CUT)/86400000.0
print("Bedingungen:", len(names), "Bars:", len(coin), f"Tage train {DAYS_TR:.0f} test {DAYS_TE:.0f}", flush=True)

@njit(cache=True)
def sim(idx, sd, coin, tent, W, X, TPs, LEVs, FG, cut, dtr, dte):
    nc = W.shape[0]; out = np.full((nc, 9), np.nan)
    rtr = np.empty(len(idx)); rte = np.empty(len(idx))
    for j in range(nc):
        ntr = 0; nte = 0; wtr = 0; wte = 0; busy = -1; lastc = -1
        for q in range(len(idx)):
            i = idx[q]
            if coin[i] != lastc: busy = -1; lastc = coin[i]
            if tent[i] < busy: continue
            s = 0 if sd[q] > 0 else 1
            w = W[j, s, i]
            if w < 0: continue
            xt = X[j, s, i]; busy = xt
            if w == 1:
                hold = (xt - tent[i])/28800000.0
                r = TPs[j]*LEVs[j] - 0.0008*LEVs[j] - 0.0001*hold*LEVs[j]*(1.0 if s == 0 else -1.0)
            else:
                r = -1.0
            if tent[i] < cut:
                rtr[ntr] = r; ntr += 1; wtr += w
            else:
                rte[nte] = r; nte += 1; wte += w
        out[j, 0] = ntr; out[j, 1] = nte
        if ntr > 0: out[j, 2] = wtr/ntr
        if nte > 0: out[j, 3] = wte/nte
        bg = -1e18; bf = 0.0
        for f in FG:
            g = 0.0
            for q in range(ntr):
                v = 1.0 + f*rtr[q]
                if v <= 0: g = -1e18; break
                g += np.log(v)
            if g > bg: bg = g; bf = f
        out[j, 4] = bf; out[j, 5] = bg/dtr
        g = 0.0
        for q in range(nte):
            v = 1.0 + bf*rte[q]
            if v <= 0: g = -1e18; break
            g += np.log(v)
        out[j, 6] = g/dte
        # Durchschnitt je Trade (Edge) train/test
        s1 = 0.0
        for q in range(ntr): s1 += rtr[q]
        out[j, 7] = s1/ntr if ntr > 0 else np.nan
        s2 = 0.0
        for q in range(nte): s2 += rte[q]
        out[j, 8] = s2/nte if nte > 0 else np.nan
    return out

rows = []
N = len(names)
combos = [(a,) for a in range(N)] + list(itertools.combinations(range(N), 2)) + list(itertools.combinations(range(N), 3))
print("Kombinationen:", len(combos), flush=True)
for ci, cb in enumerate(combos):
    L = ML[cb[0]].copy(); S = MS[cb[0]].copy()
    for k in cb[1:]: L &= ML[k]; S &= MS[k]
    for mode in ("Long", "Short", "beide"):
        if mode == "Long": sel = L
        elif mode == "Short": sel = S
        else: sel = L ^ S
        idx = np.flatnonzero(sel)
        if len(idx) < 200: continue
        sd = np.where(L[idx], 1, -1).astype(np.int8)
        o = sim(idx, sd, coin, tent, W, X, TPs, LEVs, FG, CUT, DAYS_TR, DAYS_TE)
        for j in range(len(CONF)):
            if o[j, 0] >= 150 and o[j, 1] >= 50:
                rows.append((" + ".join(names[k] for k in cb), mode, CONF[j][0], CONF[j][1], *o[j]))
    if ci % 2000 == 0: print(f"{ci}/{len(combos)} {time.time()-t0:.0f}s Treffer {len(rows)}", flush=True)
cols = ["regel", "richtung", "hebel", "tp", "n_tr", "n_te", "wr_tr", "wr_te", "f", "g_tr", "g_te", "edge_tr", "edge_te"]
res = pd.DataFrame(rows, columns=cols)
res.to_parquet(f"{D}/search_result.parquet")
print("FERTIG", len(res), f"{time.time()-t0:.0f}s", flush=True)
