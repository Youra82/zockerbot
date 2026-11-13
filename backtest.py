"""zockerbot – Backtest mit Bitget-Kerzen und DERSELBEN Signalfunktion wie live (strategy.signals).

Einstieg zur Eröffnung der nächsten 15m-Kerze, TP und Liquidation werden auf 15m-Hoch/Tief
geprüft; erreicht eine Kerze beides, zählt es als Liquidation (vorsichtig).
Ein Konto für alle Coins, Margin = Anteil des Kontostands bei Einstieg (höchstens frei verfügbar).

  python3 backtest.py --days 365
  python3 backtest.py --days 730 --start 30 --fraction 0.15
Kerzen werden unter data/cache/ zwischengespeichert.
"""
import argparse
import heapq
import json
import os

import numpy as np
import pandas as pd

import strategy
from exchange import Exchange

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "cache")


def history(ex: Exchange, symbol: str, tf: str, days: int) -> pd.DataFrame:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{symbol.split('/')[0]}_{tf}.csv")
    end = ex.exchange.milliseconds()
    start = end - (days + 60) * 86_400_000          # 60 Tage Vorlauf für Indikatoren
    old = pd.read_csv(path, index_col=0, parse_dates=True) if os.path.exists(path) else None
    since = start
    if old is not None and len(old) and old.index[0] <= pd.Timestamp(start, unit="ms", tz="UTC"):
        since = int(old.index[-1].timestamp() * 1000)
    rows, last = [], None
    tf_ms = ex.exchange.parse_timeframe(tf) * 1000
    while since < end - tf_ms:
        batch = ex.exchange.fetch_ohlcv(symbol, tf, since, 200)
        batch = [c for c in batch if last is None or c[0] > last]
        if not batch:
            break
        rows += batch
        last = batch[-1][0]
        since = last
    new = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    new.index = pd.to_datetime(new.pop("ts"), unit="ms", utc=True)
    df = new if old is None or since == start else pd.concat([old, new])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.to_csv(path)
    df = ex.closed_only(df, tf)
    return df[df.index >= pd.Timestamp(start, unit="ms", tz="UTC")]


def trades_for(df15, df1d, cfg):
    sig = strategy.signals(df15, df1d, cfg.get("strategy", {}))
    lev, tp = cfg["leverage"], cfg["tp_pct"]
    liq = strategy.liquidation_distance(lev)
    o, h, l = df15["open"].to_numpy(), df15["high"].to_numpy(), df15["low"].to_numpy()
    t = df15.index
    out, busy = [], -1
    for k in np.flatnonzero(sig.to_numpy() != 0):
        if k <= busy or k + 1 >= len(o):
            continue
        side = int(sig.iloc[k])
        px = o[k + 1]
        up, dn = (px * (1 + tp), px * (1 - liq)) if side > 0 else (px * (1 + liq), px * (1 - tp))
        ia = np.flatnonzero(h[k + 1:] >= up)
        ib = np.flatnonzero(l[k + 1:] <= dn)
        a = ia[0] if len(ia) else -1
        b = ib[0] if len(ib) else -1
        hit_tp, hit_liq = (a, b) if side > 0 else (b, a)
        if hit_tp == -1 and hit_liq == -1:
            continue                                # noch offen
        if hit_liq != -1 and (hit_tp == -1 or hit_liq <= hit_tp):
            win, j = 0, hit_liq
        else:
            win, j = 1, hit_tp
        x = k + 1 + j
        r = tp * lev - (cfg["taker_fee"] + cfg["maker_fee"]) * lev if win else -1.0
        out.append((t[k + 1], t[x] + pd.Timedelta(minutes=15), side, win, r))
        busy = x
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--start", type=float, default=30.0)
    ap.add_argument("--fraction", type=float, default=None)
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "settings.json"), encoding="utf-8"))
    f = a.fraction if a.fraction is not None else cfg["margin_fraction"]
    ex = Exchange()
    allt = []
    for coin in cfg["coins"]:
        sym = f"{coin}/USDT:USDT"
        df15 = history(ex, sym, "15m", a.days)
        df1d = history(ex, sym, "1d", a.days + 60)
        tr = trades_for(df15, df1d, cfg)
        allt += [(coin, *x) for x in tr]
        wr = np.mean([x[3] for x in tr]) * 100 if tr else float("nan")
        print(f"{coin:5s} {len(tr):4d} Trades, Treffer {wr:5.1f} %")
    T = pd.DataFrame(allt, columns=["coin", "entry", "exit", "side", "win", "r"]).sort_values("entry")
    if T.empty:
        print("Keine Trades.")
        return
    T["jahr"] = T.entry.dt.year
    print("\nJe Jahr:")
    print(T.groupby("jahr").agg(trades=("win", "size"), treffer=("win", "mean"), je_trade=("r", "mean")).round(3).to_string())
    eq, peak, mdd, open_ = a.start, a.start, 0.0, []
    for _, row in T.iterrows():
        while open_ and open_[0][0] <= row.entry:
            _, m, r = heapq.heappop(open_)
            eq += m * r
            peak = max(peak, eq)
            mdd = max(mdd, 1 - eq / peak)
        used = sum(m for _, m, _ in open_)
        m = min(f * eq, eq - used)
        if m > 0:
            heapq.heappush(open_, (row.exit, m, row.r))
    while open_:
        _, m, r = heapq.heappop(open_)
        eq += m * r
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
    print(f"\n{len(T)} Trades, Treffer {T.win.mean()*100:.1f} % (Gewinnschwelle ca. "
          f"{100/(1+cfg['tp_pct']*cfg['leverage']-(cfg['taker_fee']+cfg['maker_fee'])*cfg['leverage']):.1f} %)")
    print(f"Konto: {a.start:.2f} -> {eq:.2f} USDT bei {f*100:.0f} % Margin je Trade, größter Rückgang {mdd*100:.0f} %")
    T.to_csv(os.path.join(ROOT, "data", "backtest_trades.csv"), index=False)


if __name__ == "__main__":
    main()
