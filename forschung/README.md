# Forschung zum zockerbot

Alle Skripte werden in diesem Ordner gestartet. Kerzen liegen nicht im Repo:
`download40.py` lädt 15m-Kerzen von 42 Binance-Futures-Coins (2021–10/2026) nach `kerzen40/ohlcv_15m/`.

**v3 – „Ausbruch stark“ (aktuelle Regel)**

| Datei | Inhalt |
|---|---|
| `improve.py` | 2.160 Varianten (RSI-Schwellen, Tages-RSI, Donchian, Filter, Hebel, TP) auf 42 Coins; Auswahl Gruppe A 2021–23, Gegenprobe A 2024–26 und Gruppe B → `improve_result.csv` |
| `portfolio.py`, `portfolio2.py` | gemeinsames Konto: Einsatzanteil und Höchstzahl gleichzeitiger Positionen |
| `streaks.py`, `streak_trades.py` | Serien mit ≥ 10 Treffern in Folge à > +50 % |
| `absahnen.py` | Kontoverlauf „Ausbruch stark“, all-in mit Auszahlungsziel |
| `tipp_zonen.py` | Cockpit-Zonen (Treppe/Aufzug/Rückprall) als Filter und als TP |
| `multi.py` | mehrere Regeln gleichzeitig (Auswahl Gruppe A 2021–23) gegen die Einzelregel |
| `levtp.py` | Hebel/TP-Varianten der Regel als Konto (Serie mit Tresor, Anteil) |
| `tsl_test.py` | Bitget-Trailing-Stop statt festem TP auf 1m-Kerzen (8 Coins, Ordner per `ZB_KERZEN_1M`) |
| `ausbruch_stark_trades.csv` | Trade-Folge des Bots (eine Position gleichzeitig, x10, TP 7,5 %), Grundlage der README-Grafiken |

**v2 – „Rücksetzer im Ausbruch“ (abgelöst)**: `labels.py`, `features.py`, `search.py`, `analyse.py`, `holdout.py`, `winner.py`,
`winner_trades.csv`, `holdout_result.csv`, `search_top200.csv` – Suche über 39.773 Kombinationen auf 8 + 3 Coins.
