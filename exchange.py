"""Bitget-Anbindung (USDT-Perpetuals) – übernommen aus dem live erprobten mbot
(Hedge-Modus, isolierte Margin, TP als reduce-only Trigger-Order)."""
import logging
import time

import ccxt
import pandas as pd

logger = logging.getLogger(__name__)
PRODUCT = {"productType": "USDT-FUTURES", "marginCoin": "USDT"}


class Exchange:
    def __init__(self, account: dict | None = None):
        account = account or {}
        self.exchange = ccxt.bitget({
            "apiKey": account.get("apiKey"),
            "secret": account.get("secret"),
            "password": account.get("password"),
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
        })
        self.markets = {}
        self._ensure_markets()

    def _ensure_markets(self):
        if self.markets:
            return
        last = None
        for attempt in range(3):
            try:
                self.markets = self.exchange.load_markets()
                return
            except Exception as e:  # Netz-Hickser
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"Märkte nicht ladbar: {last}")

    # --- Kerzen ---
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Letzte `limit` Kerzen, überlappend paginiert (keine Lücke an Seitengrenzen).
        Index = Eröffnung (UTC). Enthält evtl. noch die laufende Kerze -> closed_only()."""
        tf_ms = self.exchange.parse_timeframe(timeframe) * 1000
        since = self.exchange.milliseconds() - tf_ms * (limit + 1)
        rows, last_ts, retries = [], None, 0
        while since < self.exchange.milliseconds():
            try:
                batch = self.exchange.fetch_ohlcv(symbol, timeframe, since, 200)
            except ccxt.NetworkError as e:
                retries += 1
                if retries > 5:
                    raise
                logger.warning(f"OHLCV {symbol} {timeframe}: {type(e).__name__}, Retry {retries}/5")
                time.sleep(2 * retries)
                continue
            retries = 0
            batch = [c for c in batch if last_ts is None or c[0] > last_ts]
            if not batch:
                break
            rows.extend(batch)
            last_ts = batch[-1][0]
            since = last_ts
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df.iloc[-limit:]

    def closed_only(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Laufende (noch nicht abgeschlossene) Kerze entfernen."""
        tf = pd.Timedelta(seconds=self.exchange.parse_timeframe(timeframe))
        now = pd.Timestamp.now(tz="UTC")
        return df[df.index + tf <= now]

    # --- Konto ---
    def fetch_equity(self) -> tuple[float, float]:
        """(Gesamtkapital, frei verfügbar) in USDT."""
        bal = self.exchange.fetch_balance(params=PRODUCT)
        u = bal.get("USDT", {})
        total = float(u.get("total") or 0.0)
        free = float(u.get("free") or 0.0)
        return total, free

    def fetch_all_open_positions(self) -> dict:
        """Alle offenen USDT-Futures-Positionen: {Basis-Coin: Position}. Wirft bei API-Fehlern weiter."""
        self._ensure_markets()
        last = None
        for attempt in range(2):
            try:
                ps = self.exchange.fetch_positions(None, params=PRODUCT)
                return {p["symbol"].split("/")[0]: p for p in ps if abs(float(p.get("contracts") or 0)) > 1e-12}
            except Exception as e:
                last = e
                time.sleep(2)
        raise last

    def fetch_open_positions(self, symbol: str) -> list:
        """Wirft bei API-Fehlern weiter: [] heißt garantiert 'keine Position'."""
        self._ensure_markets()
        last = None
        for attempt in range(2):
            try:
                ps = self.exchange.fetch_positions([symbol], params=PRODUCT)
                return [p for p in ps if abs(float(p.get("contracts") or 0)) > 1e-12]
            except Exception as e:
                last = e
                time.sleep(2)
        raise last

    def fetch_open_trigger_orders(self, symbol: str) -> list:
        orders = []
        for plan in ("normal_plan", "profit_loss"):
            orders.extend(self.exchange.fetch_open_orders(
                symbol, params={"trigger": True, "planType": plan, "productType": "USDT-FUTURES"}))
        return orders

    def min_amount(self, symbol: str) -> float:
        m = self.markets.get(symbol, {})
        return float(((m.get("limits") or {}).get("amount") or {}).get("min") or 0.0)

    # --- Einstellungen ---
    def set_isolated(self, symbol: str):
        try:
            self.exchange.set_margin_mode("isolated", symbol, params=PRODUCT)
        except ccxt.ExchangeError as e:
            if not any(x in str(e) for x in ("Margin mode is the same", "40051")):
                raise

    def set_leverage(self, symbol: str, leverage: int):
        try:
            self.exchange.set_leverage(leverage, symbol, params={**PRODUCT, "marginMode": "isolated"})
        except ccxt.ExchangeError as e:
            if not any(x in str(e) for x in ("Leverage not changed", "40052")):
                raise

    # --- Orders ---
    def market_order(self, symbol: str, side: str, amount: float, reduce: bool = False) -> dict:
        amt = float(self.exchange.amount_to_precision(symbol, amount))
        params = {**PRODUCT, "marginMode": "isolated", "hedged": True, "reduceOnly": reduce}
        logger.info(f"Market {side.upper()} {amt} {symbol} reduce={reduce}")
        return self.exchange.create_order(symbol, "market", side, amt, params=params)

    def take_profit(self, symbol: str, close_side: str, amount: float, trigger: float) -> dict:
        """TP als reduce-only Trigger-Market-Order (wie mbot)."""
        amt = float(self.exchange.amount_to_precision(symbol, amount))
        px = self.exchange.price_to_precision(symbol, trigger)
        params = {"triggerPrice": px, "reduceOnly": True, "productType": "USDT-FUTURES",
                  "marginMode": "isolated", "hedged": True}
        logger.info(f"TP {close_side.upper()} {amt} {symbol} @ {px}")
        return self.exchange.create_order(symbol, "market", close_side, amt, params=params)

    def cancel_all(self, symbol: str):
        for stop in (False, True):
            try:
                self.exchange.cancel_all_orders(symbol, params={"productType": "USDT-FUTURES", "stop": stop})
            except ccxt.ExchangeError as e:
                if not any(x in str(e) for x in ("Order not found", "no order to cancel", "22001")):
                    logger.error(f"Stornieren {symbol} (stop={stop}): {e}")


class PapierExchange(Exchange):
    """Gleiche Schnittstelle wie Exchange, aber Buchung im Papierkonto (papier.py) mit echten Bitget-Kursen.
    Kerzen/Kurse öffentlich; es wird nie eine Order an Bitget geschickt (kein Schlüssel)."""
    papier = True

    def __init__(self, konto_pfad: str, start: float):
        super().__init__({})
        from papier import PapierKonto
        self.konto = PapierKonto(konto_pfad, start, self.exchange)
        self._lev = {}

    def _side(self, buy: bool) -> str:
        return "long" if buy else "short"

    def fetch_equity(self) -> tuple[float, float]:
        self.konto.abrechnen()
        kurse = {}
        for p in self.konto.positionen:
            try:
                kurse[p["symbol"]] = self.konto.kurs(p["symbol"])
            except Exception:
                pass
        return self.konto.kontostand(kurse), self.konto.s["cash"]

    def _ccxt_pos(self, p):
        return {"symbol": p["symbol"], "side": p["side"], "contracts": p["qty"], "entryPrice": p["entry"],
                "initialMargin": p["margin"], "leverage": p["lev"], "liquidationPrice": p["liq"]}

    def fetch_all_open_positions(self) -> dict:
        self.konto.abrechnen()
        return {p["symbol"].split("/")[0]: self._ccxt_pos(p) for p in self.konto.positionen}

    def fetch_open_positions(self, symbol: str) -> list:
        self.konto.abrechnen()
        return [self._ccxt_pos(p) for p in self.konto.positionen if p["symbol"] == symbol]

    def fetch_open_trigger_orders(self, symbol: str) -> list:
        return [{"id": "papier-tp", "triggerPrice": p["tp"]} for p in self.konto.positionen
                if p["symbol"] == symbol and p.get("tp")]

    def set_isolated(self, symbol: str):
        pass

    def set_leverage(self, symbol: str, leverage: int):
        self._lev[symbol] = int(leverage)

    def market_order(self, symbol: str, side: str, amount: float, reduce: bool = False) -> dict:
        kurs = self.konto.kurs(symbol)
        amt = float(self.exchange.amount_to_precision(symbol, amount))
        if reduce:                                      # Schließen: Gegenseite der Order
            p = self.konto.position(symbol, self._side(side == "sell"))
            if p:
                self.konto.schliessen(p, kurs, "Market")
            return {"average": kurs, "filled": amt}
        p = self.konto.eroeffnen(symbol, self._side(side == "buy"), amt, kurs, self._lev.get(symbol, 1))
        logger.info(f"PAPIER Market {side.upper()} {amt} {symbol} @ {p['entry']:.6g}")
        return {"average": p["entry"], "filled": amt}

    def take_profit(self, symbol: str, close_side: str, amount: float, trigger: float) -> dict:
        side = self._side(close_side == "sell")
        self.konto.setze(symbol, side, tp=float(self.exchange.price_to_precision(symbol, trigger)))
        logger.info(f"PAPIER TP {close_side.upper()} {symbol} @ {trigger:.6g}")
        return {"id": "papier-tp"}

    def cancel_all(self, symbol: str):
        pass
