import numpy as np, pandas as pd
src = open("multi.py", encoding="utf-8").read()
exec(src[: src.index("base = [")])
def kelly_best(rs):
    best = max((0.05, 0.1, 0.15, 0.2, 0.25, 0.3), key=lambda f: np.sum(np.log1p(f*np.asarray(rs))) if (1+f*np.asarray(rs)).min() > 0 else -1e9)
    return best
key = (30, 75, 40, "ohne")
buckets = [("A 21-23", isA & (tent < CUT)), ("A 24-26", isA & (tent >= CUT)), ("B 21-23", ~isA & (tent < CUT)), ("B 24-26", ~isA & (tent >= CUT)), ("alle", np.ones(len(tent), bool))]
for cfg in [(10, 0.075), (20, 0.075), (20, 0.05), (15, 0.075), (15, 0.10), (20, 0.10)]:
    g = cfg[1]*cfg[0] - 0.0008*cfg[0]
    print(f"\n=== x{cfg[0]} TP {cfg[1]*100:.1f}% (+{g*100:.0f}%/Treffer, Schwelle {100/(1+g):.1f}%)")
    fA = kelly_best(seq([(key, cfg)], isA & (tent < CUT)).r.values)     # Anteil nur auf A 21-23 gewaehlt
    for lab, sel in buckets:
        T = seq([(key, cfg)], sel); h, ext, net = tresor(T.r.values)
        side = ""
        print(f"   {lab:8s} {len(T):3d} Tr  Treffer {T.w.mean()*100:5.1f}%  je Trade {T.r.mean():+.3f} | Serie+Tresor: {h}x Ziel, ein {ext:5d}, netto {net:+7,} | Anteil {int(fA*100)}% (gewählt A 21-23): 30->{kelly(T.r.values, fA):,}")
