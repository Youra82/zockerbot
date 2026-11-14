import numpy as np, pandas as pd
src = open("portfolio.py", encoding="utf-8").read()
exec(src[: src.index("T0 = int(")])
T0 = int(pd.Timestamp("2021-03-01").value//10**6); TE = int(tent.max())
rows = []
for name, (key, cfg) in KEYS.items():
    T = trades(key, cfg)
    for kmax in (1, 2, 3, 5):
        for f in (0.01, 0.02, 0.03, 0.05, 0.075, 0.1):
            a, da, _ = account(T, f, kmax, T0, CUT); b, db, _ = account(T, f, kmax, CUT, TE)
            rows.append((name, kmax, f, round(a), round(da*100), round(b), round(db*100)))
d = pd.DataFrame(rows, columns=["regel", "K", "f", "21-23_aus30", "DD21-23", "24-26_aus30", "DD24-26"])
d["beide>30"] = (d["21-23_aus30"] > 30) & (d["24-26_aus30"] > 30)
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 200)
print(d[d["beide>30"]].sort_values("24-26_aus30", ascending=False).to_string(index=False))
print("\nbeste je Regel nach 2021-23 (Auswahl) -> 2024-26:")
for n, g in d.groupby("regel"):
    r = g.loc[g["21-23_aus30"].idxmax()]; print(f"  {n}: K={r.K} f={r.f} | 21-23 30->{r['21-23_aus30']} (DD {r['DD21-23']}%) | 24-26 30->{r['24-26_aus30']} (DD {r['DD24-26']}%)")
