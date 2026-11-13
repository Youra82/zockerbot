"""zockerbot – Live-Betrieb auf Bitget (USDT-Perpetuals).

Alle 15 Minuten kurz nach Kerzenschluss:
  1. Für jeden Coin: Position prüfen. Ist eine offen, sicherstellen, dass der Take-Profit steht.
     Ist eine Position seit dem letzten Lauf verschwunden: Ergebnis (TP oder Liquidation) melden.
  2. Ohne Position: Signal auf der gerade abgeschlossenen 15m-Kerze berechnen (strategy.signals)
     und bei Signal einsteigen: Market-Order, isolierte Margin, Hebel laut settings.json,
     Margin = Anteil des Kontos, Take-Profit als reduce-only Trigger-Order. Kein Stop-Loss.

Aufruf:
  python3 live.py            Dauerbetrieb (über start.sh / Cron-Wächter)
  python3 live.py --check    nur anzeigen: Kontostand, Positionen, aktuelles Signal je Coin (keine Orders)
  python3 live.py --once     genau einen Durchlauf ausführen (mit Orders)
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
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"open": {}}


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


def current_signal(ex: Exchange, symbol: str, params: dict, fresh_only: bool = True):
    """Signal der zuletzt abgeschlossenen 15m-Kerze. Live nur gültig, wenn diese Kerze gerade erst schloss."""
    df15 = ex.closed_only(ex.fetch_ohlcv(symbol, "15m", 400), "15m")
    df1d = ex.closed_only(ex.fetch_ohlcv(symbol, "1d", 150), "1d")
    if len(df15) < 100 or len(df1d) < 40:
        log.warning(f"{symbol}: zu wenig Kerzen ({len(df15)} x 15m, {len(df1d)} x 1d)")
        return 0, None
    sig = strategy.signals(df15, df1d, params)
    last = df15.index[-1]
    age = pd.Timestamp.now(tz="UTC") - (last + pd.Timedelta(minutes=15))
    if fresh_only and age > pd.Timedelta(minutes=10):
        log.warning(f"{symbol}: letzte 15m-Kerze ist {age} alt, kein Einstieg")
        return 0, last
    return int(sig.iloc[-1]), last


def check_closed(ex, cfg, st, tg, coin, symbol):
    """Position aus dem Zustand ist auf der Börse weg -> Ergebnis feststellen und melden."""
    t = st["open"].pop(coin)
    ex.cancel_all(symbol)                      # übrig gebliebenen TP entfernen
    since = pd.Timestamp(t["opened"])
    minutes = int((pd.Timestamp.now(tz="UTC") - since).total_seconds() // 60) + 5
    df = ex.fetch_ohlcv(symbol, "1m" if minutes <= 3000 else "15m", min(minutes if minutes <= 3000 else minutes // 15 + 2, 3000))
    df = df[df.index >= since.floor("15min")]
    side, tp = t["side"], t["tp"]
    hit = bool((df["high"] >= tp).any()) if side > 0 else bool((df["low"] <= tp).any())
    result = "TP" if hit else "Liquidation/manuell"
    pnl = t["margin"] * (cfg["tp_pct"] * cfg["leverage"]) if hit else -t["margin"]
    log_trade({"geschlossen": datetime.now(timezone.utc).isoformat(timespec="seconds"), "coin": coin,
               "richtung": "Long" if side > 0 else "Short", "einstieg": t["entry"], "tp": tp,
               "menge": t["amount"], "margin": round(t["margin"], 4), "ergebnis": result,
               "pnl_ca": round(pnl, 4), "eroeffnet": t["opened"]})
    msg = (f"zockerbot {coin} {'Long' if side > 0 else 'Short'} geschlossen: {result}\n"
           f"Einstieg {t['entry']:.6g} | TP {tp:.6g} | Margin {t['margin']:.2f} USDT | ca. {pnl:+.2f} USDT")
    log.info(msg.replace("\n", " | "))
    telegram(tg, msg)


def place_tp(ex, symbol, side, amount, tp) -> bool:
    for attempt in range(2):
        try:
            ex.take_profit(symbol, "sell" if side > 0 else "buy", amount, tp)
            return True
        except Exception as e:
            log.error(f"TP {symbol} fehlgeschlagen ({attempt + 1}/2): {e}")
            time.sleep(2)
    return False


def open_trade(ex, cfg, st, tg, coin, symbol, side, equity, free):
    lev = int(cfg["leverage"])
    margin = min(cfg["margin_fraction"] * equity, free * 0.95)
    if margin < cfg.get("min_margin_usdt", 1.0):
        log.info(f"{coin}: Signal, aber zu wenig freie Margin ({margin:.2f} USDT)")
        return
    ex.set_isolated(symbol)
    ex.set_leverage(symbol, lev)
    price = float(ex.exchange.fetch_ticker(symbol)["last"])
    amount = margin * lev / price
    if amount < ex.min_amount(symbol):
        log.info(f"{coin}: Menge {amount:.6g} unter Börsen-Minimum {ex.min_amount(symbol)}")
        return
    order = ex.market_order(symbol, "buy" if side > 0 else "sell", amount)
    entry = float(order.get("average") or order.get("price") or price)
    filled = float(order.get("filled") or order.get("amount") or amount)
    tp = strategy.tp_price(entry, side, cfg["tp_pct"])
    time.sleep(1)
    tp_ok = place_tp(ex, symbol, side, filled, tp)
    st["open"][coin] = {"side": side, "entry": entry, "tp": tp, "amount": filled, "margin": margin,
                        "opened": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save_state(st)
    liq = strategy.liquidation_distance(lev) * 100
    msg = (f"zockerbot {coin} {'LONG' if side > 0 else 'SHORT'} eröffnet\n"
           f"Einstieg {entry:.6g} | TP {tp:.6g} ({cfg['tp_pct'] * 100:+.1f} %) | ohne SL, Liquidation bei ca. {liq:.1f} %\n"
           f"Margin {margin:.2f} USDT x{lev} | Konto {equity:.2f} USDT"
           + ("" if tp_ok else "\nACHTUNG: TP konnte nicht gesetzt werden, nächster Lauf versucht es erneut"))
    log.info(msg.replace("\n", " | "))
    telegram(tg, msg)


def cycle(ex, cfg, tg, dry=False):
    st = load_state()
    keys = bool(ex.exchange.apiKey)
    equity, free = ex.fetch_equity() if keys else (0.0, 0.0)
    if not dry:
        log.info(f"Durchlauf: Konto {equity:.2f} USDT, frei {free:.2f} USDT, offen: {list(st['open'])}")
    params = cfg.get("strategy", {})
    for coin in cfg["coins"]:
        symbol = f"{coin}/USDT:USDT"
        try:
            if keys:
                pos = ex.fetch_open_positions(symbol)
                if pos:
                    t = st["open"].get(coin)
                    if dry:
                        print(f"  {coin:5s} Position offen: {pos[0].get('side')} {pos[0].get('contracts')} @ {pos[0].get('entryPrice')}")
                    elif t and not ex.fetch_open_trigger_orders(symbol):
                        log.warning(f"{coin}: Position ohne TP gefunden, setze TP neu")
                        place_tp(ex, symbol, t["side"], float(pos[0]["contracts"]), t["tp"])
                    continue
                if coin in st["open"] and not dry:
                    check_closed(ex, cfg, st, tg, coin, symbol)
                    save_state(st)
            sig, last = current_signal(ex, symbol, params, fresh_only=not dry)
            if dry:
                print(f"  {coin:5s} letzte 15m-Kerze {last} -> Signal {['Short', '-', 'Long'][sig + 1]}")
                continue
            if sig != 0:
                open_trade(ex, cfg, st, tg, coin, symbol, sig, equity, free)
                equity, free = ex.fetch_equity()
        except Exception as e:
            log.error(f"{coin}: {type(e).__name__}: {e}", exc_info=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="nur anzeigen, keine Orders")
    ap.add_argument("--once", action="store_true", help="einen Durchlauf mit Orders")
    a = ap.parse_args()
    setup_logging()
    cfg = load_json(os.path.join(ROOT, "settings.json"), "settings.json")
    acc, tg = load_secret(required=not a.check)
    ex = Exchange(acc)
    if a.check:
        print(f"zockerbot --check  ({len(cfg['coins'])} Coins, x{cfg['leverage']}, TP {cfg['tp_pct'] * 100:.1f} %, "
              f"Margin {cfg['margin_fraction'] * 100:.0f} % je Trade)")
        if ex.exchange.apiKey:
            e, f = ex.fetch_equity()
            print(f"  Konto {e:.2f} USDT, frei {f:.2f} USDT")
        cycle(ex, cfg, tg, dry=True)
        return
    if a.once:
        cycle(ex, cfg, tg)
        return
    telegram(tg, f"zockerbot gestartet: {len(cfg['coins'])} Coins, x{cfg['leverage']}, TP {cfg['tp_pct'] * 100:.1f} %, "
                 f"Margin {cfg['margin_fraction'] * 100:.0f} % je Trade")
    delay = int(cfg.get("delay_after_close_s", 20))
    while True:
        now = time.time()
        nxt = (now // 900 + 1) * 900 + delay
        time.sleep(max(1, nxt - now))
        cycle(ex, cfg, tg)


if __name__ == "__main__":
    main()
