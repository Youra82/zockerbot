"""Indikator-Bedingungen je 15m-Bar (abgeschlossene Kerzen, kein Lookahead). Liefert dict name -> (long_mask, short_mask)."""
import numpy as np, pandas as pd

def rsi(c, n=14):
    d = c.diff(); g = d.clip(lower=0); l = (-d).clip(lower=0)
    ag = g.ewm(alpha=1/n, adjust=False).mean(); al = l.ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + ag/al.replace(0, np.nan))

def ind(df):
    c, h, l = df.close, df.high, df.low
    out = {}
    r = rsi(c); out["rsi"] = r
    mn = r.rolling(14).min(); mx = r.rolling(14).max()
    k = ((r-mn)/(mx-mn).replace(0, np.nan)*100).rolling(3).mean(); d = k.rolling(3).mean()
    out["k"], out["d"] = k, d
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    m = e12-e26; s = m.ewm(span=9, adjust=False).mean(); hist = m-s
    out["macd"], out["sig"], out["hist"], out["hist_prev"] = m, s, hist, hist.shift(1)
    out["e20"], out["e50"], out["e200"] = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean(), c.ewm(span=200, adjust=False).mean()
    sma = c.rolling(20).mean(); sd = c.rolling(20).std()
    out["bbu"], out["bbl"] = sma+2*sd, sma-2*sd
    out["dch"], out["dcl"] = h.rolling(20).max().shift(1), l.rolling(20).min().shift(1)
    # Supertrend 10/3
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/10, adjust=False).mean().values
    hl2 = ((h+l)/2).values; cv = c.values
    ub = hl2+3*atr; lb = hl2-3*atr; fu = ub.copy(); fl = lb.copy(); dirn = np.ones(len(cv))
    for i in range(1, len(cv)):
        fu[i] = ub[i] if (ub[i] < fu[i-1] or cv[i-1] > fu[i-1]) else fu[i-1]
        fl[i] = lb[i] if (lb[i] > fl[i-1] or cv[i-1] < fl[i-1]) else fl[i-1]
        dirn[i] = 1 if cv[i] > fu[i-1] else (-1 if cv[i] < fl[i-1] else dirn[i-1])
    out["st"] = pd.Series(dirn, index=c.index)
    out["close"] = c
    return pd.DataFrame(out)

def conds(F, tf):
    c = F.close; C = {}
    C[f"{tf} RSI<30 | >70"] = (F.rsi < 30, F.rsi > 70)
    C[f"{tf} RSI>50 | <50"] = (F.rsi > 50, F.rsi < 50)
    C[f"{tf} RSI>70 | <30"] = (F.rsi > 70, F.rsi < 30)
    C[f"{tf} StochK>D"] = (F.k > F.d, F.k < F.d)
    C[f"{tf} StochK<20 | >80"] = (F.k < 20, F.k > 80)
    C[f"{tf} MACD>Signal"] = (F.macd > F.sig, F.macd < F.sig)
    C[f"{tf} Histogramm steigt"] = (F["hist"] > F["hist_prev"], F["hist"] < F["hist_prev"])
    C[f"{tf} MACD>0"] = (F.macd > 0, F.macd < 0)
    C[f"{tf} Kurs>EMA50"] = (c > F.e50, c < F.e50)
    C[f"{tf} EMA20>EMA50"] = (F.e20 > F.e50, F.e20 < F.e50)
    C[f"{tf} Kurs>EMA200"] = (c > F.e200, c < F.e200)
    C[f"{tf} unter BB-unten | ueber BB-oben"] = (c < F.bbl, c > F.bbu)
    C[f"{tf} ueber BB-oben | unter BB-unten"] = (c > F.bbu, c < F.bbl)
    C[f"{tf} Donchian-Ausbruch"] = (c > F.dch, c < F.dcl)
    C[f"{tf} Supertrend"] = (F.st > 0, F.st < 0)
    return C

def build(df15):
    """df15: 15m OHLCV mit open_time (ms). Gibt dict name -> (long bool np, short bool np) auf 15m-Raster."""
    df15 = df15.copy(); df15.index = pd.to_datetime(df15.open_time, unit="ms")
    close_t = df15.index + pd.Timedelta(minutes=15)
    allc = {}
    F = ind(df15)
    for k, (a, b) in conds(F, "15m").items(): allc[k] = (a.values.astype(bool), b.values.astype(bool))
    v = df15.volume; z = (v - v.rolling(96).mean())/v.rolling(96).std()
    green = df15.close > df15.open
    allc["15m Volumen-Spitze"] = (((z > 2) & green).values, ((z > 2) & ~green).values)
    kp, dp = F.k.shift(1), F.d.shift(1)
    allc["15m Stoch-Kreuz"] = (((kp <= dp) & (F.k > F.d)).values, ((kp >= dp) & (F.k < F.d)).values)
    for tf, rule in [("1h", "1h"), ("4h", "4h"), ("1d", "1D")]:
        agg = df15.resample(rule, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        Fh = ind(agg)
        avail = agg.index + pd.Timedelta(rule)            # Zeitpunkt, ab dem die HTF-Kerze abgeschlossen ist
        pos = np.searchsorted(avail.values, close_t.values, side="right") - 1
        ok = pos >= 0
        for k, (a, b) in conds(Fh, tf).items():
            av, bv = a.values.astype(bool), b.values.astype(bool)
            allc[k] = (np.where(ok, av[np.clip(pos, 0, None)], False), np.where(ok, bv[np.clip(pos, 0, None)], False))
    # Warmup: erste 30 Tage nichts
    warm = (df15.index - df15.index[0]) < pd.Timedelta(days=60)
    for k in allc: allc[k] = (allc[k][0] & ~warm, allc[k][1] & ~warm)
    return allc
