import heapq, numpy as np, pandas as pd
from features import build
B = "kerzen"
LEV, TP = 20, 0.05; LIQ = 1/LEV - 0.005
parts = ["15m RSI<30 | >70", "1d RSI>70 | <30", "1d Donchian-Ausbruch"]
trades = []
for sym in ["XRPUSDT","BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","LTCUSDT","AVAXUSDT","ARBUSDT","AAVEUSDT","ADAUSDT","DOGEUSDT"]:
    df = pd.read_parquet(f"{B}/ohlcv_15m/{sym}.parquet"); C = build(df)
    L = np.ones(len(df), bool); S = np.ones(len(df), bool)
    for p in parts: L &= C[p][0]; S &= C[p][1]
    sel = np.flatnonzero(L ^ S); t15 = df.open_time.values.astype(np.int64)
    try:
        z = np.load(f"labels/{sym}.npz"); src = "1m"
    except FileNotFoundError:
        z = None; src = "15m"
    o, h, l = df.open.values, df.high.values, df.low.values
    busy = -1
    for k in sel:
        te = t15[k] + 15*60_000
        if te < busy: continue
        side = 1 if L[k] else -1
        if z is not None:
            w = z[f"w_L20_T50_{'L' if side > 0 else 'S'}"][k]; xt = z[f"x_L20_T50_{'L' if side > 0 else 'S'}"][k]
            if w < 0: continue
        else:
            if k+1 >= len(o): continue
            px = o[k+1]; up, dn = (px*(1+TP), px*(1-LIQ)) if side > 0 else (px*(1+LIQ), px*(1-TP))
            ia = np.flatnonzero(h[k+1:] >= up); ib = np.flatnonzero(l[k+1:] <= dn)
            a = ia[0] if len(ia) else -1; b = ib[0] if len(ib) else -1
            tpj, lqj = (a, b) if side > 0 else (b, a)
            if tpj == -1 and lqj == -1: continue
            if lqj != -1 and (tpj == -1 or lqj <= tpj): w, j = 0, lqj
            else: w, j = 1, tpj
            xt = t15[k+1+j] + 15*60_000
        hold = (xt - te)/28800000
        r = TP*LEV - 0.0008*LEV - 0.0001*hold*LEV*side if w else -1.0
        trades.append((sym[:-4], te, xt, side, int(w), r, src)); busy = xt
T = pd.DataFrame(trades, columns=["coin","te","xt","side","win","r","src"]).sort_values("te").reset_index(drop=True)
T["datum"] = pd.to_datetime(T.te, unit="ms"); T["jahr"] = T.datum.dt.year
print("Trades:", len(T), "| Treffer %.1f%%" % (T.win.mean()*100), "| Long", (T.side>0).sum(), "Short", (T.side<0).sum(), "| Haltedauer Median %.1f h" % ((T.xt-T.te).median()/3.6e6))
print(T.groupby("jahr").agg(trades=("win","size"), treffer=("win","mean"), edge=("r","mean")).round(3).to_string())
print(T.groupby("coin").agg(trades=("win","size"), treffer=("win","mean"), edge=("r","mean")).round(3).to_string())
T.to_csv("winner_trades.csv", index=False)

def account(T, f, start=30.0, t0=None, goal=1100.0):
    """gemeinsames Konto, mehrere Coins gleichzeitig; Margin = f * Kontostand bei Einstieg, P&L bei Ausstieg"""
    eq = start; open_ = []; 
    for te, xt, r in zip(T.te, T.xt, T.r):
        if t0 is not None and te < t0: continue
        while open_ and open_[0][0] <= te:
            x, m, rr = heapq.heappop(open_); eq += m*rr
            if eq >= goal: return x, eq
            if eq <= 0.5: return None, 0
        free = eq - sum(m for _, m, _ in open_)
        m = min(f*eq, free)
        if m <= 0: continue
        heapq.heappush(open_, (xt, m, r))
    while open_:
        x, m, rr = heapq.heappop(open_); eq += m*rr
        if eq >= goal: return x, eq
    return None, eq

print("\nFester Anteil: Start 30 USDT zu jedem Monatsanfang -> Tage bis 1100 USDT")
starts = pd.date_range("2021-03-01", "2025-06-01", freq="MS")
for f in [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 1.0]:
    days = []; ruin = 0; never = 0
    for s in starts:
        t0 = int(s.value//10**6); x, eq = account(T, f, t0=t0)
        if x is None:
            if eq == 0: ruin += 1
            else: never += 1
        else: days.append((x - t0)/86400000)
    d = np.array(days)
    print(f"  Anteil {int(f*100):3d}%: erreicht {len(d)}/{len(starts)}, pleite {ruin}, nicht erreicht {never} | Tage Median {np.median(d) if len(d) else np.nan:.0f}, schnellstes {d.min() if len(d) else np.nan:.0f}, 75% {np.percentile(d,75) if len(d) else np.nan:.0f}")

print("\nAll-in bis 1100 (nach Liquidation 30 neu), chronologisch ab Maerz 2021, nur eine Position gleichzeitig:")
eq = 30; dep = 30; wins = []; t_start = T.te.iloc[0]; busy = -1
for te, xt, r in zip(T.te, T.xt, T.r):
    if te < busy: continue
    busy = xt; eq *= 1+r
    if eq >= 1100: wins.append((pd.to_datetime(xt, unit="ms").date(), round(eq), dep)); eq = 30; dep += 30
    elif eq <= 0: eq = 30; dep += 30
print("  Erfolge:", len(wins), "| eingezahlt gesamt", dep, "| ausgezahlt", sum(w[1] for w in wins))
for w in wins: print("   ", w)
