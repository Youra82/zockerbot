"""zockerbot – Backtest mit Bitget-Kerzen und DERSELBEN Signalfunktion wie live (strategy.signals).

Wie live: alle Coins, Signale in zeitlicher Reihenfolge, höchstens `max_positionen` gleichzeitig,
Einstieg zur Eröffnung der nächsten 15m-Kerze. TP und Liquidation werden auf 15m-Hoch/Tief geprüft;
erreicht eine Kerze beides, zählt es als Liquidation (vorsichtig).

Modus „serie“: all-in mit Zinseszins, ab `ziel_usdt` wird ausgezahlt und mit `--start` neu begonnen,
nach einer Liquidation wird `--start` neu eingezahlt. Modus „anteil“: Margin = Anteil des Kontos.

  python3 backtest.py --days 365
  python3 backtest.py --days 730 --start 30 --modus anteil --fraction 0.2
Kerzen werden unter data/cache/ zwischengespeichert.
"""
import argparse
import heapq
import json
import os
import time

import ccxt
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
    tries = 0
    while since < end - tf_ms:
        try:
            batch = ex.exchange.fetch_ohlcv(symbol, tf, since, 200)
        except ccxt.NetworkError:                 # inkl. 429 Too Many Requests
            tries += 1
            if tries > 8:
                raise
            time.sleep(2 * tries)
            continue
        tries = 0
        time.sleep(0.12)
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


def resolve(df15, k, side, tp, liq):
    """Ergebnis eines Einstiegs zur Eröffnung von Kerze k+1: (gewonnen, Ausstiegszeit) oder None (noch offen)."""
    o, h, l = df15["open"].to_numpy(), df15["high"].to_numpy(), df15["low"].to_numpy()
    if k + 1 >= len(o):
        return None
    px = o[k + 1]
    up, dn = (px * (1 + tp), px * (1 - liq)) if side > 0 else (px * (1 + liq), px * (1 - tp))
    ia = np.flatnonzero(h[k + 1:] >= up)
    ib = np.flatnonzero(l[k + 1:] <= dn)
    a = ia[0] if len(ia) else -1
    b = ib[0] if len(ib) else -1
    hit_tp, hit_liq = (a, b) if side > 0 else (b, a)
    if hit_tp == -1 and hit_liq == -1:
        return None
    if hit_liq != -1 and (hit_tp == -1 or hit_liq <= hit_tp):
        return False, df15.index[k + 1 + hit_liq] + pd.Timedelta(minutes=15)
    return True, df15.index[k + 1 + hit_tp] + pd.Timedelta(minutes=15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365, help="gehandelter Zeitraum bis heute in Tagen")
    ap.add_argument("--von", default=None, help="gehandelter Zeitraum ab Datum (JJJJ-MM-TT), ersetzt --days")
    ap.add_argument("--start", type=float, default=30.0)
    ap.add_argument("--modus", choices=["serie", "anteil"], default=None)
    ap.add_argument("--fraction", type=float, default=None)
    ap.add_argument("--ziel", type=float, default=None, help="Modus serie: ziel_usdt überschreiben")
    ap.add_argument("--im-spiel", type=float, default=None, help="Modus serie: im_spiel_nach_ziel überschreiben (0..1)")
    ap.add_argument("--polster", type=float, default=None, help="Modus serie: polster_usdt überschreiben (0 = aus)")
    ap.add_argument("--tresor-start", type=float, default=0.0, help="Modus serie: eigene Reserve im Tresor zum Start (wie live.py --tresor)")
    a = ap.parse_args()
    if a.von:
        try:
            von = pd.Timestamp(a.von, tz="UTC")
        except ValueError:
            raise SystemExit(f"FEHLER: --von '{a.von}' ist kein Datum (JJJJ-MM-TT).")
        a.days = int((pd.Timestamp.now(tz="UTC") - von).days) + 1
    else:
        von = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=a.days)
    print(f"Gehandelt ab {von.date()} bis heute ({a.days} Tage), davor 60 Tage nur als Vorlauf für die Indikatoren")
    cfg = json.load(open(os.path.join(ROOT, "settings.json"), encoding="utf-8"))
    if a.ziel is not None:
        cfg["ziel_usdt"] = a.ziel
    if a.im_spiel is not None:
        if not 0 <= a.im_spiel <= 1:
            raise SystemExit("FEHLER: --im-spiel muss zwischen 0 und 1 liegen.")
        cfg["im_spiel_nach_ziel"] = a.im_spiel
    if a.polster is not None:
        cfg["polster_usdt"] = a.polster
    modus = a.modus or cfg["modus"]
    f = a.fraction if a.fraction is not None else cfg["margin_fraction"]
    lev, tp, kmax = cfg["leverage"], cfg["tp_pct"], cfg["max_positionen"]
    liq = strategy.liquidation_distance(lev)
    g = tp * lev - (cfg["taker_fee"] + cfg["maker_fee"]) * lev
    ex = Exchange()
    data, events = {}, []
    for coin in cfg["coins"]:
        sym = f"{coin}/USDT:USDT"
        try:
            df15 = history(ex, sym, "15m", a.days)
            df1d = history(ex, sym, "1d", a.days + 60)
        except Exception as e:
            print(f"{coin}: keine Daten ({e})")
            continue
        sig = strategy.signals(df15, df1d, cfg.get("strategy", {}))
        data[coin] = df15
        n = 0
        for k in np.flatnonzero(sig.to_numpy() != 0):
            if df15.index[k] + pd.Timedelta(minutes=15) < von:      # Vorlauf wird nicht gehandelt
                continue
            events.append((df15.index[k], coin, int(k), int(sig.iloc[k])))
            n += 1
        print(f"{coin:5s} {n:4d} Signal-Kerzen")
    events.sort()
    taken, open_ = [], []                      # open_: (Ausstieg, Coin)
    for t, coin, k, side in events:
        open_ = [(x, c) for x, c in open_ if x > t]
        if len(open_) >= kmax or any(c == coin for _, c in open_):
            continue
        res = resolve(data[coin], k, side, tp, liq)
        if res is None:
            continue
        win, xt = res
        taken.append((t + pd.Timedelta(minutes=15), xt, coin, side, win))
        open_.append((xt, coin))
    T = pd.DataFrame(taken, columns=["entry", "exit", "coin", "side", "win"])
    if T.empty:
        print("Keine Trades.")
        return
    T["r"] = np.where(T.win, g, -1.0)
    T["jahr"] = T.entry.dt.year
    print("\nTrades:")
    for r in T.itertuples():
        print(f"  {r.entry:%d.%m.%y %H:%M}  {r.coin:5s} {'Long ' if r.side > 0 else 'Short'}  -> {'TP' if r.win else 'Liquidation':11s} {r.exit:%d.%m.%y %H:%M}")
    print(f"\n{len(T)} Trades, Treffer {T.win.mean() * 100:.1f} % (Gewinnschwelle {100 / (1 + g):.1f} %), +{g * 100:.0f} % je Treffer")
    print(T.groupby("jahr").agg(trades=("win", "size"), treffer=("win", "mean")).round(3).to_string())
    best = cur = 0
    for w in T.win:
        cur = cur + 1 if w else 0
        best = max(best, cur)
    print(f"Längste Trefferserie: {best}")
    if modus == "serie":
        # wie live: Spielgeld = Konto - Tresor; Ziel -> Teil bleibt im Spiel, Rest Tresor; Liquidation -> aus Tresor auffüllen
        neu, e = float(cfg.get("neustart_usdt", 30)), cfg.get("serie_einsatz", 0.97)
        pol, pol_anteil = float(cfg.get("polster_usdt", 0.0)), float(cfg.get("polster_anteil", 0.5))
        spiel, tresor, ext, hits = a.start, a.tresor_start, a.start + a.tresor_start, 0
        grenze = pol + a.tresor_start
        for r in T.sort_values("entry").r:
            gewinn = e * spiel * r
            if r > 0 and pol > 0 and tresor < grenze:          # wie live: Teil des Gewinns sofort ins Polster
                tresor += pol_anteil * gewinn
                gewinn *= 1 - pol_anteil
            spiel += gewinn
            if spiel >= cfg["ziel_usdt"]:
                bleibt = max(neu, cfg.get("im_spiel_nach_ziel", 0.2) * spiel)
                tresor += spiel - bleibt; spiel = bleibt; hits += 1
            elif spiel < neu:                         # wie live: unter neustart_usdt aus dem Tresor auffüllen
                need = neu - spiel
                if tresor >= need:
                    tresor -= need
                else:
                    ext += need - tresor; tresor = 0.0
                spiel = neu
        print(f"Serie ab {a.start:.0f} USDT + Reserve {a.tresor_start:.0f}, Ziel {cfg['ziel_usdt']}, danach "
              f"{cfg.get('im_spiel_nach_ziel', 0.2) * 100:.0f} % im Spiel, Polster {pol:.0f}: "
              f"{hits}x erreicht | eingezahlt {ext:.0f} | Tresor {tresor:.0f} | Spielgeld {spiel:.0f} | netto {tresor + spiel - ext:+.0f} USDT")
    else:
        k, peak, mdd, op = a.start, a.start, 0.0, []
        for _, row in T.sort_values("entry").iterrows():
            while op and op[0][0] <= row.entry:
                _, m, r = heapq.heappop(op); k += m * r; peak = max(peak, k); mdd = max(mdd, 1 - k / peak)
            m = min(f * k, k - sum(x[1] for x in op))
            if m > 0:
                heapq.heappush(op, (row.exit, m, row.r))
        while op:
            _, m, r = heapq.heappop(op); k += m * r; peak = max(peak, k); mdd = max(mdd, 1 - k / peak)
        print(f"Anteil {f * 100:.0f} %: {a.start:.2f} -> {k:.2f} USDT, größter Rückgang {mdd * 100:.0f} %")
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    T.to_csv(os.path.join(ROOT, "data", "backtest_trades.csv"), index=False)


if __name__ == "__main__":
    main()
