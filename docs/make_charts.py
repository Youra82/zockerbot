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
E, NEU, ZIEL, KEEP, POLSTER, DYN = 0.97, 30.0, 400.0, 0.5, 150.0, 0.15

# Modus serie, B + Polster: Spielgeld, Tresor, eigene Einzahlungen nach jedem Trade
spiel, tresor, ein, rows, ziele = NEU, 0.0, NEU, [], []
rows.append((T.einstieg.iloc[0], spiel, tresor, ein))
for t, w in zip(T.ausstieg, T.treffer):
    g = E * spiel * (G if w else -1.0)
    if w and tresor < POLSTER:
        tresor += 0.5 * g; g *= 0.5
    spiel += g
    neu = max(NEU, DYN * (spiel + tresor))            # dynamischer Neustart wie live
    if spiel >= ZIEL:
        b = max(neu, KEEP * spiel); tresor += spiel - b; spiel = b; ziele.append(t)
    elif spiel < neu - 0.01:
        need = neu - spiel
        if tresor >= need:
            tresor -= need
        else:
            ein += need - tresor; tresor = 0.0
        spiel = neu
    rows.append((t, spiel, tresor, ein))
S = pd.DataFrame(rows, columns=["d", "spiel", "tresor", "ein"])
# Modus anteil 20 %
k, ant = 30.0, []
for t, w in zip(T.ausstieg, T.treffer):
    k *= 1 + 0.20 * (G if w else -1.0); ant.append((t, k))
ant = pd.DataFrame(ant, columns=["d", "konto"])
yr = T.assign(j=T.einstieg.dt.year).groupby("j").agg(n=("treffer", "size"), wr=("treffer", "mean"))

themes = {"light": dict(bg="#ffffff", fg="#1f2328", mu="#656d76", grid="#e6e8eb", a="#2f6feb", b="#c9772b", t="#b07a1a", tf="#f3e3c3", ok="#1a7f37", bad="#cf222e", ein="#8a909b"),
          "dark": dict(bg="#0d1117", fg="#e6edf3", mu="#8b949e", grid="#30363d", a="#58a6ff", b="#e3a35b", t="#e0ad4f", tf="#3a2e17", ok="#3fb950", bad="#f85149", ein="#7d8593")}


def frame(t, h):
    plt.rcParams.update({"font.size": 11, "text.color": t["fg"], "axes.labelcolor": t["mu"], "xtick.color": t["mu"], "ytick.color": t["mu"]})
    fig, ax = plt.subplots(figsize=(10, h), dpi=130)
    fig.patch.set_facecolor(t["bg"]); ax.set_facecolor(t["bg"])
    for s in ax.spines.values():
        s.set_color(t["grid"])
    return fig, ax


for name, t in themes.items():
    fig, ax = frame(t, 4.4)
    ax.fill_between(S["d"], 10, S["tresor"].clip(lower=10), step="post", color=t["tf"], label="Tresor (wird nie eingesetzt)")
    ax.step(S["d"], S["tresor"], where="post", color=t["t"], lw=1.4)
    ax.step(S["d"], S["spiel"], where="post", color=t["a"], lw=1.2, label="Spielgeld")
    ax.step(S["d"], S["ein"], where="post", color=t["ein"], lw=1.8, ls="--", label="eigene Einzahlungen gesamt")
    for d in ziele:
        v = S.loc[S["d"] == d, "tresor"].iloc[-1]
        ax.scatter([d], [v], color=t["t"], s=7, zorder=3)
    ax.set_yscale("log"); ax.set_ylabel("USDT (log)"); ax.grid(color=t["grid"], lw=0.6); ax.set_ylim(10, max(S["tresor"].max(), S["spiel"].max()) * 1.6)
    tz = f"{S['tresor'].iloc[-1]:,.0f}".replace(",", ".")
    ax.set_title(f"B + Polster, Neustart 15 %: {len(ziele)}× Ziel, Tresor {tz} USDT, eingezahlt {S['ein'].iloc[-1]:.0f} USDT",
                 color=t["fg"], loc="left", fontsize=11.5)
    ax.legend(frameon=False, labelcolor=t["fg"], loc="upper left"); fig.tight_layout()
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
print("ok", len(ziele), round(S["tresor"].iloc[-1]), round(S["ein"].iloc[-1]), round(ant["konto"].iloc[-1]))
