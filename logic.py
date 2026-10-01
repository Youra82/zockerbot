# zockerbot/logic.py — reine Rechenlogik (Groesse, Tagesabrechnung), ohne Netzwerk.
# Die KI liefert Richtung + Wahrscheinlichkeit + Chance/Risiko; die Einsatzhoehe kommt NICHT von der KI,
# sondern aus der Kelly-Formel mit Sicherheitsabschlag und harten Obergrenzen.


def size_positions(decision, cfg, coins):
    """Wandelt die KI-Entscheidung in Zielpositionen um: {coin: {side, weight, sl_pct, tp_pct, thesis}}.
    weight = Anteil des Kapitals als Positionswert. Kelly bezieht sich auf den Verlust beim Stop:
    Riskierter Anteil = weight * sl_pct = kelly_fraction * f*  ->  weight = kelly_fraction * f* / sl_pct."""
    out = {}
    for p in decision.get("positions", []):
        coin = p.get("coin")
        if coin not in coins or coin in out:
            continue
        side = 1 if p.get("side") == "long" else -1 if p.get("side") == "short" else 0
        prob = float(p.get("win_probability", 0)); rr = float(p.get("reward_risk", 0))
        sl = float(p.get("stop_loss_pct", 0)) / 100; tp = float(p.get("take_profit_pct", 0)) / 100
        if side == 0 or not (0.005 <= sl <= 0.5) or tp <= 0:
            continue
        f = prob - (1 - prob) / rr if rr > 0 else 0
        if f <= 0:
            continue
        w = min(cfg["max_position"], cfg["kelly_fraction"] * f / sl)
        out[coin] = {"side": side, "weight": w, "sl_pct": sl, "tp_pct": tp, "prob": prob, "rr": rr,
                     "thesis": p.get("thesis", "")[:300]}
    gross = sum(v["weight"] for v in out.values())
    if gross > cfg["max_gross_leverage"]:                     # gesamtes Exposure deckeln
        for v in out.values():
            v["weight"] *= cfg["max_gross_leverage"] / gross
    return out


def settle_day(positions, ohlc, funding, fee):
    """Rechnet einen Tag ab. positions: {coin: {side, weight, entry, sl, tp}} (Preise absolut).
    ohlc: {coin: (o, h, l, c)} des Tages, funding: {coin: Tagessumme}. Stop vor Ziel, falls beides moeglich
    (konservativ). Gibt (Tagesrendite aufs Kapital, uebrige Positionen, geschlossene Trades) zurueck."""
    ret = 0.0; keep = {}; closed = []
    for coin, p in positions.items():
        if coin not in ohlc:
            keep[coin] = p; continue
        o, h, l, c = ohlc[coin]
        s, w, ref = p["side"], p["weight"], p["mark"]
        hit_sl = (l <= p["sl"]) if s > 0 else (h >= p["sl"])
        hit_tp = (h >= p["tp"]) if s > 0 else (l <= p["tp"])
        if hit_sl:
            px, why = p["sl"], "STOP"
        elif hit_tp:
            px, why = p["tp"], "ZIEL"
        else:
            px, why = c, None
        ret += w * s * (px / ref - 1) - w * s * funding.get(coin, 0.0)   # Longs zahlen positives Funding
        if why:
            ret -= w * fee
            closed.append({"coin": coin, "side": s, "entry": p["entry"], "exit": px, "reason": why,
                           "pnl_pct": s * (px / p["entry"] - 1) * 100})
        else:
            keep[coin] = {**p, "mark": c}
    return ret, keep, closed


def rebalance(current, targets, prices, fee):
    """Setzt neue Zielpositionen zum aktuellen Kurs. Kosten = Gebuehr auf jede Gewichtsaenderung."""
    cost = 0.0; new = {}
    for coin in set(current) | set(targets):
        cur = current.get(coin); tgt = targets.get(coin)
        cw = cur["weight"] * cur["side"] if cur else 0.0
        tw = tgt["weight"] * tgt["side"] if tgt else 0.0
        cost += abs(tw - cw) * fee
        if tgt:
            px = prices[coin]
            keep_entry = cur and cur["side"] == tgt["side"]
            entry = cur["entry"] if keep_entry else px
            s = tgt["side"]
            new[coin] = {"side": s, "weight": tgt["weight"], "entry": entry, "mark": px,
                         "sl": px * (1 - s * tgt["sl_pct"]), "tp": px * (1 + s * tgt["tp_pct"]),
                         "thesis": tgt["thesis"], "prob": tgt["prob"], "rr": tgt["rr"]}
    return new, cost
