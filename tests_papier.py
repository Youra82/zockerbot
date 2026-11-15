"""Offline-Prüfung des Papierkontos (keine Netzverbindung, keine Orders): python tests_papier.py"""
import os
import tempfile
import unittest

from papier import PapierKonto, SPREAD, FEE, echtgeld_aktiv, startkapital

M = 60_000


class FakeEx:
    def __init__(self):
        self.kerzen, self.last = {}, 100.0

    def fetch_ticker(self, symbol):
        return {"last": self.last}

    def fetch_ohlcv(self, symbol, tf, since, limit):
        return [c for c in self.kerzen.get(symbol, []) if c[0] >= since][:limit]


class Uhr:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def konto(d, uhr, ex, start=100.0):
    return PapierKonto(os.path.join(d, "k.json"), start, ex, now_fn=uhr)


class Papier(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.uhr, self.ex = Uhr(10 * M + 30_000), FakeEx()

    def test_tp_long(self):
        k = konto(self.d, self.uhr, self.ex)
        p = k.eroeffnen("X/USDT:USDT", "long", 1.0, 100.0, 10, tp=107.5)
        self.assertAlmostEqual(p["entry"], 100 * (1 + SPREAD))
        self.ex.kerzen["X/USDT:USDT"] = [(10 * M, 100, 101, 99, 100, 0), (11 * M, 100, 101, 99, 100, 0),
                                         (12 * M, 101, 108, 100, 107, 0)]
        self.uhr.t = 14 * M
        k.abrechnen()
        self.assertEqual(k.positionen, [])
        c = k.s["closed"][0]
        self.assertEqual(c["grund"], "TP")
        erwartet = (107.5 - p["entry"]) - p["fee_in"] - 107.5 * FEE
        self.assertAlmostEqual(c["pnl"], erwartet, places=9)
        self.assertAlmostEqual(k.s["cash"], 100 + erwartet, places=9)

    def test_minute_of_entry_ignored(self):
        k = konto(self.d, self.uhr, self.ex)
        k.eroeffnen("X/USDT:USDT", "long", 1.0, 100.0, 10, tp=107.5)
        self.ex.kerzen["X/USDT:USDT"] = [(10 * M, 100, 120, 80, 100, 0)]          # Einstiegsminute: nicht werten
        self.uhr.t = 11 * M + 1
        k.abrechnen()
        self.assertEqual(len(k.positionen), 1)

    def test_liquidation_without_sl(self):
        k = konto(self.d, self.uhr, self.ex)
        p = k.eroeffnen("X/USDT:USDT", "long", 1.0, 100.0, 10, tp=107.5)
        cash0 = k.s["cash"]
        self.ex.kerzen["X/USDT:USDT"] = [(11 * M, 100, 101, 90, 91, 0)]
        self.uhr.t = 13 * M
        k.abrechnen()
        c = k.s["closed"][0]
        self.assertEqual(c["grund"], "Liquidation")
        self.assertAlmostEqual(c["pnl"], -p["margin"] - p["fee_in"])
        self.assertAlmostEqual(k.s["cash"], cash0)                                 # Margin weg, nichts zurück

    def test_sl_before_tp_same_candle_and_gap(self):
        k = konto(self.d, self.uhr, self.ex)
        k.eroeffnen("X/USDT:USDT", "short", 2.0, 100.0, 5, sl=103.0, tp=95.0)
        self.ex.kerzen["X/USDT:USDT"] = [(11 * M, 104, 105, 94, 96, 0)]           # Lücke über SL, TP auch erreicht
        self.uhr.t = 13 * M
        k.abrechnen()
        c = k.s["closed"][0]
        self.assertEqual(c["grund"], "SL")
        self.assertAlmostEqual(c["exit"], 104 * (1 + SPREAD))                    # Eröffnungskurs + Spread

    def test_equity_and_switch_helpers(self):
        k = konto(self.d, self.uhr, self.ex)
        k.eroeffnen("X/USDT:USDT", "long", 1.0, 100.0, 10)
        self.assertAlmostEqual(k.realisiert(), 100 - k.positionen[0]["fee_in"])
        self.assertAlmostEqual(k.kontostand({"X/USDT:USDT": 110.0}),
                               k.realisiert() + (110 - k.positionen[0]["entry"]))
        self.assertAlmostEqual(k.kontostand({"X/USDT:USDT": 1.0}), k.realisiert() - k.positionen[0]["margin"])
        self.assertTrue(echtgeld_aktiv({}))
        self.assertFalse(echtgeld_aktiv({"echtgeld": {"aktiv": False}}))
        self.assertEqual(startkapital({"echtgeld": {"papier_startkapital": 250}}), 250.0)
        with self.assertRaises(ValueError):
            k.eroeffnen("Y/USDT:USDT", "long", 100.0, 100.0, 1)                  # zu wenig Guthaben

    def test_persist_and_market_close(self):
        k = konto(self.d, self.uhr, self.ex)
        p = k.eroeffnen("X/USDT:USDT", "long", 1.0, 100.0, 10)
        k2 = konto(self.d, self.uhr, self.ex)
        self.assertEqual(len(k2.positionen), 1)
        pnl = k2.schliessen(k2.positionen[0], 100.0, "Market")
        aus = 100 * (1 - SPREAD)
        self.assertAlmostEqual(pnl, (aus - p["entry"]) - p["fee_in"] - aus * FEE, places=9)


if __name__ == "__main__":
    unittest.main()
