import json, numpy as np, pandas as pd
src = open("streaks.py", encoding="utf-8").read()
exec(src[: src.rindex("rows = []")])
def seq_full(key, cfg):
    Li, Si = M[key]; both = np.intersect1d(Li, Si); Li = np.setdiff1d(Li, both); Si = np.setdiff1d(Si, both)
    idx = np.concatenate([Li, Si]); sd = np.concatenate([np.ones(len(Li), np.int8), -np.ones(len(Si), np.int8)])
    o = np.argsort(rank[idx], kind="stable"); idx, sd = idx[o], sd[o]
    j = CONF.index(cfg); busy = -1; out = []
    for i, s in zip(idx, sd):
        if tent[i] < busy: continue
        w = W[j, 0 if s > 0 else 1, i]
        if w < 0: continue
        busy = X[j, 0 if s > 0 else 1, i]
        out.append(dict(coin=coins[coin_id[i]], side=int(s), te=int(tent[i]), xt=int(busy), win=int(w)))
    return out
found = []
for key in M:
    for cfg in ELIG:
        s = seq_full(key, cfg)
        run = []
        for t in s + [dict(win=0)]:
            if t["win"]: run.append(t)
            else:
                if len(run) >= 10: found.append((key, cfg, run))
                run = []
print("Serien >= 10 insgesamt:", len(found))
# gleiche Serie in vielen Varianten -> nach Zeitraum gruppieren, je Gruppe die laengste/ertragreichste behalten
groups = {}
for key, cfg, run in found:
    g = cfg[1]*cfg[0] - 0.008*cfg[0]
    gid = (run[0]["te"] // (86400000*20))           # Startfenster 20 Tage
    score = len(run)*np.log1p(g)
    if gid not in groups or score > groups[gid][0]: groups[gid] = (score, key, cfg, run)
best = sorted(groups.values(), key=lambda x: -x[0])
for score, key, cfg, run in best:
    g = cfg[1]*cfg[0] - 0.008*cfg[0]
    print(f"{pd.to_datetime(run[0]['te'], unit='ms').date()} - {pd.to_datetime(run[-1]['xt'], unit='ms').date()} | {len(run)} Treffer | {key} x{cfg[0]} TP{cfg[1]*100:.1f}% (+{g*100:.0f}%/Treffer) | all-in 30 -> {30*(1+g)**len(run):,.0f} | Coins: {' '.join(t['coin'] for t in run)}")
json.dump([dict(key=list(key), lev=cfg[0], tp=cfg[1], gain=cfg[1]*cfg[0]-0.008*cfg[0], trades=run) for _, key, cfg, run in best],
          open("streak_trades.json", "w"), default=int)
