import numpy as np, pandas as pd
from features import build
B = "kerzen"
r = pd.read_parquet("search_result.parquet")
pool = r[(r.g_tr > 0) & (r.g_te > 0) & (r.n_te >= 100)].copy()
pool["gmin"] = np.minimum(pool.g_tr, pool.g_te)
print("Kandidaten in beiden Zeitraeumen positiv:", len(pool), "von", len(r))
cand = pool.nlargest(40, "gmin")
def labels15(df, lev, tp, side):
    o, h, l = df.open.values, df.high.values, df.low.values; n = len(o); liq = 1/lev - 0.005
    win = np.full(n, -1, np.int8); ex = np.full(n, -1, np.int64)
    for k in range(n-1):
        px = o[k+1]
        up, dn = (px*(1+tp), px*(1-liq)) if side > 0 else (px*(1+liq), px*(1-tp))
        hh, ll = h[k+1:], l[k+1:]
        a = np.argmax(hh >= up) if (hh >= up).any() else -1
        b = np.argmax(ll <= dn) if (ll <= dn).any() else -1
        if side > 0: tpj, lqj = a, b
        else: tpj, lqj = b, a
        if tpj == -1 and lqj == -1: continue
        if lqj != -1 and (tpj == -1 or lqj <= tpj): win[k] = 0; ex[k] = k+1+lqj
        else: win[k] = 1; ex[k] = k+1+tpj
    return win, ex
FG = [0.005,0.01,0.015,0.02,0.03,0.04,0.05,0.06,0.075,0.09,0.1,0.125,0.15,0.175,0.2,0.25,0.3,0.4,0.5]
out = {i: [] for i in cand.index}
for sym in ["AAVEUSDT", "ADAUSDT", "DOGEUSDT"]:
    df = pd.read_parquet(f"{B}/ohlcv_15m/{sym}.parquet"); C = build(df)
    cache = {}
    for i, row in cand.iterrows():
        parts = row.regel.split(" + ")
        L = np.ones(len(df), bool); S = np.ones(len(df), bool)
        for p in parts: L &= C[p][0]; S &= C[p][1]
        sel = L if row.richtung == "Long" else (S if row.richtung == "Short" else (L ^ S))
        key = (row.hebel, row.tp)
        busy = -1
        for k in np.flatnonzero(sel):
            if k <= busy: continue
            side = 1 if L[k] else -1
            ck = key + (side,)
            if ck not in cache:
                # nur fuer gebrauchte Indizes rechnen waere schneller; einfach komplett
                cache[ck] = None
            out[i].append((sym, k, side))
    # Labels nur fuer benoetigte Kombis berechnen (vektorisiert per Schleife)
    need = {}
    for i, row in cand.iterrows():
        for (s_, k, side) in [x for x in out[i] if x[0] == sym]:
            need.setdefault((row.hebel, row.tp, side), set()).add(k)
    lab = {}
    o, h, l = df.open.values, df.high.values, df.low.values
    for (lev, tp, side), ks in need.items():
        liq = 1/lev - 0.005
        for k in ks:
            if k+1 >= len(o): continue
            px = o[k+1]
            up, dn = (px*(1+tp), px*(1-liq)) if side > 0 else (px*(1+liq), px*(1-tp))
            hh, ll = h[k+1:], l[k+1:]
            ia = np.flatnonzero(hh >= up); ib = np.flatnonzero(ll <= dn)
            a = ia[0] if len(ia) else -1; b = ib[0] if len(ib) else -1
            tpj, lqj = (a, b) if side > 0 else (b, a)
            if tpj == -1 and lqj == -1: continue
            if lqj != -1 and (tpj == -1 or lqj <= tpj): lab[(lev, tp, side, k)] = (0, k+1+lqj)
            else: lab[(lev, tp, side, k)] = (1, k+1+tpj)
    for i, row in cand.iterrows():
        rs = []; busy = -1
        for (s_, k, side) in [x for x in out[i] if x[0] == sym]:
            if k <= busy: continue
            v = lab.get((row.hebel, row.tp, side, k))
            if v is None: continue
            w, x = v; busy = x
            rs.append(row.tp*row.hebel - 0.0008*row.hebel if w else -1.0)
        row_store = cand.at[i, "regel"]
        cand.loc[i, f"n_{sym[:-4]}"] = len(rs)
        cand.loc[i, f"wr_{sym[:-4]}"] = np.mean([x > 0 for x in rs]) if rs else np.nan
        cand.loc[i, f"edge_{sym[:-4]}"] = np.mean(rs) if rs else np.nan
    print("fertig", sym, flush=True)
pd.set_option("display.width", 300); pd.set_option("display.max_colwidth", 80)
cand["edge_hold"] = (cand.edge_AAVE*cand.n_AAVE + cand.edge_ADA*cand.n_ADA + cand.edge_DOGE*cand.n_DOGE)/(cand.n_AAVE+cand.n_ADA+cand.n_DOGE)
cand["n_hold"] = cand.n_AAVE+cand.n_ADA+cand.n_DOGE
cols = ["regel","richtung","hebel","tp","n_tr","n_te","wr_tr","wr_te","f","edge_tr","edge_te","n_hold","edge_hold","edge_AAVE","edge_ADA","edge_DOGE"]
print(cand[cols].round(3).to_string(index=False))
cand.to_csv("holdout_result.csv", index=False)
