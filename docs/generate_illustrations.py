# Erzeugt die README-Grafiken in Hell- und Dunkel-Variante (docs/*_light.png, docs/*_dark.png).
# Aufruf: python docs/generate_illustrations.py   (braucht matplotlib, ccxt, pandas)
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd
import ccxt

OUT = os.path.dirname(os.path.abspath(__file__))
THEMES = {   # Referenzpalette (dataviz): Slots 1-3 sind in beiden Modi fuer alle Paarungen validiert
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9",
                  axis="#c3c2b7", s1="#2a78d6", s2="#eb6834", s3="#1baf7a", good="#0ca30c", crit="#d03b3b",
                  box="#f0efec", neg="#e34948"),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a",
                 axis="#383835", s1="#3987e5", s2="#d95926", s3="#199e70", good="#0ca30c", crit="#d03b3b",
                 box="#262624", neg="#e66767"),
}
plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 11})


def style(ax, t):
    ax.set_facecolor(t["surface"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(t["axis"])
    ax.tick_params(colors=t["muted"], length=0)
    ax.grid(axis="y", color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name, mode):
    fig.savefig(os.path.join(OUT, f"{name}_{mode}.png"), dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


# 1) Ablauf ------------------------------------------------------------------------------------------
def flow(mode):
    t = THEMES[mode]
    fig, ax = plt.subplots(figsize=(11, 4.6)); fig.patch.set_facecolor(t["surface"])
    ax.set_xlim(0, 11); ax.set_ylim(-0.1, 4.6); ax.axis("off")

    def box(x, y, w, h, title, lines, accent=None):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    facecolor=t["box"], edgecolor=accent or t["axis"], linewidth=2 if accent else 1))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="top", color=t["ink"], fontsize=12, fontweight="bold")
        for i, l in enumerate(lines):
            ax.text(x + w / 2, y + h - 0.78 - i * 0.34, l, ha="center", va="top", color=t["ink2"], fontsize=9.5)

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=t["muted"], lw=1.6, mutation_scale=14))

    box(0.1, 1.9, 2.4, 2.5, "Marktbericht", ["Top-10-Coins (Tageskerzen)", "Trend, Momentum, RSI", "Funding, Stablecoins",
                                             "Binance-Ankündigungen"])
    box(0.1, 0.15, 2.4, 1.45, "Websuche", ["News der letzten 24 h", "Makro-Termine (Fed, Jobs)"])
    box(3.3, 1.0, 2.5, 2.6, "Claude", ["Opus 5.5 über das Abo", "entscheidet frei:", "long, short oder nichts",
                                      "+ Wahrscheinlichkeit", "+ Stop und Ziel"], accent=t["s1"])
    box(6.6, 1.0, 2.0, 2.6, "Kelly-Größe", ["¼ Kelly", "max. 35 % je Coin", "max. 2× gesamt", "−5 % Tagesstopp"],
        accent=t["s2"])
    box(9.1, 1.0, 1.8, 2.6, "Konto", ["simuliert", "100 USDT", "Stop / Ziel", "täglich", "abgerechnet"], accent=t["s3"])
    arrow(2.5, 3.1, 3.3, 2.6); arrow(2.5, 0.9, 3.3, 1.6); arrow(5.8, 2.3, 6.6, 2.3); arrow(8.6, 2.3, 9.1, 2.3)
    ax.annotate("", xy=(4.55, 0.98), xytext=(10.0, 0.98), arrowprops=dict(arrowstyle="-|>", color=t["muted"], lw=1.4,
                connectionstyle="arc3,rad=-0.12", linestyle=(0, (4, 3)), mutation_scale=14))
    ax.text(7.3, 0.12, "Gedächtnis: letzte 7 Entscheidungen + Ergebnis", ha="center", color=t["muted"], fontsize=9.5)
    save(fig, "flow", mode)


# 2) Erste echte Entscheidung ------------------------------------------------------------------------
def decision(mode, btc):
    t = THEMES[mode]
    entry, sl, tp = 83623.6, 83623.6 * 0.94, 83623.6 * 1.12      # Entscheidung fuer den 30.09.2026
    s = btc.iloc[-120:]; sma50 = btc.rolling(50).mean().iloc[-120:]
    fig, ax = plt.subplots(figsize=(11, 4.8)); fig.patch.set_facecolor(t["surface"]); style(ax, t)
    ax.plot(s.index, s.values, color=t["s1"], lw=2, label="BTC (Tagesschluss)")
    ax.plot(sma50.index, sma50.values, color=t["s2"], lw=2, label="50-Tage-Schnitt")
    for y, c, lab in ((tp, t["good"], "▲ Ziel +12 %"), (entry, t["ink2"], "● Einstieg"), (sl, t["crit"], "▼ Stop −6 %")):
        ax.axhline(y, color=c, lw=1.2, ls=(0, (5, 4)))
        ax.text(s.index[48], y, f" {lab}  {y:,.0f} $".replace(",", "."), color=t["ink"], fontsize=9.5, va="bottom")
    ax.text(s.index[-1], s.iloc[-1], "  BTC", color=t["ink"], fontsize=10, va="center", fontweight="bold")
    ax.text(sma50.index[-1], sma50.iloc[-1], "  SMA50", color=t["ink2"], fontsize=9.5, va="center")
    ax.set_xlim(s.index[0], s.index[-1] + pd.Timedelta(days=12))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax.legend(loc="lower right", frameon=False, labelcolor=t["ink2"], fontsize=9.5)
    ax.set_title("Erste KI-Entscheidung (30.09.2026): BTC long, 35 % des Kontos", loc="left", color=t["ink"],
                 fontsize=12.5, fontweight="bold", pad=12)
    save(fig, "decision", mode)


# 3) Kelly-Groesse -----------------------------------------------------------------------------------
def kelly(mode):
    t = THEMES[mode]
    p = [x / 1000 for x in range(330, 501, 2)]; rr = 2.0
    fig, ax = plt.subplots(figsize=(11, 4.6)); fig.patch.set_facecolor(t["surface"]); style(ax, t)
    for stop, c in ((0.04, t["s1"]), (0.06, t["s2"]), (0.10, t["s3"])):
        w = [min(0.35, max(0.0, 0.25 * (q - (1 - q) / rr) / stop)) * 100 for q in p]
        ax.plot([q * 100 for q in p], w, color=c, lw=2, label=f"Stop {stop * 100:.0f} %")
        kink = (0.35 * stop / 0.25 + 1 / rr) / (1 + 1 / rr) * 100     # p, ab der die Obergrenze greift
        ax.text(kink, 36.4, f"Stop {stop * 100:.0f} %", color=t["ink"], fontsize=9.5, ha="center")
    ax.axhline(35, color=t["muted"], lw=1.2, ls=(0, (5, 4)))
    ax.text(50, 32.6, "Obergrenze 35 % je Coin", color=t["ink2"], fontsize=9.5, ha="right")
    ax.axvline(33.3, color=t["axis"], lw=1)
    ax.text(33.5, 24, "ab 33,3 %\npositiver\nErwartungswert", color=t["muted"], fontsize=9)
    ax.set_xlabel("Gewinnwahrscheinlichkeit, die die KI angibt (%)", color=t["ink2"])
    ax.set_ylabel("Positionsgröße (% des Kontos)", color=t["ink2"])
    ax.set_ylim(0, 42); ax.set_xlim(33, 50)
    ax.legend(loc="lower right", frameon=False, labelcolor=t["ink2"], fontsize=9.5)
    ax.set_title("Wie viel gesetzt wird: ¼ Kelly bei Chance/Risiko 2 : 1", loc="left", color=t["ink"],
                 fontsize=12.5, fontweight="bold", pad=12)
    save(fig, "kelly", mode)


# 4) Alpha Arena -------------------------------------------------------------------------------------
def arena(mode):
    t = THEMES[mode]
    res = [("Qwen 3 Max", 22.3), ("DeepSeek V3.1", 4.9), ("Claude Sonnet 4.5", -42.0), ("Gemini 2.5 Pro", -45.6),
           ("Grok 4", -57.9), ("GPT-5", -58.7)]
    fig, ax = plt.subplots(figsize=(11, 4.2)); fig.patch.set_facecolor(t["surface"]); style(ax, t)
    ax.grid(axis="y", visible=False); ax.grid(axis="x", color=t["grid"], linewidth=0.8)
    names = [r[0] for r in res][::-1]; vals = [r[1] for r in res][::-1]
    ax.barh(names, vals, color=[t["s1"] if v > 0 else t["neg"] for v in vals], height=0.55,
            edgecolor=t["surface"], linewidth=2)
    for i, v in enumerate(vals):
        ax.text(v + (1.5 if v > 0 else -1.5), i, f"{v:+.1f} %".replace(".", ","), va="center",
                ha="left" if v > 0 else "right", color=t["ink"], fontsize=10)
    ax.axvline(0, color=t["axis"], lw=1.2)
    ax.set_xlim(-75, 35); ax.tick_params(axis="y", colors=t["ink2"])
    ax.set_xlabel("Ergebnis nach 2 Wochen mit je 10.000 $ echtem Geld", color=t["ink2"])
    ax.set_title("Alpha Arena (Okt./Nov. 2025): KIs handeln Krypto frei mit echtem Geld", loc="left",
                 color=t["ink"], fontsize=12.5, fontweight="bold", pad=12)
    save(fig, "arena", mode)


if __name__ == "__main__":
    rows = ccxt.binance().fetch_ohlcv("BTC/USDT", "1d", limit=400)
    btc = pd.Series([r[4] for r in rows], index=pd.to_datetime([r[0] for r in rows], unit="ms"))
    btc = btc.loc[:"2026-09-30"]
    for m in THEMES:
        flow(m); decision(m, btc); kelly(m); arena(m)
    print("fertig:", sorted(f for f in os.listdir(OUT) if f.endswith(".png")))
