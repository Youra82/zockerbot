import numpy as np, pandas as pd
src = open("improve.py", encoding="utf-8").read()
exec(src[: src.index("rows = []")].replace("cache=True", "cache=False"))
ELIG = [(lev, tp) for (lev, tp) in CONF if tp*lev - 0.008*lev >= 0.5]
order = np.argsort(tent, kind="stable")
rank = np.empty_like(order); rank[order] = np.arange(len(order))
def seq(key, cfg):
    Li, Si = M[key]; both = np.intersect1d(Li, Si); Li = np.setdiff1d(Li, both); Si = np.setdiff1d(Si, both)
    idx = np.concatenate([Li, Si]); sd = np.concatenate([np.ones(len(Li), np.int8), -np.ones(len(Si), np.int8)])
    o = np.argsort(rank[idx], kind="stable"); idx, sd = idx[o], sd[o]
    j = CONF.index(cfg); busy = -1; out = []
    for i, s in zip(idx, sd):                      # global nur EIN Trade gleichzeitig (wie all-in)
        if tent[i] < busy: continue
        w = W[j, 0 if s > 0 else 1, i]
        if w < 0: continue
        busy = X[j, 0 if s > 0 else 1, i]
        out.append((tent[i], int(w), coins[coin_id[i]]))
    return out
def streak_stats(ws):
    best = cur = 0; n10 = 0
    for w in ws:
        if w: cur += 1; best = max(best, cur); n10 += (cur == 10)
        else: cur = 0
    return best, n10
rows = []
for key in M:
    for cfg in ELIG:
        s = seq(key, cfg)
        if len(s) < 40: continue
        tr = [w for t, w, c in s if t < CUT]; te = [w for t, w, c in s if t >= CUT]
        if len(tr) < 20 or len(te) < 20: continue
        g = cfg[1]*cfg[0] - 0.008*cfg[0]
        btr, ntr = streak_stats(tr); bte, nte = streak_stats(te)
        rows.append({"rsi15": key[0], "tagesrsi": key[1], "donchian": key[2], "filter": key[3], "hebel": cfg[0], "tp%": cfg[1]*100,
                     "gewinn_je_treffer%": round(g*100), "n_tr": len(tr), "wr_tr": np.mean(tr), "serie_max_tr": btr, "10er_tr": ntr,
                     "n_te": len(te), "wr_te": np.mean(te), "serie_max_te": bte, "10er_te": nte,
                     "edge_tr": np.mean(tr)*(1+g)-1, "edge_te": np.mean(te)*(1+g)-1})
d = pd.DataFrame(rows); d.to_csv("streaks_result.csv", index=False)
pd.set_option("display.width", 250)
print("Varianten:", len(d), "| mit mind. einer 10er-Serie 2021-23:", (d["10er_tr"] > 0).sum(), "| davon auch 2024-26:", ((d["10er_tr"] > 0) & (d["10er_te"] > 0)).sum())
cols = ["rsi15","tagesrsi","donchian","filter","hebel","tp%","gewinn_je_treffer%","n_tr","wr_tr","serie_max_tr","10er_tr","n_te","wr_te","serie_max_te","10er_te","edge_tr","edge_te"]
print("\nAUSWAHL nach 2021-23 (meiste 10er-Serien, dann Trefferquote):")
print(d.sort_values(["10er_tr", "wr_tr"], ascending=False).head(15)[cols].round(3).to_string(index=False))
print("\nZum Vergleich: Varianten mit 10er-Serien in BEIDEN Zeitraeumen:")
print(d[(d["10er_tr"] > 0) & (d["10er_te"] > 0)].sort_values("edge_te", ascending=False).head(15)[cols].round(3).to_string(index=False))
