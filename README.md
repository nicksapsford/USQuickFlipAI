# USQuickFlip A.I. — Shadow Collector
**Version:** 1.0.0 | **Port:** 5009 | **Status:** SHADOW (no capital) | **Desk:** QuickFlip (future)

Part of the **Albion Trading Desk**. USQuickFlip is a **shadow data collector** for the
**Quick Flip Scalper** strategy (Gaius Commission 011) on **US500 (S&P 500, ^GSPC)**. It
observes and logs theoretical setups + simulated outcomes to validate the ~40% win rate
out of sample **before** any live/paper trading system is built. It does **not** connect to
a broker and **never trades real capital**.

## The strategy (Commission 011)
1. **Box the opening range** — the first 15-minute candle of the US RTH session
   (high/low incl. wicks).
2. **Manipulation filter** — opening range ≥ **25%** of the 14-day daily ATR (22–23% ok);
   below → no trade that day.
3. **Engulfing reversal** (within 90 min, 5-min candles, **engulfing only** — no hammers):
   GREEN opening candle → **bearish** engulfing above the box → **short**;
   RED opening candle → **bullish** engulfing below the box → **long**.
4. **Entry** = break of the reversal candle · **Stop** = beyond its wick ·
   **Target** = opposite end of the opening-range box.
5. **Sizing** = fixed **£20 risk** → stake = 20 ÷ stop distance. **No Profit Protection
   Ladder** (it would clip the ~2.7:1 winners that carry the strategy).

## Session / open time
The S&P RTH open is **09:30 America/New_York** — **13:30 UTC in summer (EDT)**, 14:30 UTC in
winter (EST). The collector keys off the **exchange session open** (first candle of the day),
so DST is handled automatically — it is *not* hardcoded to a UTC time.

## What it is / isn't
- **Is:** a Flask one-page dashboard + a background poller (every 5 min) that re-analyses
  ^GSPC via yfinance, logs each day to `logs/quickflip_log.csv`, and shows running stats.
- **Isn't:** no Stanley/Excalibur/Arthur/Morgan/Lancelot/Percival, no broker, no capital,
  no P&L/phantom/Guinevere pages.

## Data
yfinance `^GSPC` (daily for ATR + 5-minute intraday, ~15-min delayed — fine for a shadow
collector). No API keys required.

## Running
```
python dashboard_usquickflip.py     # collector + dashboard, port 5009
```
Or the desktop shortcut **Start USQuickFlip** (starts it and opens the browser).

## Next step (if validated)
After 3–4 weeks confirming the win rate, the follow-on is **USQuickFlipTrader (port 5061)** —
a live paper system (Stanley + Capital.com US500), Type-1 hybrid (Lancelot detects the setup,
Stanley enters, Arthur manages the exit). This collector is the precursor; get the data right first.

All times UTC.
