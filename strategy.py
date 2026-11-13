"""zockerbot – Strategie „Rücksetzer im Ausbruch“.

EINE Signalfunktion für Live-Betrieb und Backtest (live.py und backtest.py rufen beide
`signals()` auf), damit beide garantiert dasselbe rechnen.

Regel (Long, Short gespiegelt):
  Tageskerze (UTC, abgeschlossen): RSI(14) > 70 UND Schluss > Hoch der 20 Tage davor
  15m-Kerze  (abgeschlossen):      RSI(14) < 30
  -> Einstieg zur Eröffnung der nächsten 15m-Kerze, Take-Profit +5 % Kurs, kein Stop-Loss.

Short: Tages-RSI < 30 UND Schluss < Tief der 20 Tage davor, 15m-RSI > 70.
Feuern Long und Short gleichzeitig, gibt es kein Signal.
"""
import numpy as np
import pandas as pd

DEFAULTS = {
    "rsi_period": 14,
    "donchian_days": 20,
    "rsi_day_long": 70.0,
    "rsi_day_short": 30.0,
    "rsi_15m_long": 30.0,
    "rsi_15m_short": 70.0,
}


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI nach Wilder (exponentielle Glättung mit alpha = 1/n)."""
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def signals(df15: pd.DataFrame, df1d: pd.DataFrame, params: dict | None = None) -> pd.Series:
    """Signal je 15m-Kerze: +1 Long, -1 Short, 0 nichts.

    df15, df1d: NUR abgeschlossene Kerzen, Index = Eröffnungszeit (UTC, tz-aware oder naiv,
    aber beide gleich), Spalten open/high/low/close.
    Eine Tageskerze zählt ab ihrem Schluss (Eröffnung + 1 Tag); sie gilt für jede 15m-Kerze,
    die zu diesem Zeitpunkt oder danach schließt.
    """
    p = {**DEFAULTS, **(params or {})}
    n = int(p["rsi_period"])
    r15 = rsi(df15["close"], n)

    r1d = rsi(df1d["close"], n)
    hi = df1d["high"].rolling(int(p["donchian_days"])).max().shift(1)
    lo = df1d["low"].rolling(int(p["donchian_days"])).min().shift(1)
    day_long = ((r1d > p["rsi_day_long"]) & (df1d["close"] > hi)).to_numpy()
    day_short = ((r1d < p["rsi_day_short"]) & (df1d["close"] < lo)).to_numpy()

    day_avail = (df1d.index + pd.Timedelta(days=1)).to_numpy()
    close15 = (df15.index + pd.Timedelta(minutes=15)).to_numpy()
    pos = np.searchsorted(day_avail, close15, side="right") - 1
    ok = pos >= 0
    pc = np.clip(pos, 0, None)
    dl = np.where(ok, day_long[pc], False)
    ds = np.where(ok, day_short[pc], False)

    long_ = (r15.to_numpy() < p["rsi_15m_long"]) & dl
    short_ = (r15.to_numpy() > p["rsi_15m_short"]) & ds
    sig = np.where(long_ & ~short_, 1, np.where(short_ & ~long_, -1, 0))
    return pd.Series(sig, index=df15.index, name="signal")


def tp_price(entry: float, side: int, tp_pct: float) -> float:
    """Take-Profit-Kurs: Long über, Short unter dem Einstieg."""
    return entry * (1 + tp_pct) if side > 0 else entry * (1 - tp_pct)


def liquidation_distance(leverage: float, maintenance: float = 0.005) -> float:
    """Ungefähre Kursbewegung bis zur Liquidation bei isolierter Margin (Bitget, kleinste Stufe)."""
    return 1 / leverage - maintenance
