import numpy as np, pandas as pd
src = open("portfolio.py", encoding="utf-8").read()
exec(src[: src.index("T0 = int(")].replace('KEYS = {', 'KEYS0 = {'))
T0 = int(pd.Timestamp("2021-03-01").value//10**6); TE = int(tent.max())
for name, key in {"Ausbruch stark 30/75/40": (30, 75, 40, "ohne"), "Ausbruch stark 30/75/20": (30, 75, 20, "ohne")}.items():
    T = trades(key, (10, 0.075))
    T["jahr"] = pd.to_datetime(T.te, unit="ms").dt.year
    print(f"\n=== {name}, x10, TP +7,5 %: {len(T)} Trades (je Coin einer gleichzeitig), Treffer {(T.r > 0).mean()*100:.1f} %, je Trade {T.r.mean():+.3f}")
    print("   je Jahr:", " ".join(f"{j}: {len(g)} Tr/{(g.r > 0).mean()*100:.0f}%" for j, g in T.groupby("jahr")))
    for kmax in (1, 2, 3, 5):
        line = []
        for f in (0.05, 0.1, 0.15, 0.2, 0.3, 1.0):
            a, da, _ = account(T, f, kmax, T0, CUT); b, db, _ = account(T, f, kmax, CUT, TE)
            line.append(f"f={f:.2f}: {a:,.0f}/{b:,.0f} (DD {da*100:.0f}/{db*100:.0f}%)")
        print(f"   K={kmax}: " + " | ".join(line))
    # all-in Serien, Ziel-Abzug: Start 30, bei Ziel auszahlen, bei Liquidation neu 30
    for goal in (600, 1100, 5000):
        dep = 30; paid = 0; eq = 30; hits = 0; busy = -1
        for te, xt, r in zip(T.te, T.xt, T.r):
            if te < busy: continue
            busy = xt; eq *= 1 + r
            if eq >= goal: paid += eq; hits += 1; eq = 30; dep += 30
            elif eq <= 0: eq = 30; dep += 30
        print(f"   all-in bis {goal}: {hits}x erreicht, eingezahlt {dep:,}, ausgezahlt {paid:,.0f}")
