import os, sys, numpy as np, pandas as pd
from numba import njit
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import strategy
B = os.environ.get("ZB_KERZEN_1M", "kerzen1m")   # Ordner mit <COIN>USDT.parquet (1m-Kerzen)
COINS = ["XRP", "BTC", "ETH", "SOL", "BNB", "LTC", "AVAX", "ARB"]
LEV = 10; LIQ = 1/LEV - 0.005
EXITS = [("TP fest 7,5 %", 0.075, 0.0, 0.0)] + [(f"TSL ab +{a*100:g} %, Abstand {c*100:g} %", 0.0, a, c) for a in (0.025, 0.05, 0.075) for c in (0.01, 0.02, 0.03, 0.05)]
CUT = pd.Timestamp("2024-01-01")

@njit(cache=True)
def run_exit(o, h, l, s0, side, tp, act, cb, liq):
    """ab Index s0 (Einstieg zur Eröffnung von s0). Rückgabe: (Kursrendite in Trade-Richtung, Ausstiegs-Index, Art 0=Liq 1=TP 2=TSL)"""
    px = o[s0]; n = len(o)
    if side > 0: lq = px*(1-liq)
    else: lq = px*(1+liq)
    active = False; peak = px
    for j in range(s0, n):
        if side > 0:
            if l[j] <= lq: return -liq, j, 0
            if tp > 0 and h[j] >= px*(1+tp): return tp, j, 1
            if active:
                st = peak*(1-cb)
                if l[j] <= st:
                    ex = min(st, o[j]) if j > s0 else st
                    return ex/px - 1, j, 2
            if h[j] > peak: peak = h[j]
            if not active and act > 0 and peak >= px*(1+act): active = True
        else:
            if h[j] >= lq: return -liq, j, 0
            if tp > 0 and l[j] <= px*(1-tp): return tp, j, 1
            if active:
                st = peak*(1+cb)
                if h[j] >= st:
                    ex = max(st, o[j]) if j > s0 else st
                    return 1 - ex/px, j, 2
            if l[j] < peak: peak = l[j]
            if not active and act > 0 and peak <= px*(1-act): active = True
    return np.nan, -1, -1

rows = []
for c in COINS:
    m1 = pd.read_parquet(f"{B}/{c}USDT.parquet"); m1.index = pd.to_datetime(m1.open_time, unit="ms")
    o, h, l = m1.open.to_numpy(), m1.high.to_numpy(), m1.low.to_numpy()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    d15 = m1[["open", "high", "low", "close"]].resample("15min").agg(agg).dropna()
    d1 = d15.resample("1D").agg(agg).dropna()
    sig = strategy.signals(d15, d1)
    warm = (d15.index - d15.index[0]) < pd.Timedelta(days=60)
    for k in np.flatnonzero((sig.to_numpy() != 0) & ~warm):
        te = d15.index[k] + pd.Timedelta(minutes=15)
        s0 = m1.index.searchsorted(te)
        if s0 >= len(o) - 1: continue
        side = int(sig.iloc[k])
        rec = {"coin": c, "t": te, "side": side}
        for name, tp, a, cb in EXITS:
            ret, j, art = run_exit(o, h, l, s0, side, tp, a, cb, LIQ)
            if j < 0: rec[name] = None; continue
            fee = (0.0006 + (0.0002 if art == 1 else 0.0006)) * LEV
            rec[name] = -1.0 if art == 0 else ret*LEV - fee
            rec[name + "|x"] = m1.index[j]
        rows.append(rec)
    print(c, len(rows), flush=True)
D = pd.DataFrame(rows).sort_values(["t", "coin"]).reset_index(drop=True); D.to_pickle("tsl_trades.pkl")
def seq(col):
    busy = pd.Timestamp(0); out = []
    for r in D.itertuples(index=False):
        rr = getattr(r, "_" + str(list(D.columns).index(col))) if False else None
    for i in range(len(D)):
        if D.at[i, "t"] < busy or pd.isna(D.at[i, col]): continue
        busy = D.at[i, col + "|x"]; out.append((D.at[i, "t"], D.at[i, col]))
    return pd.DataFrame(out, columns=["t", "r"])
def tresor(rs, ziel=1000, keep=0.2, neu=30.0, e=0.97):
    spiel, tre, ext, hits = neu, 0.0, neu, 0
    for r in rs:
        spiel += e*spiel*r
        if spiel >= ziel: b = max(neu, keep*spiel); tre += spiel - b; spiel = b; hits += 1
        elif spiel < neu:
            need = neu - spiel
            if tre >= need: tre -= need
            else: ext += need - tre; tre = 0
            spiel = neu
    return hits, round(ext), round(tre + spiel - ext)
def grow(rs, f):
    k = 30.0
    for r in rs: k *= 1 + f*r
    return k
print(f"\n{'Ausstieg':34s} | {'2021-23':^40s} | {'2024-26':^40s} | Serie+Tresor 21-26 | Anteil (f gewählt 21-23)")
for name, *_ in EXITS:
    T = seq(name)
    tr, te = T[T.t < CUT].r.values, T[T.t >= CUT].r.values
    f = max((0.05, 0.1, 0.15, 0.2, 0.25, 0.3), key=lambda f: np.log1p(f*tr).sum() if (1+f*tr).min() > 0 else -1e9)
    h, ext, net = tresor(T.r.values)
    print(f"{name:34s} | {len(tr):3d} Tr, Treffer {np.mean(tr>0)*100:4.1f}%, je Trade {tr.mean():+.3f} | {len(te):3d} Tr, Treffer {np.mean(te>0)*100:4.1f}%, je Trade {te.mean():+.3f} | {h}x Ziel, netto {net:+6,} | f={f:.2f}: 21-23 30->{grow(tr, f):,.0f}, 24-26 30->{grow(te, f):,.0f}")
