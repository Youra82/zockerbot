import numpy as np, pandas as pd
D = "."
r = pd.read_parquet(f"{D}/search_result.parquet")
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
TARGET = np.log(1100/30)
r["tage_bis_1100_train"] = np.where(r.g_tr > 0, TARGET/r.g_tr, np.inf)
r["tage_bis_1100_test"] = np.where(r.g_te > 0, TARGET/r.g_te, np.inf)
r["tr_tag"] = (r.n_tr/1095).round(2)
print("Zeilen:", len(r), "| Anteil mit Wachstum >0: train %.1f%%, test %.1f%%" % ((r.g_tr > 0).mean()*100, (r.g_te > 0).mean()*100))
print("Korrelation g_train/g_test (nur g_tr>0): %.3f" % r[r.g_tr > 0][["g_tr", "g_te"]].corr().iloc[0, 1])
for n in [20, 100, 1000]:
    top = r.nlargest(n, "g_tr")
    print(f"Top {n} nach Train: Anteil Test>0 {(top.g_te > 0).mean()*100:.0f}%, Median Test-Tage bis 1100 {np.median(top.tage_bis_1100_test):.0f}")
cols = ["regel", "richtung", "hebel", "tp", "n_tr", "n_te", "wr_tr", "wr_te", "f", "tage_bis_1100_train", "tage_bis_1100_test", "edge_tr", "edge_te"]
print("\nTOP 25 nach Train-Wachstum (Auswahl nur 2021-23):")
print(r.nlargest(25, "g_tr")[cols].round(3).to_string(index=False))
# robuster: mind. 1 Trade/Tag im Train
rb = r[r.n_tr >= 1095]
print("\nTOP 15 mit >= 1 Trade/Tag (Train):")
print(rb.nlargest(15, "g_tr")[cols].round(3).to_string(index=False))
r.nlargest(200, "g_tr").to_csv(f"{D}/search_top200.csv", index=False)
