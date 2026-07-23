# -*- coding: utf-8 -*-
"""USQuickFlip shadow collector -- detection core (Gaius Commission 011).

Quick Flip Scalper on US500 (^GSPC): box the first 15-min opening range, require the
range >= 25% of the 14-day daily ATR (a "manipulation" candle), then hunt for an
ENGULFING reversal outside the box within 90 min (bearish above a green open -> short;
bullish below a red open -> long). Entry = break of the reversal candle, stop = beyond
its wick, target = the opposite box end. Fixed GBP20 risk -> stake = 20 / stop_distance.

SHADOW ONLY: this logs theoretical setups + simulated outcomes. It never trades.

NOTE ON THE OPEN: the S&P RTH open is 09:30 America/New_York, i.e. 13:30 UTC in summer
(EDT) and 14:30 UTC in winter (EST). We key off the exchange session (first candle of the
day in US/Eastern) so DST is handled automatically -- NOT a hardcoded UTC time.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

TICKER      = "^GSPC"
ATR_LEN     = 14
THR         = 0.25       # manipulation filter: opening range >= 25% of daily ATR
BOX_N       = 3          # first 3x 5-min candles = the 15-min opening range
WIN_MIN     = 90         # reversal must appear within 90 min of the open
RISK_GBP    = 20.0

CSV_COLUMNS = [
    "date", "opening_high", "opening_low", "opening_range", "daily_atr", "atr_pct",
    "manip_candle", "candle_colour", "reversal_found", "reversal_time", "reversal_type",
    "entry_price", "stop_price", "target_price", "stop_distance", "target_distance",
    "rr_ratio", "stake_gbp", "outcome", "outcome_time", "pnl_gbp", "notes",
]


def _flatten(df):
    if df is None or df.empty:
        return df
    if getattr(df.columns, "nlevels", 1) > 1:
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def fetch():
    """Return (daily_df, five_min_df) for ^GSPC. Raises on total failure."""
    import yfinance as yf
    daily = _flatten(yf.download(TICKER, interval="1d", period="120d",
                                 progress=False, auto_adjust=True))
    five = _flatten(yf.download(TICKER, interval="5m", period="60d",
                                progress=False, auto_adjust=True))
    return daily, five


def atr14(daily):
    """14-day daily ATR keyed by date, taken as of the PRIOR close (no lookahead)."""
    if daily is None or daily.empty:
        return {}
    H, L, C = daily["High"], daily["Low"], daily["Close"]
    pc = C.shift(1)
    tr = pd.concat([H - L, (H - pc).abs(), (L - pc).abs()], axis=1).max(axis=1)
    a = tr.rolling(ATR_LEN).mean().shift(1)
    out = {}
    for ts, v in a.items():
        if pd.notna(v):
            out[pd.Timestamp(ts).date()] = float(v)
    return out


def latest_atr(daily):
    """Most recent available 14-day ATR value (for display / market_context)."""
    a = atr14(daily)
    return a[max(a)] if a else None


def _is_bull_engulf(o, h, l, c, po, pc):
    return (c > o) and (pc < po) and (c >= po) and (o <= pc)


def _is_bear_engulf(o, h, l, c, po, pc):
    return (c < o) and (pc > po) and (c <= po) and (o >= pc)


def analyse_day(g, atr_val, thr=THR, now_utc=None):
    """Analyse one session-day's 5-min candles (g, tz-aware index, US/Eastern date).
    Returns a full record dict (CSV_COLUMNS). Handles PENDING for an incomplete day."""
    day = g.index[0].date()
    rec = {c: "" for c in CSV_COLUMNS}
    rec["date"] = str(day)
    if len(g) < BOX_N + 1 or atr_val is None or atr_val <= 0:
        rec["outcome"] = "NO_SETUP"; rec["notes"] = "insufficient data / no ATR"
        return rec
    O = g["Open"].values; H = g["High"].values; L = g["Low"].values; C = g["Close"].values
    T = g.index
    box_hi = float(H[:BOX_N].max()); box_lo = float(L[:BOX_N].min())
    rng = box_hi - box_lo
    atr_pct = rng / atr_val * 100.0
    green = C[BOX_N - 1] >= O[0]
    rec.update(opening_high=round(box_hi, 2), opening_low=round(box_lo, 2),
               opening_range=round(rng, 2), daily_atr=round(atr_val, 2),
               atr_pct=round(atr_pct, 1),
               manip_candle=("YES" if rng >= thr * atr_val else "NO"),
               candle_colour=("GREEN" if green else "RED"))
    if rng < thr * atr_val:
        rec["reversal_found"] = "NO"; rec["reversal_type"] = "NONE"
        rec["outcome"] = "NO_SETUP"; rec["notes"] = "below ATR threshold"
        return rec
    short = green   # green open -> bearish engulf above box -> short ; red -> long
    win_bars = WIN_MIN // 5
    end = min(BOX_N + win_bars, len(g))
    found = None
    for j in range(BOX_N, end):
        outside = (H[j] > box_hi) if short else (L[j] < box_lo)
        if not outside:
            continue
        ok = _is_bear_engulf(O[j], H[j], L[j], C[j], O[j - 1], C[j - 1]) if short \
            else _is_bull_engulf(O[j], H[j], L[j], C[j], O[j - 1], C[j - 1])
        if ok:
            found = j; break
    if found is None:
        # still inside the window and day not over -> PENDING, else NO_SETUP
        incomplete = (now_utc is not None) and (T[-1] >= T[0]) and (len(g) < BOX_N + win_bars) \
            and (now_utc.date() >= day)
        rec["reversal_found"] = "PENDING" if incomplete else "NO"
        rec["reversal_type"] = "NONE"
        rec["outcome"] = "PENDING" if incomplete else "NO_SETUP"
        rec["notes"] = "watching for reversal" if incomplete else "no engulfing reversal in 90m"
        return rec
    j = found
    rtype = "BEARISH_ENGULF" if short else "BULLISH_ENGULF"
    if short:
        entry = float(L[j]); stop = float(H[j]); target = box_lo
    else:
        entry = float(H[j]); stop = float(L[j]); target = box_hi
    stop_d = abs(entry - stop); targ_d = abs(target - entry)
    rec.update(reversal_found="YES", reversal_time=T[j].strftime("%H:%M UTC"),
               reversal_type=rtype, entry_price=round(entry, 2), stop_price=round(stop, 2),
               target_price=round(target, 2), stop_distance=round(stop_d, 2),
               target_distance=round(targ_d, 2))
    if stop_d <= 0 or targ_d <= 0:
        rec["outcome"] = "NO_SETUP"; rec["notes"] = "degenerate stop/target"
        return rec
    rr = targ_d / stop_d
    stake = RISK_GBP / stop_d
    rec["rr_ratio"] = round(rr, 2); rec["stake_gbp"] = round(stake, 4)
    # simulate: trigger on break, then target/stop first
    outcome = None; triggered = False; out_time = ""
    for k in range(j + 1, len(g)):
        if not triggered:
            if (short and L[k] <= entry) or ((not short) and H[k] >= entry):
                triggered = True
            else:
                continue
        if short:
            if H[k] >= stop: outcome = "LOSS"; out_time = T[k].strftime("%H:%M UTC"); break
            if L[k] <= target: outcome = "WIN"; out_time = T[k].strftime("%H:%M UTC"); break
        else:
            if L[k] <= stop: outcome = "LOSS"; out_time = T[k].strftime("%H:%M UTC"); break
            if H[k] >= target: outcome = "WIN"; out_time = T[k].strftime("%H:%M UTC"); break
    if not triggered:
        # setup found but entry break not yet hit
        incomplete = (now_utc is not None) and (now_utc.date() >= day) and (len(g) < 78)
        rec["outcome"] = "PENDING" if incomplete else "NO_SETUP"
        rec["notes"] = "reversal found, entry not triggered" + ("" if incomplete else " (day closed)")
        return rec
    if outcome is None:
        rec["outcome"] = "PENDING"; rec["notes"] = "in trade, unresolved"
        return rec
    rec["outcome"] = outcome
    rec["outcome_time"] = out_time
    rec["pnl_gbp"] = round(rr * RISK_GBP, 2) if outcome == "WIN" else round(-RISK_GBP, 2)
    return rec


def build_records(daily, five, thr=THR, now_utc=None):
    """One record per US session-day (US/Eastern date) over the 5-min history."""
    if five is None or five.empty:
        return []
    idx = five.index
    try:
        est = idx.tz_convert("America/New_York")
    except Exception:
        est = idx
    dates = pd.Index(est.date)
    atr = atr14(daily)
    recs = []
    for day in sorted(set(dates)):
        g = five[dates == day]
        recs.append(analyse_day(g, atr.get(day), thr=thr, now_utc=now_utc))
    return recs


def stats(records):
    resolved = [r for r in records if r.get("outcome") in ("WIN", "LOSS")]
    setups = [r for r in records if r.get("reversal_found") == "YES"]
    manip = [r for r in records if r.get("manip_candle") == "YES"]
    days = [r for r in records if r.get("date")]
    wins = [r for r in resolved if r["outcome"] == "WIN"]
    def _f(v):
        try: return float(v)
        except (TypeError, ValueError): return 0.0
    total_pnl = sum(_f(r.get("pnl_gbp")) for r in resolved)
    avg_rr = np.mean([_f(r["rr_ratio"]) for r in setups]) if setups else 0.0
    return {
        "trading_days": len(days),
        "manip_days": len(manip),
        "manip_pct": round(len(manip) / len(days) * 100, 0) if days else 0,
        "setups": len(setups),
        "reversal_pct": round(len(setups) / len(manip) * 100, 0) if manip else 0,
        "resolved": len(resolved),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(resolved) * 100, 1) if resolved else 0.0,
        "avg_rr": round(float(avg_rr), 2),
        "total_pnl_gbp": round(total_pnl, 2),
    }
