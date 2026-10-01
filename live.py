# zockerbot/live.py — DRY-RUN: taeglich nach Tagesschluss entscheidet Claude, das Konto ist simuliert.
#   python live.py            Dauerbetrieb (prueft alle 10 min, holt verpasste Tage nach)
#   python live.py --prompt   zeigt nur den heutigen Auftrag an die KI (kein API-Aufruf, kostenlos)
#   python live.py --mock     ein Durchlauf mit einer Test-Entscheidung statt KI (kostenlos)
# API-Schluessel: Umgebungsvariable ANTHROPIC_API_KEY oder secret.json {"anthropic_api_key": "..."}
import json, os, sys, time, datetime, traceback
import ccxt
import pandas as pd
from data import build_report
from logic import size_positions, settle_day, rebalance
import brain

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ZOCKERBOT_DATA", os.path.join(HERE, "data_dryrun"))
STATE = os.path.join(DATA, "state.json")
COSTS = os.path.join(DATA, "api_costs.jsonl")
os.makedirs(DATA, exist_ok=True)
CFG = json.load(open(os.path.join(HERE, "settings.json")))


def log(msg):
    line = f"[{datetime.datetime.now(datetime.UTC):%Y-%m-%d %H:%M:%S} UTC] {msg}"
    print(line, flush=True)
    with open(os.path.join(DATA, "zockerbot.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def append(name, rec):
    with open(os.path.join(DATA, name), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"equity": CFG["start_equity"], "positions": {}, "last_day": None, "memory": [], "pause_until": None}


def save_state(st):
    json.dump(st, open(STATE + ".tmp", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(STATE + ".tmp", STATE)


def api_key_ready():
    s = os.path.join(HERE, "secret.json")
    if not os.environ.get("ANTHROPIC_API_KEY") and os.path.exists(s):
        k = json.load(open(s)).get("anthropic_api_key")
        if k:
            os.environ["ANTHROPIC_API_KEY"] = k
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def portfolio_view(st):
    return {"kapital_usdt": round(st["equity"], 2),
            "positionen": {c: {"seite": "long" if p["side"] > 0 else "short", "gewicht": round(p["weight"], 3),
                               "einstieg": p["entry"], "aktuell": p["mark"],
                               "ergebnis_%": round(p["side"] * (p["mark"] / p["entry"] - 1) * 100, 2),
                               "these": p.get("thesis", "")} for c, p in st["positions"].items()}}


MOCK = {"marktlage": "Testlauf ohne KI", "notiz_fuer_morgen": "-", "positions": [
    {"coin": "BTC", "side": "long", "win_probability": 0.55, "reward_risk": 2.0, "stop_loss_pct": 5,
     "take_profit_pct": 10, "thesis": "Test"}]}


def run_once(ex, mode=None):
    st = load_state()
    day, market, feats, ohlc, fund, C = build_report(ex, CFG["coins"])
    if st["last_day"] == str(day.date()) and mode is None:
        return False
    # 1) verpasste + heutige Tage abrechnen (Stop/Ziel ueber Tageshoch/-tief, Funding) — ohne neue KI-Entscheidungen
    if st["last_day"]:
        days = [d for d in C["BTC"].index if d > pd.Timestamp(st["last_day"]) and d <= day]
        if len(days) > 1:
            log(f"Bot lief nicht (PC aus?): {len(days)} Tage werden abgerechnet, Positionen liefen weiter.")
        for d in days:
            o = {b: tuple(float(x) for x in df.loc[d, ["o", "h", "l", "c"]]) for b, df in C.items() if d in df.index}
            ret, st["positions"], closed = settle_day(st["positions"], o, fund if d == day else {}, CFG["taker_fee"])
            before = st["equity"]; st["equity"] *= 1 + ret
            for t in closed:
                log(f"{d.date()}: {t['coin']} {'long' if t['side'] > 0 else 'short'} geschlossen ({t['reason']}) {t['pnl_pct']:+.1f} %")
                append("trades.jsonl", {"day": str(d.date()), **t})
            append("daily.jsonl", {"day": str(d.date()), "ret": ret, "equity": st["equity"], "late": d != day})
            if st["memory"]:
                st["memory"][-1].setdefault("ergebnis_tage", []).append(round(ret * 100, 2))
            if ret <= -CFG["daily_loss_stop"]:
                st["pause_until"] = str((d + pd.Timedelta(days=1)).date())
                log(f"Tagesverlust {ret:+.1%} -> Verluststopp: alles schliessen, Pause bis {st['pause_until']}")
            log(f"{d.date()}: Tag {ret:+.2%} -> Konto {st['equity']:.2f} USDT ({before:.2f} vorher)")
    st["last_day"] = str(day.date())
    prices = {b: v[3] for b, v in ohlc.items()}
    # 2) Entscheidung
    if st.get("pause_until") and str(day.date()) <= st["pause_until"]:
        new, cost = rebalance(st["positions"], {}, prices, CFG["taker_fee"])
        st["positions"] = new; st["equity"] *= 1 - cost
        save_state(st); return True
    msg = brain.build_user_message(market, feats, portfolio_view(st), st["memory"][-CFG["memory_decisions"]:])
    if mode == "prompt":
        print(brain.SYSTEM + "\n\n" + msg); return True
    if mode == "mock":
        decision, usd, note = MOCK, 0.0, "Mock"
    elif CFG.get("backend", "abo") == "abo":
        decision, usd, note = brain.decide_abo(CFG, msg, DATA)
        log(f"KI-Entscheidung {note}")
    elif not api_key_ready():
        log("Kein API-Schluessel (ANTHROPIC_API_KEY oder secret.json) - keine Entscheidung, Positionen bleiben.")
        save_state(st); return True
    else:
        left = CFG["budget_usd_per_month"] - brain.month_spent(COSTS)
        decision, usd, note = brain.decide(CFG, msg, COSTS, left)
        log(f"KI-Kosten heute {usd:.4f} $ | diesen Monat {brain.month_spent(COSTS):.2f} von {CFG['budget_usd_per_month']:.2f} $")
    if decision is None:
        log(note); save_state(st); return True
    targets = size_positions(decision, CFG, CFG["coins"])
    st["positions"], cost = rebalance(st["positions"], targets, prices, CFG["taker_fee"])
    st["equity"] *= 1 - cost
    st["memory"].append({"tag": str(day.date()), "marktlage": decision.get("marktlage", "")[:400],
                         "positionen": [f"{c} {'long' if t['side'] > 0 else 'short'} {t['weight']:.0%} p={t['prob']:.2f}"
                                        for c, t in targets.items()],
                         "notiz": decision.get("notiz_fuer_morgen", "")[:300]})
    st["memory"] = st["memory"][-30:]
    append("decisions.jsonl", {"day": str(day.date()), "decision": decision, "targets": targets})
    pos = ", ".join(f"{c} {'LONG' if t['side'] > 0 else 'SHORT'} {t['weight']:.0%}" for c, t in targets.items()) or "keine (Cash)"
    log(f"Entscheidung {day.date()}: {pos} | {decision.get('marktlage', '')[:160]}")
    save_state(st)
    return True


def main():
    ex = ccxt.binance({"enableRateLimit": True})
    mode = "prompt" if "--prompt" in sys.argv else "mock" if "--mock" in sys.argv else None
    if mode:
        run_once(ex, mode); return
    log(f"zockerbot DRY-RUN gestartet | KI ueber {'Claude-Abo (Claude Code)' if CFG.get('backend', 'abo') == 'abo' else 'API, Budget ' + str(CFG['budget_usd_per_month']) + ' $/Monat'}")
    while True:
        try:
            if datetime.datetime.now(datetime.UTC).hour >= CFG["decision_after_utc_hour"]:
                run_once(ex)
        except Exception as e:
            log(f"Fehler: {e!r}"); traceback.print_exc()
        time.sleep(600)


if __name__ == "__main__":
    main()
