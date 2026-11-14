"""Erzeugt die README-Grafiken (hell/dunkel) aus forschung/ausbruch_stark_trades.csv
(Trade-Folge des Bots: 42 Coins, eine Position gleichzeitig, x10, TP +7,5 %)."""
import os
import matplotlib
import pandas as pd
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
T = pd.read_csv(os.path.join(HERE, "..", "forschung", "ausbruch_stark_trades.csv"), parse_dates=["einstieg", "ausstieg"])
G = 0.075 * 10 - 0.008
SCHWELLE = 100 / (1 + G)
ZIEL = 1100

# Modus serie: all-in, bei Ziel auszahlen, nach Liquidation 30 neu
serie, k, auszahl = [], 30.0, []
for t, w in zip(T.ausstieg, T.treffer):
    k *= (1 + G) if w else 0.0
    serie.append((t, k if k > 0 else 0.5))
    if k >= ZIEL:
        auszahl.append((t, k)); k = 30.0; serie.append((t, k))
    elif k <= 0:
        k = 30.0; serie.append((t, k))
serie = pd.DataFrame(serie, columns=["d", "konto"])
# Modus anteil 20 %
k, ant = 30.0, []
for t, w in zip(T.ausstieg, T.treffer):
    k *= 1 + 0.20 * (G if w else -1.0); ant.append((t, k))
ant = pd.DataFrame(ant, columns=["d", "konto"])
yr = T.assign(j=T.einstieg.dt.year).groupby("j").agg(n=("treffer", "size"), wr=("treffer", "mean"))

themes = {"light": dict(bg="#ffffff", fg="#1f2328", mu="#656d76", grid="#e6e8eb", a="#2f6feb", b="#c9772b", ok="#1a7f37", bad="#cf222e"),
          "dark": dict(bg="#0d1117", fg="#e6edf3", mu="#8b949e", grid="#30363d", a="#58a6ff", b="#e3a35b", ok="#3fb950", bad="#f85149")}


def frame(t, h):
    plt.rcParams.update({"font.size": 11, "text.color": t["fg"], "axes.labelcolor": t["mu"], "xtick.color": t["mu"], "ytick.color": t["mu"]})
    fig, ax = plt.subplots(figsize=(10, h), dpi=130)
    fig.patch.set_facecolor(t["bg"]); ax.set_facecolor(t["bg"])
    for s in ax.spines.values():
        s.set_color(t["grid"])
    return fig, ax


for name, t in themes.items():
    fig, ax = frame(t, 4.2)
    ax.step(serie["d"], serie["konto"], where="post", color=t["a"], lw=1.6, label="Modus serie: all-in, Auszahlung bei 1.100 USDT")
    for d, v in auszahl:
        ax.scatter([d], [v], color=t["ok"], s=40, zorder=3)
    ax.axhline(ZIEL, color=t["ok"], lw=1, ls="--")
    ax.text(serie["d"].iloc[-1], ZIEL * 0.6, f"Ziel {ZIEL:,} USDT: {len(auszahl)}× erreicht (grüne Punkte)".replace(",", "."),
            color=t["ok"], fontsize=10, ha="right")
    ax.set_yscale("log"); ax.set_ylim(0.4, ZIEL * 2.2); ax.set_ylabel("Konto in USDT (log, Liquidation = unten)")
    ax.grid(color=t["grid"], lw=0.6)
    ax.set_title("Serienmodus: all-in ab 30 USDT, Auszahlung bei 1.100, nach Liquidation neu 30 (Backtest 2021–2026)",
                 color=t["fg"], loc="left", fontsize=11.5)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, f"serie_{name}.png"), facecolor=t["bg"]); plt.close(fig)

    fig, ax = frame(t, 3.8)
    ax.plot(ant["d"], ant["konto"], color=t["b"], lw=2, label="Modus anteil: 20 % Margin je Trade")
    ax.set_yscale("log"); ax.set_ylabel("Konto in USDT (log)"); ax.grid(color=t["grid"], lw=0.6)
    ax.set_title("Anteilsmodus ab 30 USDT, ohne Nachzahlen (Backtest 2021–2026)", color=t["fg"], loc="left", fontsize=12)
    ax.legend(frameon=False, labelcolor=t["fg"], loc="upper left"); fig.tight_layout()
    fig.savefig(os.path.join(HERE, f"anteil_{name}.png"), facecolor=t["bg"]); plt.close(fig)

    fig, ax = frame(t, 3.6)
    cols = [t["a"] if w * 100 >= SCHWELLE else t["bad"] for w in yr.wr]
    ax.bar(yr.index.astype(str), yr.wr * 100, color=cols, width=0.6)
    ax.axhline(SCHWELLE, color=t["mu"], lw=1, ls="--")
    ax.text(-0.45, SCHWELLE + 1.5, f"Gewinnschwelle {SCHWELLE:.1f} %".replace(".", ","), color=t["mu"], fontsize=10)
    for i, (w, n) in enumerate(zip(yr.wr, yr.n)):
        ax.text(i, w * 100 + 1.5, f"{w * 100:.0f} %  ({n})", ha="center", color=t["fg"], fontsize=9)
    ax.set_ylim(0, 85); ax.set_ylabel("Trefferquote in %"); ax.grid(axis="y", color=t["grid"], lw=0.6)
    ax.set_title("Trefferquote je Jahr, in Klammern Anzahl Trades (TP +7,5 % vor Liquidation, x10)", color=t["fg"], loc="left", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, f"jahre_{name}.png"), facecolor=t["bg"]); plt.close(fig)
print("ok", len(auszahl), round(ant["konto"].iloc[-1]))
