import heapq, numpy as np, pandas as pd
src = open("improve.py", encoding="utf-8").read()
exec(src[: src.index("rows = []")].replace("cache=True", "cache=False"))
KEYS = {"aktuell (30/70/20, x20 TP5)": ((30, 70, 20, "ohne"), (20, 0.05)),
        "breit (30/60/20, x10 TP3)":   ((30, 60, 20, "breit"), (10, 0.03)),
        "breit (30/70/20, x10 TP3)":   ((30, 70, 20, "breit"), (10, 0.03)),
        "BTC-Trend (30/60/10, x10 TP3)": ((30, 60, 10, "BTC-Trend"), (10, 0.03))}
def trades(key, cfg):
    Li, Si = M[key]; both = np.intersect1d(Li, Si); Li = np.setdiff1d(Li, both); Si = np.setdiff1d(Si, both)
    idx = np.concatenate([Li, Si]); sd = np.concatenate([np.ones(len(Li), np.int8), -np.ones(len(Si), np.int8)])
    o = np.argsort(idx, kind="stable"); idx, sd = idx[o], sd[o]
    j = CONF.index(cfg); out = []; busy = -1; lastc = -1
    for i, s in zip(idx, sd):
        if coin_id[i] != lastc: busy = -1; lastc = coin_id[i]
        if tent[i] < busy: continue
        w = W[j, 0 if s > 0 else 1, i]
        if w < 0: continue
        xt = X[j, 0 if s > 0 else 1, i]; busy = xt
        hold = (xt - tent[i])/28800000
        r = cfg[1]*cfg[0] - 0.0008*cfg[0] - 0.0001*hold*cfg[0]*s if w == 1 else -1.0
        out.append((tent[i], xt, r, coins[coin_id[i]]))
    return pd.DataFrame(out, columns=["te", "xt", "r", "coin"]).sort_values("te").reset_index(drop=True)
def account(T, f, kmax, t0, t1, start=30.0, goal=None):
    k = start; open_ = []; peak = k; mdd = 0
    for te, xt, r in zip(T.te, T.xt, T.r):
        if te < t0: continue
        if te >= t1: break
        while open_ and open_[0][0] <= te:
            x, m, rr = heapq.heappop(open_); k += m*rr; peak = max(peak, k); mdd = max(mdd, 1-k/peak)
            if goal and k >= goal: return k, mdd, (x - t0)/864e5
            if k < 1: return 0.0, 1.0, None
        if len(open_) >= kmax: continue
        m = min(f*k, k - sum(mm for _, mm, _ in open_))
        if m > 0: heapq.heappush(open_, (xt, m, r))
    while open_:
        x, m, rr = heapq.heappop(open_); k += m*rr; peak = max(peak, k); mdd = max(mdd, 1-k/peak)
        if goal and k >= goal: return k, mdd, (x - t0)/864e5
    return k, mdd, None
T0 = int(pd.Timestamp("2021-03-01").value//10**6); TE = int(tent.max())
for name, (key, cfg) in KEYS.items():
    T = trades(key, cfg)
    print(f"\n=== {name}: {len(T)} Trades, Treffer {(T.r > 0).mean()*100:.1f} %, je Trade {T.r.mean():+.3f}, Trades/Tag {len(T)/((TE-T0)/864e5):.2f}")
    best = None
    for kmax in (2, 3, 5, 10, 99):
        for f in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4):
            ktr, ddtr, _ = account(T, f, kmax, T0, CUT); kte, ddte, _ = account(T, f, kmax, CUT, TE)
            if best is None or ktr > best[0]: best = (ktr, f, kmax)
            if kmax in (3, 99) and f in (0.1, 0.2, 0.3): print(f"   K={kmax:2d} f={f:.2f}: 2021-23 30->{ktr:,.0f} (DD {ddtr*100:.0f}%) | 2024-26 30->{kte:,.0f} (DD {ddte*100:.0f}%)")
    _, f, kmax = best
    kte, ddte, _ = account(T, f, kmax, CUT, TE)
    days = []
    for s in pd.date_range("2021-03-01", "2025-06-01", freq="MS"):
        t0 = int(s.value//10**6); k, dd, d = account(T, f, kmax, t0, TE, goal=1100)
        days.append(d if d is not None else np.nan)
    d = np.array(days)
    print(f"  -> gewaehlt auf 2021-23: f={f}, K={kmax} | Gegenprobe 2024-26: 30 -> {kte:,.0f} USDT, DD {ddte*100:.0f}% | "
          f"Monatsstarts bis 1100: erreicht {np.isfinite(d).sum()}/{len(d)}, Median {np.nanmedian(d):.0f} Tage, schnellstes {np.nanmin(d):.0f}")
