# zockerbot/brain.py — die Entscheidung trifft Claude; dieses Modul baut den Auftrag, ruft die API auf,
# prueft das Ergebnis und fuehrt Buch ueber die Kosten (hartes Monatsbudget).
import json, os, datetime
import anthropic

# $ pro 1 Mio. Token (Eingabe, Ausgabe) — fuer die Budgetkontrolle
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0),
          "claude-opus-4-8": (5.0, 25.0), "claude-opus-5": (5.0, 25.0)}

SYSTEM = """Du bist ein disziplinierter, professioneller Krypto-Spekulant ("schlauer Zocker"). Einmal pro Tag, nach
Tagesschluss (UTC), entscheidest du ueber ein Konto, das Perpetual-Futures auf zehn grosse Coins handeln darf
(long oder short). Du bekommst einen kompakten Marktbericht, dein aktuelles Portfolio und deine letzten Entscheidungen
mit ihrem Ergebnis.

Spielregeln:
- Du nennst je Idee Richtung, deine ehrliche Gewinnwahrscheinlichkeit, das Chance/Risiko-Verhaeltnis, Stop und Ziel.
  Die Einsatzhoehe berechnet das System selbst per Kelly-Formel aus deinen Zahlen — ueberschaetzte
  Wahrscheinlichkeiten kosten also direkt Geld. Sei kalibriert, nicht mutig.
- Keine Position ist eine vollwertige Entscheidung. Ohne erkennbaren Vorteil: leere Liste.
- Positionen, die du nicht erneut nennst, werden geschlossen. Was du halten willst, nenne erneut.
- Handelskosten: 0,06 % pro Ein- oder Ausstieg; Longs zahlen bei positivem Funding taeglich.
- Nutze nur die gelieferten Daten. Du kennst die Kurse nach dem Datum im Bericht nicht.

Was in sorgfaeltigen Tests (2023-2026, ausserhalb der Suchperiode) funktioniert hat und was nicht:
- Funktioniert: Trendfolge auf Tagesbasis (Kurs ueber gleitenden Durchschnitten, staerkstes Momentum), nur wenn BTC
  ueber seinem 100-Tage-Schnitt liegt; Positionsgroesse in unruhigen Phasen verkleinern; Stablecoin-Zufluesse als
  Rueckenwind fuer BTC.
- Funktioniert nicht: Scalping, haeufiges Hin und Her, Shorts gegen gehypte Altcoins (Short-Squeezes), Hebel auf
  Altcoins in Bärenphasen, Wetten auf Tageszeit- oder Wochentagsmuster.
- Messlatte: einfach BTC halten. Eine Idee lohnt sich nur, wenn sie das voraussichtlich schlaegt.

Schreibe in "marktlage" knapp deine Einschaetzung und in "notiz_fuer_morgen", worauf du morgen achten willst."""

WEB_HINT = """

Du hast eine Websuche. Nutze sie vor deiner Entscheidung kurz (hoechstens 4 Suchen) fuer:
1) wichtige Krypto-News der letzten 24 Stunden (Hacks, Regulierung, ETF-Fluesse, grosse Liquidationen),
2) anstehende Makro-Termine der naechsten 3 Tage (US-Arbeitsmarkt, CPI/PCE, Fed-Entscheid) und ihre Erwartung.
Termine mit hohem Risiko kurz vor dem naechsten Tag sind ein Grund fuer kleinere Positionen oder weitere Stops.
Nenne in "marktlage" die wichtigsten Funde mit Datum. Vertraue Kursen aus der Suche nicht mehr als dem Marktbericht."""

SCHEMA = {
    "type": "object",
    "properties": {
        "marktlage": {"type": "string"},
        "positions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "coin": {"type": "string", "enum": ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "LINK", "AVAX"]},
                "side": {"type": "string", "enum": ["long", "short"]},
                "win_probability": {"type": "number"},
                "reward_risk": {"type": "number"},
                "stop_loss_pct": {"type": "number"},
                "take_profit_pct": {"type": "number"},
                "thesis": {"type": "string"}},
            "required": ["coin", "side", "win_probability", "reward_risk", "stop_loss_pct", "take_profit_pct", "thesis"],
            "additionalProperties": False}},
        "notiz_fuer_morgen": {"type": "string"}},
    "required": ["marktlage", "positions", "notiz_fuer_morgen"],
    "additionalProperties": False}


def month_spent(cost_log):
    m = datetime.datetime.now(datetime.UTC).strftime("%Y-%m")
    if not os.path.exists(cost_log):
        return 0.0
    return sum(json.loads(x)["usd"] for x in open(cost_log, encoding="utf-8") if json.loads(x)["month"] == m)


def build_user_message(market, feats, portfolio, memory):
    return ("MARKTBERICHT\n" + json.dumps(market, ensure_ascii=False) +
            "\n\nCOINS (Tageskerzen, abgeschlossen)\n" + json.dumps(feats, ensure_ascii=False) +
            "\n\nDEIN PORTFOLIO\n" + json.dumps(portfolio, ensure_ascii=False) +
            "\n\nDEINE LETZTEN ENTSCHEIDUNGEN UND IHR ERGEBNIS\n" + json.dumps(memory, ensure_ascii=False) +
            "\n\nTriff deine Entscheidung fuer den naechsten Tag.")


def find_claude_cli(cfg=None):
    """Claude-Code-Kommandozeile: settings "claude_cli", dann PATH, dann uebliche Installationsorte
    (Linux ~/.local/bin, ~/.claude/local; Windows VS-Code-Erweiterung). Cron hat einen kurzen PATH."""
    import glob, shutil
    if cfg and cfg.get("claude_cli") and os.path.exists(os.path.expanduser(cfg["claude_cli"])):
        return os.path.expanduser(cfg["claude_cli"])
    for c in (shutil.which("claude"), os.path.expanduser("~/.local/bin/claude"),
              os.path.expanduser("~/.claude/local/claude")):
        if c and os.path.exists(c):
            return c
    found = sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe")))
    return found[-1] if found else None


def decide_abo(cfg, user_message, workdir):
    """Entscheidung ueber das Claude-Abo (Claude Code im Kommandozeilen-Modus): keine Zusatzkosten.
    Keine Werkzeuge (die KI kann nichts auf dem PC ausfuehren), keine gespeicherte Sitzung."""
    import subprocess
    cli = find_claude_cli(cfg)
    if not cli:
        return None, 0.0, "Claude Code nicht gefunden - keine Entscheidung."
    tools = cfg.get("abo_tools", "")                 # z.B. "WebSearch" - nur lesend, nichts lokal ausfuehrbar
    system = SYSTEM + (WEB_HINT if "WebSearch" in tools else "")
    sp = os.path.join(workdir, "system_prompt.txt")
    open(sp, "w", encoding="utf-8").write(system)
    cmd = [cli, "-p", "--output-format", "json", "--tools", tools, "--no-session-persistence",
           "--system-prompt-file", sp, "--json-schema", json.dumps(SCHEMA), "--effort", cfg["effort"],
           "--strict-mcp-config"]                     # keine verknuepften Dienste (Mail, Kalender, Drive ...)
    if tools:
        cmd += ["--allowedTools", tools]           # ohne Rueckfrage erlaubt (nur diese Werkzeuge existieren)
    if cfg.get("abo_model"):
        cmd += ["--model", cfg["abo_model"]]
    r = subprocess.run(cmd, input=user_message, capture_output=True, text=True, encoding="utf-8",
                       cwd=workdir, timeout=900)
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, 0.0, f"Claude Code ohne lesbare Antwort (Code {r.returncode}): {r.stderr[:200]}"
    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        return None, 0.0, f"Claude Code meldet Fehler: {str(out.get('result'))[:200]}"
    return out["structured_output"], 0.0, f"ueber Abo (Listenpreis-Gegenwert {out.get('total_cost_usd', 0):.3f} $)"


def decide(cfg, user_message, cost_log, budget_left):
    """Ruft Claude auf. Gibt (Entscheidung oder None, Kosten in $, Hinweistext) zurueck."""
    est = (len(user_message) + len(SYSTEM)) / 3.5 / 1e6 * PRICES.get(cfg["model"], (5, 25))[0] + 8000 / 1e6 * \
        PRICES.get(cfg["model"], (5, 25))[1]
    if est > budget_left:
        return None, 0.0, f"Monatsbudget erreicht (Rest {budget_left:.2f} $) - keine KI-Anfrage, Positionen bleiben."
    client = anthropic.Anthropic()            # liest ANTHROPIC_API_KEY bzw. hinterlegte Zugangsdaten
    resp = client.beta.messages.create(
        model=cfg["model"], max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        output_config={"effort": cfg["effort"], "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    pin, pout = PRICES.get(resp.model, PRICES.get(cfg["model"], (5, 25)))
    u = resp.usage
    usd = (u.input_tokens * pin + u.output_tokens * pout + (u.cache_read_input_tokens or 0) * pin * 0.1
           + (u.cache_creation_input_tokens or 0) * pin * 1.25) / 1e6
    with open(cost_log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"month": datetime.datetime.now(datetime.UTC).strftime("%Y-%m"), "model": resp.model,
                            "in": u.input_tokens, "out": u.output_tokens, "usd": round(usd, 5)}) + "\n")
    if resp.stop_reason == "refusal":
        return None, usd, "KI hat die Anfrage abgelehnt - heute keine Aenderung."
    if resp.stop_reason == "max_tokens":
        return None, usd, "Antwort abgeschnitten - heute keine Aenderung."
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return json.loads(text), usd, ""
    except json.JSONDecodeError:
        return None, usd, "Antwort nicht lesbar - heute keine Aenderung."
