import sys, glob, os, math, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cockpit")); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import zonen, strategy
K = "kerzen40/ohlcv_15m"; CUT = pd.Timestamp("2024-01-01")
LEV = 10; LIQ = 1/LEV - 0.005; FEE = 0.0008*LEV
def resolve(o, h, l, k, side, tp):
    px = o[k+1]; up, dn = (px*(1+tp), px*(1-LIQ)) if side > 0 else (px*(1+LIQ), px*(1-tp))
    ia = np.flatnonzero(h[k+1:] >= up); ib = np.flatnonzero(l[k+1:] <= dn)
    a = ia[0] if len(ia) else -1; b = ib[0] if len(ib) else -1
    t_, q_ = (a, b) if side > 0 else (b, a)
    if t_ == -1 and q_ == -1: return None
    return (0, k+1+q_) if (q_ != -1 and (t_ == -1 or q_ <= t_)) else (1, k+1+t_)
rows = []
for f in sorted(glob.glob(f"{K}/*.parquet")):
    c = os.path.basename(f)[:-12]
    df = pd.read_parquet(f); df.index = pd.to_datetime(df.open_time, unit="ms")
    d15 = df[["open", "high", "low", "close"]]
    d1 = d15.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    h1 = d15.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    sig = strategy.signals(d15, d1).to_numpy()
    warm = (df.index - df.index[0]) < pd.Timedelta(days=60)
    o, h, l = d15.open.to_numpy(), d15.high.to_numpy(), d15.low.to_numpy()
    h1v = h1.reset_index(); h1t = h1.index.values
    for k in np.flatnonzero((sig != 0) & ~warm):
        if k + 1 >= len(o): continue
        side = int(sig[k]); tclose = df.index[k] + pd.Timedelta(minutes=15)
        j = np.searchsorted(h1t, (tclose - pd.Timedelta(hours=1)).to_datetime64(), side="right")   # nur abgeschlossene 1h-Kerzen
        seg = h1.iloc[max(0, j-1500): j]
        cand = [[0, r.open, r.high, r.low, r.close] for r in seg.itertuples()]
        cand.append([0, o[k], h[k], l[k], d15.close.iloc[k]])          # laufender Stand inkl. Signal-Kerze
        z = zonen.analyse(cand)
        if z is None: continue
        sig_pct = z["sigma_pct"]/100
        res = {"coin": c, "t": tclose, "side": side, "art": z["art"], "richtung": z["richtung"], "zur": z["zurueck_sigma"],
               "gelaufen": z["gelaufen_sigma"], "sigma": sig_pct}
        for name, tp in [("fest", 0.075), ("q25", 2.6*sig_pct), ("med", 3.6*sig_pct)]:
            r = resolve(o, h, l, k, side, tp)
            res[f"w_{name}"] = None if r is None else r[0]; res[f"x_{name}"] = None if r is None else df.index[r[1]]
            res[f"g_{name}"] = tp*LEV - FEE
        rows.append(res)
    print(c, len(rows), flush=True)
D = pd.DataFrame(rows); D.to_parquet("tipp_zonen.parquet"); print("FERTIG", len(D))
