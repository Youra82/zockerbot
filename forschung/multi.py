import numpy as np, pandas as pd
src = open("improve.py", encoding="utf-8").read()
exec(src[: src.index("rows = []")].replace("cache=True", "cache=False"))
R = pd.read_csv("improve_result.csv")
order = np.argsort(tent, kind="stable"); rank = np.empty_like(order); rank[order] = np.arange(len(order))
grpA_mask = isA
def events(key, cfg, rid):
    Li, Si = M[key]; both = np.intersect1d(Li, Si); Li = np.setdiff1d(Li, both); Si = np.setdiff1d(Si, both)
    return [(i, 1, rid) for i in Li] + [(i, -1, rid) for i in Si]
def seq(rules, sel):
    ev = []
    for rid, (key, cfg) in enumerate(rules): ev += events(key, cfg, rid)
    ev = [e for e in ev if sel[e[0]]]
    ev.sort(key=lambda e: (rank[e[0]], e[2]))
    busy = -1; out = []
    for i, s, rid in ev:
        if tent[i] < busy: continue
        key, cfg = rules[rid]; j = CONF.index(cfg); w = W[j, 0 if s > 0 else 1, i]
        if w < 0: continue
        busy = X[j, 0 if s > 0 else 1, i]
        g = cfg[1]*cfg[0] - 0.0008*cfg[0]
        out.append((tent[i], rid, w, g if w else -1.0))
    return pd.DataFrame(out, columns=["t", "rid", "w", "r"])
def tresor(rs, ziel=1000, keep=0.2, neu=30.0, e=0.97):
    spiel, tre, ext, hits = neu, 0.0, neu, 0
    for r in rs:
        spiel += e*spiel*r
        if spiel >= ziel: b = max(neu, keep*spiel); tre += spiel - b; spiel = b; hits += 1
        elif spiel < neu:
            need = neu - spiel
            if tre >= need: tre -= need
            else: ext += need - tre; tre = 0
            spiel = neu
    return hits, round(ext), round(tre + spiel - ext)
def kelly(rs, f):
    k = 30.0
    for r in rs: k *= 1 + f*r
    return round(k)
yrsA_tr = (CUT - tent.min())/864e5/365; yrs_te = (tent.max() - CUT)/864e5/365
def report(name, rules):
    out = []
    for lab, sel, yrs in [("A 21-23 (Auswahl)", isA & (tent < CUT), yrsA_tr), ("A 24-26", isA & (tent >= CUT), yrs_te),
                          ("B 21-23", ~isA & (tent < CUT), yrsA_tr), ("B 24-26", ~isA & (tent >= CUT), yrs_te), ("alle 21-26", np.ones(len(tent), bool), yrsA_tr + yrs_te)]:
        T = seq(rules, sel)
        if T.empty: continue
        h, ext, net = tresor(T.r.values)
        out.append(f"   {lab:18s} {len(T)/yrs:5.0f} Tr/J  Treffer {T.w.mean()*100:5.1f}%  je Trade {T.r.mean():+.3f} | Tresor-Serie: {h}x Ziel, ein {ext}, netto {net:+,} | 20%: 30->{kelly(T.r.values, 0.2):,}")
    print(f"\n=== {name}"); print("\n".join(out))
base = [((30, 75, 40, "ohne"), (10, 0.075))]
report("Basis: Ausbruch stark allein", base)
# Kandidaten NUR nach Gruppe A 2021-23: positive Kante, genug Trades, Wachstum A_tr
C = R[(R.edge_A_tr > 0.05) & (R.n_A_tr >= 100)].copy()
C = C.sort_values("g_A_tr", ascending=False)
picked, keys = [], set()
for r in C.itertuples():
    key = (int(r.rsi15), int(r.tagesrsi), int(r.donchian), r.filter); cfg = (int(r.hebel), float(r.tp))
    fam = (key[0], key[1], r.filter)            # nicht zweimal fast dieselbe Regel
    if fam in keys or key == base[0][0]: continue
    picked.append((key, cfg)); keys.add(fam)
    if len(picked) == 6: break
print("\nNach A 2021-23 gewaehlte Zusatzregeln:")
for k, c in picked: print("  ", k, "x%d TP%.1f%%" % (c[0], c[1]*100))
for n in (1, 2, 3, 6):
    report(f"Basis + {n} Zusatzregel(n)", base + picked[:n])
