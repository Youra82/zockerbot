"""zockerbot – Strategie „Ausbruch stark“.

EINE Signalfunktion für Live-Betrieb und Backtest (live.py und backtest.py rufen beide
`signals()` bzw. `day_flags()` auf), damit beide garantiert dasselbe rechnen.

Regel (Long, Short gespiegelt):
  Tageskerze (UTC, abgeschlossen): RSI(14) > 75 UND Schluss > Hoch der 40 Tage davor
  15m-Kerze  (abgeschlossen):      RSI(14) < 30
  -> Einstieg zur Eröffnung der nächsten 15m-Kerze, Take-Profit +7,5 % Kurs, Hebel x10, kein Stop-Loss.

Short: Tages-RSI < 25 UND Schluss < Tief der 40 Tage davor, 15m-RSI > 70.
Feuern Long und Short gleichzeitig, gibt es kein Signal.
"""
import numpy as np
import pandas as pd

DEFAULTS = {
    "rsi_period": 14,
    "donchian_days": 40,
    "rsi_day_long": 75.0,
    "rsi_day_short": 25.0,
    "rsi_15m_long": 30.0,
    "rsi_15m_short": 70.0,
}


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI nach Wilder (exponentielle Glättung mit alpha = 1/n)."""
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def day_flags(df1d: pd.DataFrame, params: dict | None = None) -> pd.Series:
    """Tagesbedingung je abgeschlossener Tageskerze: +1 starker Ausbruch nach oben, -1 nach unten, 0 nichts."""
    p = {**DEFAULTS, **(params or {})}
    r1d = rsi(df1d["close"], int(p["rsi_period"]))
    n = int(p["donchian_days"])
    hi = df1d["high"].rolling(n).max().shift(1)
    lo = df1d["low"].rolling(n).min().shift(1)
    up = (r1d > p["rsi_day_long"]) & (df1d["close"] > hi)
    dn = (r1d < p["rsi_day_short"]) & (df1d["close"] < lo)
    return pd.Series(np.where(up, 1, np.where(dn, -1, 0)), index=df1d.index, name="tag")


def signals(df15: pd.DataFrame, df1d: pd.DataFrame, params: dict | None = None) -> pd.Series:
    """Signal je 15m-Kerze: +1 Long, -1 Short, 0 nichts.

    df15, df1d: NUR abgeschlossene Kerzen, Index = Eröffnungszeit (UTC), Spalten open/high/low/close.
    Eine Tageskerze zählt ab ihrem Schluss (Eröffnung + 1 Tag); sie gilt für jede 15m-Kerze,
    die zu diesem Zeitpunkt oder danach schließt.
    """
    p = {**DEFAULTS, **(params or {})}
    r15 = rsi(df15["close"], int(p["rsi_period"])).to_numpy()
    flag = day_flags(df1d, p).to_numpy()
    day_avail = (df1d.index + pd.Timedelta(days=1)).to_numpy()
    close15 = (df15.index + pd.Timedelta(minutes=15)).to_numpy()
    pos = np.searchsorted(day_avail, close15, side="right") - 1
    f = np.where(pos >= 0, flag[np.clip(pos, 0, None)], 0)
    long_ = (f == 1) & (r15 < p["rsi_15m_long"])
    short_ = (f == -1) & (r15 > p["rsi_15m_short"])
    return pd.Series(np.where(long_, 1, np.where(short_, -1, 0)), index=df15.index, name="signal")


def tp_price(entry: float, side: int, tp_pct: float) -> float:
    """Take-Profit-Kurs: Long über, Short unter dem Einstieg."""
    return entry * (1 + tp_pct) if side > 0 else entry * (1 - tp_pct)


def liquidation_distance(leverage: float, maintenance: float = 0.005) -> float:
    """Ungefähre Kursbewegung bis zur Liquidation bei isolierter Margin (Bitget, kleinste Stufe)."""
    return 1 / leverage - maintenance
