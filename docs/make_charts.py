"""Erzeugt die README-Grafiken (hell/dunkel) aus forschung/winner_trades.csv."""
import heapq, os, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
T = pd.read_csv(os.path.join(HERE, "..", "forschung", "winner_trades.csv")).sort_values("te")
T["datum"] = pd.to_datetime(T.te, unit="ms")

def curve(f, start=30.0):
    k = start; open_ = []; pts = [(T.datum.iloc[0], k)]
    for te, xt, r in zip(T.te, T.xt, T.r):
        while open_ and open_[0][0] <= te:
            x, m, rr = heapq.heappop(open_); k += m*rr; pts.append((pd.to_datetime(x, unit="ms"), k))
        used = sum(m for _, m, _ in open_); m = min(f*k, k-used)
        if m > 0: heapq.heappush(open_, (xt, m, r))
    while open_:
        x, m, rr = heapq.heappop(open_); k += m*rr; pts.append((pd.to_datetime(x, unit="ms"), k))
    return pd.DataFrame(pts, columns=["d", "konto"]).sort_values("d")

c15, c25 = curve(0.15), curve(0.25)
yr = T.assign(j=T.datum.dt.year).groupby("j").agg(n=("win", "size"), wr=("win", "mean"))
themes = {"light": dict(bg="#ffffff", fg="#1f2328", mu="#656d76", grid="#e6e8eb", a="#2f6feb", b="#c9772b", ok="#1a7f37", bad="#cf222e"),
          "dark": dict(bg="#0d1117", fg="#e6edf3", mu="#8b949e", grid="#30363d", a="#58a6ff", b="#e3a35b", ok="#3fb950", bad="#f85149")}
for name, t in themes.items():
    plt.rcParams.update({"font.size": 11, "text.color": t["fg"], "axes.labelcolor": t["mu"], "xtick.color": t["mu"], "ytick.color": t["mu"]})
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=130); fig.patch.set_facecolor(t["bg"]); ax.set_facecolor(t["bg"])
    ax.plot(c15["d"], c15["konto"], color=t["a"], lw=2, label="15 % Margin je Trade (Standard)")
    ax.plot(c25["d"], c25["konto"], color=t["b"], lw=1.6, ls="--", label="25 % Margin je Trade")
    ax.axhline(1100, color=t["ok"], lw=1); ax.text(c15["d"].iloc[0], 1180, "Ziel 1.100 USDT (≈ 1.000 €)", color=t["ok"], fontsize=10)
    ax.set_yscale("log"); ax.set_ylabel("Konto in USDT (log)"); ax.grid(color=t["grid"], lw=0.6)
    for s in ax.spines.values(): s.set_color(t["grid"])
    ax.set_title("Kontoverlauf ab 30 USDT, 11 Coins, ein Konto (Backtest 2021–2026)", color=t["fg"], loc="left", fontsize=12)
    ax.legend(frameon=False, labelcolor=t["fg"]); fig.tight_layout(); fig.savefig(os.path.join(HERE, f"equity_{name}.png"), facecolor=t["bg"]); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 3.6), dpi=130); fig.patch.set_facecolor(t["bg"]); ax.set_facecolor(t["bg"])
    cols = [t["a"] if w >= 0.504 else t["bad"] for w in yr.wr]
    ax.bar(yr.index.astype(str), yr.wr*100, color=cols, width=0.6)
    ax.axhline(50.4, color=t["mu"], lw=1, ls="--"); ax.text(-0.45, 52, "Gewinnschwelle 50,4 %", color=t["mu"], fontsize=10)
    for i, (w, n) in enumerate(zip(yr.wr, yr.n)): ax.text(i, w*100+1.5, f"{w*100:.0f} %  ({n})", ha="center", color=t["fg"], fontsize=9)
    ax.set_ylim(0, 85); ax.set_ylabel("Trefferquote in %"); ax.grid(axis="y", color=t["grid"], lw=0.6)
    for s in ax.spines.values(): s.set_color(t["grid"])
    ax.set_title("Trefferquote je Jahr, in Klammern Anzahl Trades (TP +5 % vor Liquidation, x20)", color=t["fg"], loc="left", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, f"jahre_{name}.png"), facecolor=t["bg"]); plt.close(fig)
print("ok", round(c15["konto"].iloc[-1], 1), round(c15["konto"].max(), 1), round(c25["konto"].iloc[-1], 1))
