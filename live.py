"""zockerbot – Live-Betrieb auf Bitget (USDT-Perpetuals), Strategie „Ausbruch stark“.

Alle 15 Minuten kurz nach Kerzenschluss:
  1. Offene Positionen prüfen: Take-Profit vorhanden? Sonst neu setzen.
     Ist eine Position seit dem letzten Lauf verschwunden: Ergebnis (TP oder Liquidation) melden,
     Serienzähler fortschreiben.
  2. Einmal pro UTC-Tag für alle Coins die Tagesbedingung bestimmen (strategy.day_flags).
  3. Für Coins mit aktiver Tagesbedingung das 15m-Signal prüfen (strategy.signals) und – solange
     weniger als `max_positionen` offen sind – einsteigen: Market-Order, isolierte Margin,
     Take-Profit als reduce-only Trigger-Order. Kein Stop-Loss.

Modus „serie“: jeder Trade mit (fast) dem ganzen Spielgeld, Gewinne laufen mit (Zinseszins).
  Spielgeld = Konto minus Tresor. Erreicht das Spielgeld `ziel_usdt`, bleibt `im_spiel_nach_ziel`
  (mindestens `neustart_usdt`) im Spiel, der Rest wandert in den Tresor und wird nie eingesetzt.
  Nach einer Liquidation füllt der Bot das Spielgeld aus dem Tresor wieder auf `neustart_usdt` auf.
  Polster: Solange der Tresor unter `polster_usdt` plus eigener Reserve (--tresor) liegt, geht
  `polster_anteil` jedes Gewinns sofort in den Tresor.
  Hebst du ab, erkennt der Bot den gesunkenen Kontostand und verkleinert den Tresor entsprechend.
Modus „anteil“: jeder Trade mit `margin_fraction` des Kontos (ohne Tresor).

Aufruf:
  python3 live.py               Dauerbetrieb (über start.sh / Cron-Wächter)
  python3 live.py --check       nur anzeigen: Konto, Tresor, Positionen, Tagesbedingungen, Signale (keine Orders)
  python3 live.py --once        genau einen Durchlauf ausführen (mit Orders)
  python3 live.py --tresor 250  Tresor von Hand auf 250 USDT setzen
"""
import argparse
import csv
import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

import strategy
from exchange import Exchange

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
LOGS = os.path.join(ROOT, "logs")
STATE = os.path.join(DATA, "state.json")
TRADES = os.path.join(DATA, "trades.csv")
log = logging.getLogger("zockerbot")
DAY_CACHE = {"datum": None, "flags": {}}


def setup_logging():
    os.makedirs(LOGS, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(os.path.join(LOGS, "zockerbot.log"), maxBytes=2_000_000,
                                              backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [fh, sh]


def load_json(path, what):
    if not os.path.exists(path):
        sys.exit(f"FEHLER: {what} fehlt: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_settings():
    cfg = load_json(os.path.join(ROOT, "settings.json"), "settings.json")
    for k in ("coins", "modus", "leverage", "tp_pct", "max_positionen"):
        if k not in cfg:
            sys.exit(f"FEHLER: settings.json: Eintrag '{k}' fehlt.")
    if cfg["modus"] not in ("serie", "anteil"):
        sys.exit("FEHLER: settings.json: 'modus' muss 'serie' oder 'anteil' sein.")
    return cfg


def load_secret(required=True):
    path = os.path.join(ROOT, "secret.json")
    if not os.path.exists(path):
        if required:
            sys.exit("FEHLER: secret.json fehlt. Vorlage secret.json.template kopieren und Bitget-Schlüssel eintragen.")
        return {}, {}
    s = load_json(path, "secret.json")
    acc = s.get("zockerbot")
    if isinstance(acc, list):
        acc = acc[0] if acc else None
    if required and (not acc or not acc.get("apiKey")):
        sys.exit("FEHLER: secret.json enthält keinen Eintrag 'zockerbot' mit apiKey/secret/password.")
    return acc or {}, s.get("telegram", {})


def telegram(tg: dict, text: str):
    if not tg.get("bot_token") or not tg.get("chat_id"):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage",
                      data={"chat_id": tg["chat_id"], "text": text}, timeout=10)
    except Exception as e:
        log.warning(f"Telegram: {e}")


def load_state():
    st = {}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
    st.setdefault("open", {})
    st.setdefault("serie", 0)
    st.setdefault("beste_serie", 0)
    st.setdefault("tresor", 0.0)
    st.setdefault("reserve_eigen", 0.0)
    st.setdefault("ziele", 0)
    st.setdefault("leer_gemeldet", False)
    st.pop("pausiert", None)
    return st


def save_state(st):
    os.makedirs(DATA, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE)


def log_trade(row: dict):
    os.makedirs(DATA, exist_ok=True)
    new = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def sym(coin: str) -> str:
    return f"{coin}/USDT:USDT"


def gain_per_hit(cfg) -> float:
    return cfg["tp_pct"] * cfg["leverage"] - (cfg.get("taker_fee", 0.0006) + cfg.get("maker_fee", 0.0002)) * cfg["leverage"]


def refresh_day_flags(ex, cfg, force=False):
    """Einmal je UTC-Tag: Tagesbedingung aller Coins aus der letzten abgeschlossenen Tageskerze."""
    today = pd.Timestamp.now(tz="UTC").date()
    if DAY_CACHE["datum"] == today and not force:
        return DAY_CACHE["flags"]
    flags = {}
    for coin in cfg["coins"]:
        try:
            d1 = ex.closed_only(ex.fetch_ohlcv(sym(coin), "1d", 150), "1d")
            if len(d1) < cfg.get("strategy", {}).get("donchian_days", 40) + 20:
                continue
            f = int(strategy.day_flags(d1, cfg.get("strategy", {})).iloc[-1])
            if f:
                flags[coin] = f
        except Exception as e:
            log.error(f"Tageskerzen {coin}: {type(e).__name__}: {e}")
            return DAY_CACHE["flags"] if DAY_CACHE["datum"] else {}
    DAY_CACHE.update(datum=today, flags=flags)
    log.info(f"Tagesbedingung {today}: " + (", ".join(f"{c} {'Long' if v > 0 else 'Short'}" for c, v in flags.items()) or "kein Coin"))
    return flags


def current_signal(ex, coin, params, fresh_only=True):
    """Signal der zuletzt abgeschlossenen 15m-Kerze (dieselbe Funktion wie im Backtest)."""
    df15 = ex.closed_only(ex.fetch_ohlcv(sym(coin), "15m", 400), "15m")
    df1d = ex.closed_only(ex.fetch_ohlcv(sym(coin), "1d", 150), "1d")
    if len(df15) < 100 or len(df1d) < 60:
        return 0, None
    sig = strategy.signals(df15, df1d, params)
    last = df15.index[-1]
    age = pd.Timestamp.now(tz="UTC") - (last + pd.Timedelta(minutes=15))
    if fresh_only and age > pd.Timedelta(minutes=10):
        log.warning(f"{coin}: letzte 15m-Kerze ist {age} alt, kein Einstieg")
        return 0, last
    return int(sig.iloc[-1]), last


def place_tp(ex, coin, side, amount, tp) -> bool:
    for attempt in range(2):
        try:
            ex.take_profit(sym(coin), "sell" if side > 0 else "buy", amount, tp)
            return True
        except Exception as e:
            log.error(f"TP {coin} fehlgeschlagen ({attempt + 1}/2): {e}")
            time.sleep(2)
    return False


def check_closed(ex, cfg, st, tg, coin):
    """Position aus dem Zustand ist auf der Börse weg -> Ergebnis feststellen, Serie fortschreiben, melden."""
    t = st["open"].pop(coin)
    ex.cancel_all(sym(coin))
    since = pd.Timestamp(t["opened"])
    minutes = int((pd.Timestamp.now(tz="UTC") - since).total_seconds() // 60) + 5
    tf, n = ("1m", minutes) if minutes <= 2900 else ("15m", minutes // 15 + 2)
    df = ex.fetch_ohlcv(sym(coin), tf, min(n, 3000))
    df = df[df.index >= since.floor("15min")]
    side, tp = t["side"], t["tp"]
    hit = bool((df["high"] >= tp).any()) if side > 0 else bool((df["low"] <= tp).any())
    polster_msg = ""
    if hit:
        st["serie"] += 1
        st["beste_serie"] = max(st["beste_serie"], st["serie"])
        pnl = t["margin"] * gain_per_hit(cfg)
        result = "TP"
        grenze = cfg.get("polster_usdt", 0.0) + st.get("reserve_eigen", 0.0)
        if cfg["modus"] == "serie" and cfg.get("polster_usdt", 0.0) > 0 and st["tresor"] < grenze:
            teil = pnl * cfg.get("polster_anteil", 0.5)           # Polster: Teil des Gewinns sofort in den Tresor
            st["tresor"] += teil
            polster_msg = f"\n{teil:.2f} USDT ins Polster (Tresor {st['tresor']:.2f} von {grenze:.0f} USDT)"
    else:
        st["serie"] = 0
        pnl = -t["margin"]
        result = "Liquidation/manuell"
    log_trade({"geschlossen": datetime.now(timezone.utc).isoformat(timespec="seconds"), "coin": coin,
               "richtung": "Long" if side > 0 else "Short", "einstieg": t["entry"], "tp": tp, "menge": t["amount"],
               "margin": round(t["margin"], 4), "ergebnis": result, "pnl_ca": round(pnl, 4),
               "serie_danach": st["serie"], "eroeffnet": t["opened"]})
    if hit:
        msg = (f"zockerbot TREFFER {st['serie']} in Folge: {coin} {'Long' if side > 0 else 'Short'}\n"
               f"+{gain_per_hit(cfg) * 100:.0f} % auf {t['margin']:.2f} USDT Margin = ca. +{pnl:.2f} USDT\n"
               f"Beste Serie bisher: {st['beste_serie']}" + polster_msg)
    else:
        msg = (f"zockerbot Serie beendet: {coin} {'Long' if side > 0 else 'Short'} liquidiert\n"
               f"Margin {t['margin']:.2f} USDT verloren")
    try:
        eq, _ = ex.fetch_equity()
        msg += f"\nKonto {eq:.2f} USDT | Tresor {st['tresor']:.2f} | Spielgeld {eq - st['tresor']:.2f}"
    except Exception:
        pass
    log.info(msg.replace("\n", " | "))
    telegram(tg, msg)
    save_state(st)


def open_trade(ex, cfg, st, tg, coin, side, equity, free):
    lev = int(cfg["leverage"])
    if cfg["modus"] == "serie":
        spiel = equity - st["tresor"]
        margin = min(spiel * cfg.get("serie_einsatz", 0.97), free * 0.97)
    else:
        margin = min(cfg["margin_fraction"] * equity, free * 0.97)
    if margin < cfg.get("min_margin_usdt", 5.0):
        log.info(f"{coin}: Signal, aber zu wenig freie Margin ({margin:.2f} USDT)")
        return False
    ex.set_isolated(sym(coin))
    ex.set_leverage(sym(coin), lev)
    price = float(ex.exchange.fetch_ticker(sym(coin))["last"])
    amount = margin * lev / price
    if amount < ex.min_amount(sym(coin)):
        log.info(f"{coin}: Menge {amount:.6g} unter Börsen-Minimum {ex.min_amount(sym(coin))}")
        return False
    order = ex.market_order(sym(coin), "buy" if side > 0 else "sell", amount)
    entry = float(order.get("average") or order.get("price") or price)
    filled = float(order.get("filled") or order.get("amount") or amount)
    tp = strategy.tp_price(entry, side, cfg["tp_pct"])
    time.sleep(1)
    tp_ok = place_tp(ex, coin, side, filled, tp)
    st["open"][coin] = {"side": side, "entry": entry, "tp": tp, "amount": filled, "margin": margin,
                        "opened": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save_state(st)
    liq = strategy.liquidation_distance(lev) * 100
    msg = (f"zockerbot {coin} {'LONG' if side > 0 else 'SHORT'} – Trade {st['serie'] + 1} der Serie\n"
           f"Einstieg {entry:.6g} | TP {tp:.6g} ({cfg['tp_pct'] * 100:+.1f} %) | ohne SL, Liquidation bei ca. {liq:.1f} %\n"
           f"Margin {margin:.2f} USDT x{lev} | Konto {equity:.2f} USDT | Modus {cfg['modus']}"
           + ("" if tp_ok else "\nACHTUNG: TP konnte nicht gesetzt werden, nächster Lauf versucht es erneut"))
    log.info(msg.replace("\n", " | "))
    telegram(tg, msg)
    return True


def tresor_verwalten(cfg, st, tg, equity):
    """Abhebung erkennen, Ziel sichern, nach Liquidation aus dem Tresor auffüllen (nur Buchhaltung im Zustand)."""
    neu = float(cfg.get("neustart_usdt", 30.0))
    t0 = st["tresor"]
    if t0 > 0 and equity < t0 - 0.5:                        # abgehoben (Konto kleiner als Tresor): Tresor schrumpft mit
        st["tresor"] = max(0.0, equity - neu) if equity > neu else 0.0
        st["reserve_eigen"] = min(st.get("reserve_eigen", 0.0), st["tresor"])
        telegram(tg, f"zockerbot: Abhebung erkannt. Konto {equity:.2f} USDT, Tresor jetzt {st['tresor']:.2f} USDT.")
    spiel = equity - st["tresor"]
    if spiel >= cfg.get("ziel_usdt", 1e18):                  # Ziel: Teil bleibt im Spiel, Rest in den Tresor
        bleibt = max(neu, cfg.get("im_spiel_nach_ziel", 0.20) * spiel)
        st["tresor"] += spiel - bleibt
        st["ziele"] += 1
        st["serie"] = 0
        telegram(tg, f"zockerbot ZIEL {st['ziele']} ERREICHT: Spielgeld {spiel:.2f} USDT.\n"
                     f"{spiel - bleibt:.2f} USDT in den Tresor, {bleibt:.2f} USDT spielen weiter.\n"
                     f"Tresor gesamt {st['tresor']:.2f} USDT – kann jederzeit abgehoben werden.")
        log.info(f"Ziel erreicht: Tresor {st['tresor']:.2f}, Spielgeld {bleibt:.2f}")
    elif spiel < neu and st["tresor"] > 0:                    # nach Liquidation: aus dem Tresor auffüllen
        nachschub = min(neu - spiel, st["tresor"])
        st["tresor"] -= nachschub
        telegram(tg, f"zockerbot: neue Serie mit {spiel + nachschub:.2f} USDT – {nachschub:.2f} USDT aus dem Tresor "
                     f"(Tresor jetzt {st['tresor']:.2f} USDT).")
        log.info(f"Aus Tresor aufgefüllt: {nachschub:.2f}, Tresor {st['tresor']:.2f}")
    if st["tresor"] != t0:
        save_state(st)


def cycle(ex, cfg, tg, dry=False):
    st = load_state()
    keys = bool(ex.exchange.apiKey)
    params = cfg.get("strategy", {})
    equity, free = ex.fetch_equity() if keys else (0.0, 0.0)
    pos = ex.fetch_all_open_positions() if keys else {}
    mine = {c: p for c, p in pos.items() if c in cfg["coins"]}

    if dry:
        print(f"  Modus {cfg['modus']} | Konto {equity:.2f} USDT, frei {free:.2f} | Tresor {st['tresor']:.2f} | "
              f"Spielgeld {equity - st['tresor']:.2f} | Serie {st['serie']} (beste {st['beste_serie']}) | Ziele erreicht {st['ziele']}")
        for c, p in mine.items():
            print(f"  offen: {c} {p.get('side')} {p.get('contracts')} @ {p.get('entryPrice')}")
    else:
        log.info(f"Durchlauf: Konto {equity:.2f} USDT, frei {free:.2f}, offen {list(mine)}, Serie {st['serie']}")
        # 1. offene Positionen und geschlossene Trades
        for coin in list(st["open"]):
            try:
                if coin in mine:
                    if not ex.fetch_open_trigger_orders(sym(coin)):
                        log.warning(f"{coin}: Position ohne TP gefunden, setze TP neu")
                        t = st["open"][coin]
                        place_tp(ex, coin, t["side"], float(mine[coin]["contracts"]), t["tp"])
                else:
                    check_closed(ex, cfg, st, tg, coin)
                    equity, free = ex.fetch_equity()
            except Exception as e:
                log.error(f"{coin}: {type(e).__name__}: {e}", exc_info=True)
        # 2. Tresor (nur ohne offene Position, damit offene Gewinne/Verluste nichts verfälschen)
        if cfg["modus"] == "serie" and keys and not mine:
            tresor_verwalten(cfg, st, tg, equity)
        spiel = equity - st["tresor"] if cfg["modus"] == "serie" else equity
        if keys and not mine and spiel < cfg.get("min_margin_usdt", 5.0):
            if not st["leer_gemeldet"]:
                st["leer_gemeldet"] = True
                save_state(st)
                telegram(tg, f"zockerbot: Spielgeld leer ({spiel:.2f} USDT) und Tresor aufgebraucht. "
                             f"Für eine neue Serie USDT auf das Futures-Konto einzahlen.")
            return
        if st["leer_gemeldet"]:
            st["leer_gemeldet"] = False
            save_state(st)

    # 3. Signale
    flags = refresh_day_flags(ex, cfg)
    if dry:
        print("  Tagesbedingung heute: " + (", ".join(f"{c} {'Long' if v > 0 else 'Short'}" for c, v in flags.items()) or "kein Coin"))
    n_open = len(set(mine) | set(st["open"]))
    for coin in cfg["coins"]:
        if coin not in flags or coin in mine:
            continue
        if not dry and n_open >= cfg["max_positionen"]:
            break
        try:
            sig, last = current_signal(ex, coin, params, fresh_only=not dry)
            if dry:
                print(f"  {coin:5s} letzte 15m-Kerze {last} -> Signal {['Short', '-', 'Long'][sig + 1]}")
                continue
            if sig != 0 and sig == flags[coin]:
                if open_trade(ex, cfg, st, tg, coin, sig, equity, free):
                    n_open += 1
                    equity, free = ex.fetch_equity()
        except Exception as e:
            log.error(f"{coin}: {type(e).__name__}: {e}", exc_info=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="nur anzeigen, keine Orders")
    ap.add_argument("--once", action="store_true", help="einen Durchlauf mit Orders")
    ap.add_argument("--tresor", type=float, default=None, help="Tresor von Hand auf diesen Betrag (USDT) setzen")
    a = ap.parse_args()
    setup_logging()
    cfg = load_settings()
    if a.tresor is not None:
        if a.tresor < 0:
            sys.exit("FEHLER: --tresor braucht einen Betrag >= 0.")
        st = load_state()
        st["tresor"] = float(a.tresor)
        st["reserve_eigen"] = float(a.tresor)                 # eigene Reserve: Polster wird zusätzlich darauf aufgebaut
        save_state(st)
        print(f"Tresor auf {a.tresor:.2f} USDT gesetzt (eigene Reserve). Polster-Grenze jetzt "
              f"{a.tresor + cfg.get('polster_usdt', 0.0):.0f} USDT. Der laufende Bot nutzt die Werte ab dem nächsten 15m-Takt.")
        return
    acc, tg = load_secret(required=not a.check)
    ex = Exchange(acc)
    if a.check:
        print(f"zockerbot --check  ({len(cfg['coins'])} Coins, x{cfg['leverage']}, TP {cfg['tp_pct'] * 100:.1f} %, "
              f"max. {cfg['max_positionen']} Position(en), Modus {cfg['modus']})")
        cycle(ex, cfg, tg, dry=True)
        return
    if a.once:
        cycle(ex, cfg, tg)
        return
    telegram(tg, f"zockerbot gestartet: {len(cfg['coins'])} Coins, x{cfg['leverage']}, TP {cfg['tp_pct'] * 100:.1f} %, "
                 f"max. {cfg['max_positionen']} Position(en), Modus {cfg['modus']}"
                 + (f", Ziel {cfg.get('ziel_usdt')} USDT, danach {cfg.get('im_spiel_nach_ziel', 0.2) * 100:.0f} % im Spiel, "
                    f"Rest in den Tresor" if cfg["modus"] == "serie" else f", {cfg['margin_fraction'] * 100:.0f} % je Trade"))
    delay = int(cfg.get("delay_after_close_s", 20))
    while True:
        now = time.time()
        nxt = (now // 900 + 1) * 900 + delay
        time.sleep(max(1, nxt - now))
        try:
            cycle(ex, cfg, tg)
        except Exception as e:
            log.error(f"Durchlauf abgebrochen: {type(e).__name__}: {e}", exc_info=True)


if __name__ == "__main__":
    main()
