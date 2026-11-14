"""Verbesserung „Rücksetzer im Ausbruch“: Parameter-Gitter + Marktphasen-Filter + Hebel/TP.
Auswahl NUR auf Coin-Gruppe A, 2021-2023. Gegenprobe: A 2024-2026 und Gruppe B (ganz)."""
import glob, os, time, itertools
import numpy as np, pandas as pd
from numba import njit
D = os.path.dirname(os.path.abspath(__file__))
K = os.path.join(D, "kerzen40", "ohlcv_15m")
CUT = int(pd.Timestamp("2024-01-01").value // 10**6)
CONF = [(lev, tp) for lev in (10, 15, 20) for tp in (0.03, 0.05, 0.075, 0.10)]
RSI15 = (25, 30, 35); DAYRSI = (60, 65, 70, 75); DON = (10, 20, 40)
FILTERS = ("ohne", "BTC-Trend", "4h-Trend", "breit", "schmal")
t0 = time.time()

def rsi(c, n=14):
    d = c.diff(); g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean(); l = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))

@njit(cache=True)
def label(o, h, l, tp, liq, side, U):
    n = len(o); win = np.full(len(U), -1, np.int8); ex = np.full(len(U), -1, np.int64)
    for u in range(len(U)):
        k = U[u]
        if k >= n - 1: continue
        px = o[k+1]
        if side > 0: up = px*(1+tp); dn = px*(1-liq)
        else: up = px*(1+liq); dn = px*(1-tp)
        for j in range(k+1, n):
            hu = h[j] >= up; hd = l[j] <= dn
            if hu or hd:
                if side > 0: w = 1 if (hu and not hd) else 0
                else: w = 1 if (hd and not hu) else 0
                win[u] = w; ex[u] = j; break
    return win, ex

files = sorted(glob.glob(os.path.join(K, "*.parquet")))
coins = [os.path.basename(f)[:-12] for f in files]
rng = np.random.default_rng(7); perm = rng.permutation(len(coins))
grpA = set(coins[i] for i in perm[: len(coins)//2])
print("Gruppe A:", sorted(grpA)); print("Gruppe B:", sorted(set(coins) - grpA), flush=True)

# BTC-Tagesregime
btc = pd.read_parquet(os.path.join(K, "BTCUSDT.parquet")); btc.index = pd.to_datetime(btc.open_time, unit="ms")
bd = btc.close.resample("1D").last().dropna(); btc_up = (bd > bd.ewm(span=50, adjust=False).mean())
btc_avail = (bd.index + pd.Timedelta(days=1)).values

per = {}   # je Coin: Tages-Signale (Basis) fuer Breite
raw = {}
for f, c in zip(files, coins):
    df = pd.read_parquet(f); df.index = pd.to_datetime(df.open_time, unit="ms")
    day = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    raw[c] = (df, day)
    r = rsi(day.close)
    per[c] = pd.DataFrame({"L": (r > 70) & (day.close > day.high.rolling(20).max().shift(1)),
                           "S": (r < 30) & (day.close < day.low.rolling(20).min().shift(1))})
breadth = pd.concat({c: v for c, v in per.items()}, axis=1)
bL = breadth.xs("L", axis=1, level=1).sum(axis=1); bS = breadth.xs("S", axis=1, level=1).sum(axis=1)

M = {}   # (rsi15, dayrsi, don, filter) -> (long, short) concat
coin_id, tent, isA, W, X = [], [], [], [], []
for ci, c in enumerate(coins):
    df, day = raw[c]
    close_t = (df.index + pd.Timedelta(minutes=15)).values
    pos = np.searchsorted((day.index + pd.Timedelta(days=1)).values, close_t, side="right") - 1
    ok = pos >= 0; pc = np.clip(pos, 0, None)
    warm = (df.index - df.index[0]) < pd.Timedelta(days=60)
    r15 = rsi(df.close).to_numpy(); rd = rsi(day.close).to_numpy()
    bp = np.searchsorted(btc_avail, close_t, side="right") - 1
    bu = np.where(bp >= 0, btc_up.to_numpy()[np.clip(bp, 0, None)], False); bdn = np.where(bp >= 0, ~btc_up.to_numpy()[np.clip(bp, 0, None)], False)
    h4 = df.close.resample("4h").last().dropna(); e4 = h4.ewm(span=50, adjust=False).mean()
    p4 = np.searchsorted((h4.index + pd.Timedelta(hours=4)).values, close_t, side="right") - 1
    up4 = np.where(p4 >= 0, (h4 > e4).to_numpy()[np.clip(p4, 0, None)], False); dn4 = np.where(p4 >= 0, (h4 < e4).to_numpy()[np.clip(p4, 0, None)], False)
    bl = bL.reindex(day.index).fillna(0).to_numpy()[pc]; bs = bS.reindex(day.index).fillna(0).to_numpy()[pc]
    local = {}
    for don in DON:
        hi = day.high.rolling(don).max().shift(1).to_numpy(); lo = day.low.rolling(don).min().shift(1).to_numpy()
        for dr in DAYRSI:
            dl = ok & (rd[pc] > dr) & (day.close.to_numpy()[pc] > hi[pc]); ds = ok & (rd[pc] < 100-dr) & (day.close.to_numpy()[pc] < lo[pc])
            for r1 in RSI15:
                L0 = dl & (r15 < r1) & ~warm; S0 = ds & (r15 > 100-r1) & ~warm
                for flt in FILTERS:
                    if flt == "ohne": L, S = L0, S0
                    elif flt == "BTC-Trend": L, S = L0 & bu, S0 & bdn
                    elif flt == "4h-Trend": L, S = L0 & up4, S0 & dn4
                    elif flt == "breit": L, S = L0 & (bl >= 3), S0 & (bs >= 3)
                    else: L, S = L0 & (bl <= 2), S0 & (bs <= 2)
                    local[(r1, dr, don, flt)] = (L, S)
    union = np.zeros(len(df), bool)
    for L, S in local.values(): union |= L | S
    U = np.flatnonzero(union); off = sum(len(a) for a in tent)
    for key, (L, S) in local.items():
        M.setdefault(key, ([], []))
        M[key][0].append(off + np.flatnonzero(L[U])); M[key][1].append(off + np.flatnonzero(S[U]))
    del local
    o, h, l = df.open.to_numpy(), df.high.to_numpy(), df.low.to_numpy()
    w = np.zeros((len(CONF), 2, len(U)), np.int8); x = np.zeros((len(CONF), 2, len(U)), np.int64)
    t15 = df.open_time.to_numpy().astype(np.int64)
    for j, (lev, tp) in enumerate(CONF):
        for s_, side in enumerate((1, -1)):
            ww, xx = label(o, h, l, tp, 1/lev - 0.005, side, U)
            w[j, s_] = ww; x[j, s_] = np.where(xx >= 0, t15[np.clip(xx, 0, None)] + 15*60_000, -1)
    W.append(w); X.append(x)
    coin_id.append(np.full(len(U), ci, np.int16)); tent.append(t15[U] + 15*60_000); isA.append(np.full(len(U), c in grpA))
    print(f"{c} fertig {time.time()-t0:.0f}s", flush=True)
coin_id = np.concatenate(coin_id); tent = np.concatenate(tent); isA = np.concatenate(isA)
W = np.concatenate(W, axis=2); X = np.concatenate(X, axis=2)
for k in M: M[k] = (np.concatenate(M[k][0]), np.concatenate(M[k][1]))
NU = len(tent)
TPs = np.array([c[1] for c in CONF]); LEVs = np.array([c[0] for c in CONF], np.float64)
FG = np.array([0.02, 0.03, 0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4])
DAYS = {"A_tr": (CUT - tent.min())/864e5, "A_te": (tent.max()-CUT)/864e5}

@njit(cache=True)
def sim(idx, sd, coin, tent, isA, W, X, TPs, LEVs, cut):
    nc = W.shape[0]; n = len(idx)
    R = np.full((nc, n), np.nan); G = np.full((nc, n), -1, np.int8)   # Gruppe 0=A_tr 1=A_te 2=B_tr 3=B_te
    for j in range(nc):
        busy = -1; lastc = -1; q2 = 0
        for q in range(n):
            i = idx[q]
            if coin[i] != lastc: busy = -1; lastc = coin[i]
            if tent[i] < busy: continue
            s = 0 if sd[q] > 0 else 1
            w = W[j, s, i]
            if w < 0: continue
            xt = X[j, s, i]; busy = xt
            hold = (xt - tent[i]) / 28800000.0
            r = TPs[j]*LEVs[j] - 0.0008*LEVs[j] - 0.0001*hold*LEVs[j]*(1.0 if s == 0 else -1.0) if w == 1 else -1.0
            R[j, q2] = r; G[j, q2] = (0 if isA[i] else 2) + (0 if tent[i] < cut else 1); q2 += 1
    return R, G

rows = []
for key, (Li, Si) in M.items():
    both = np.intersect1d(Li, Si)
    Li = np.setdiff1d(Li, both); Si = np.setdiff1d(Si, both)
    idx = np.concatenate([Li, Si]); sd = np.concatenate([np.ones(len(Li), np.int8), -np.ones(len(Si), np.int8)])
    o_ = np.argsort(idx, kind="stable"); idx = idx[o_]; sd = sd[o_]
    if len(idx) < 50: continue
    R, G = sim(idx, sd, coin_id, tent, isA, W, X, TPs, LEVs, CUT)
    for j, (lev, tp) in enumerate(CONF):
        rr, gg = R[j], G[j]; m = gg >= 0; rr, gg = rr[m], gg[m]
        out = {"rsi15": key[0], "tagesrsi": key[1], "donchian": key[2], "filter": key[3], "hebel": lev, "tp": tp}
        for g, nm in enumerate(("A_tr", "A_te", "B_tr", "B_te")):
            x = rr[gg == g]
            out[f"n_{nm}"] = len(x); out[f"wr_{nm}"] = (x > 0).mean() if len(x) else np.nan; out[f"edge_{nm}"] = x.mean() if len(x) else np.nan
        x = rr[gg == 0]
        best = max(FG, key=lambda f: np.log1p(f*x).sum() if len(x) and (1+f*x).min() > 0 else -1e9)
        out["f"] = best
        for g, nm in enumerate(("A_tr", "A_te", "B_tr", "B_te")):
            x = rr[gg == g]
            out[f"log_{nm}"] = np.log1p(best*x).sum() if len(x) and (1+best*x).min() > 0 else -np.inf
        rows.append(out)
res = pd.DataFrame(rows)
res["g_A_tr"] = res.log_A_tr/DAYS["A_tr"]; res["g_A_te"] = res.log_A_te/DAYS["A_te"]
res["g_B"] = (res.log_B_tr + res.log_B_te)/(DAYS["A_tr"] + DAYS["A_te"])
res.to_csv(os.path.join(D, "improve_result.csv"), index=False)
pd.set_option("display.width", 260)
cols = ["rsi15", "tagesrsi", "donchian", "filter", "hebel", "tp", "n_A_tr", "wr_A_tr", "edge_A_tr", "n_A_te", "wr_A_te", "edge_A_te", "n_B_tr", "n_B_te", "edge_B_tr", "edge_B_te", "f", "g_A_tr", "g_A_te", "g_B"]
base = res[(res.rsi15 == 30) & (res.tagesrsi == 70) & (res.donchian == 20) & (res["filter"] == "ohne") & (res.hebel == 20) & (res.tp == 0.05)]
print("\nBASIS (aktuelle Regel):\n", base[cols].round(3).to_string(index=False))
print("\nTOP 20 nach A 2021-23:\n", res.nlargest(20, "g_A_tr")[cols].round(3).to_string(index=False))
top = res.nlargest(200, "g_A_tr")
print(f"\nTop 200 nach A-Train: Anteil g_A_te>0 {(top.g_A_te > 0).mean()*100:.0f}%, g_B>0 {(top.g_B > 0).mean()*100:.0f}% | alle: {(res.g_A_te > 0).mean()*100:.0f}% / {(res.g_B > 0).mean()*100:.0f}%")
print("FERTIG", f"{time.time()-t0:.0f}s", flush=True)
