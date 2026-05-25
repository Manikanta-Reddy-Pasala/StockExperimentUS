"""Leveraged-ETF regime rotation backtest (US, cash-buyable, no margin).

Strategy:
  Risk-on  -> hold a leveraged ETF (default TQQQ = 3x Nasdaq-100)
  Risk-off -> hold cash (or BIL, 1-3m T-bill ETF)

  Regime is read off the UNDERLYING index (default QQQ), NOT the leveraged ETF:
    risk_on = QQQ_close > SMA(main)        [base 200d gate]
              AND (second gate off OR QQQ_close > SMA(second))   [optional 50d]
    with optional buffer band + N-day confirm to damp whipsaw.

  Signal is computed on close of day t and applied to day t+1 return (no lookahead).

DD control knobs (the point of this model):
  --sma 200          main trend gate length
  --second-sma 50    faster exit gate (0 = off); risk-off if price under EITHER
  --partial 1.0      fraction in the leveraged ETF when risk-on (rest -> risk-off
                     asset). 0.5 => half TQQQ / half cash ~ effective 1.5x, lower DD
  --buffer-pct 0.0   exit only when price is this % BELOW the SMA (hysteresis)
  --confirm-days 1   require N consecutive risk-off closes before switching out
  --riskoff cash|bil idle asset when out of the market

Returns use adj_close (captures BIL dividend yield + TQQQ tiny div); the SMA
signal uses raw close. Drawdown is computed on the DAILY equity curve (true MaxDD),
unlike the trade-snapshot DD in the equity-rotation models.

Costs: IBKR Lite => $0 commission. Slippage applied on turnover at switch days.
TQQQ's 0.84% expense + volatility decay are already baked into its real prices.
"""
from __future__ import annotations
import sys, os, json, argparse
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DEFAULT_START = date(2010, 2, 11)   # TQQQ inception
DEFAULT_END   = date(2026, 5, 24)
DEFAULT_CAP   = 100_000.0
SLIPPAGE_BPS  = 8.0                  # one-way, applied to turnover on switch days


def get_engine():
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system",
    )
    if url.startswith("postgresql+psycopg://"):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
    return create_engine(url, pool_pre_ping=True)


def load_series(eng, sym: str, start: date, end: date) -> pd.DataFrame:
    """Return DataFrame indexed by date with raw close + adj_close for one symbol."""
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT date, close, adj_close FROM historical_data "
            "WHERE symbol=:s AND data_source='yfinance' AND date BETWEEN :a AND :b "
            "ORDER BY date"
        ), c, params={"s": sym, "a": start, "b": end})
    if df.empty:
        raise SystemExit(f"No data for {sym} in {start}..{end}. Pull it first.")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["adj_close"] = df["adj_close"].fillna(df["close"])
    return df


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(-dd.min() * 100)  # positive %


def run(start: date, end: date, capital: float,
        lev: str = "TQQQ", index_sym: str = "QQQ",
        sma: int = 200, second_sma: int = 0, partial: float = 1.0,
        buffer_pct: float = 0.0, confirm_days: int = 1, target_vol: float = 0.0,
        riskoff: str = "cash", label: str | None = None,
        out_dir: Path | None = None, quiet: bool = False) -> dict:
    eng = get_engine()

    # Index history from well before `start` so the SMA is valid on day 1.
    idx = load_series(eng, index_sym, date(start.year - 2, 1, 1), end)
    levdf = load_series(eng, lev, start, end)
    bench = load_series(eng, index_sym, start, end)

    sma_main = idx["close"].rolling(sma).mean()
    sma_2nd  = idx["close"].rolling(second_sma).mean() if second_sma > 0 else None

    # raw risk-on signal on the index calendar
    on = idx["close"] > sma_main * (1.0 - buffer_pct / 100.0)
    if sma_2nd is not None:
        on = on & (idx["close"] > sma_2nd)
    on = on.fillna(False)

    # N-day confirm applied purely as an EXIT delay: flip to risk-off only after
    # `confirm_days` consecutive off closes; any risk-on close re-enters immediately.
    if confirm_days > 1:
        state, cur, run_off = [], False, 0
        for v in on.values:
            if v:
                cur, run_off = True, 0
            else:
                run_off += 1
                if run_off >= confirm_days:
                    cur = False
            state.append(cur)
        signal = pd.Series(state, index=on.index)
    else:
        signal = on

    # Restrict to the leveraged ETF's trading calendar within [start, end]
    cal = levdf.index.intersection(bench.index)
    cal = cal[(cal >= pd.Timestamp(start)) & (cal <= pd.Timestamp(end))]
    signal = signal.reindex(cal).ffill().fillna(False)

    # Decide at close t, hold for t+1 -> shift signal by one bar
    held = signal.shift(1).fillna(False)

    lev_ret = levdf["adj_close"].reindex(cal).pct_change().fillna(0.0)
    if riskoff == "bil":
        ro = load_series(eng, "BIL", start, end)
        ro_ret = ro["adj_close"].reindex(cal).ffill().pct_change().fillna(0.0)
    else:
        ro_ret = pd.Series(0.0, index=cal)  # plain cash

    w_lev = held.astype(float) * partial
    if target_vol > 0:
        # volatility targeting: scale leveraged exposure down when its vol spikes.
        # scale = target / realized (annualized 20d), capped at 1 (never lever beyond `partial`).
        rv = (lev_ret.rolling(20).std() * (252 ** 0.5)).replace(0, pd.NA)
        scale = (target_vol / 100.0 / rv).clip(upper=1.0).shift(1).fillna(1.0)
        w_lev = w_lev * scale
    w_ro  = 1.0 - w_lev
    port_ret = w_lev * lev_ret + w_ro * ro_ret

    # turnover cost on weight changes (slippage one-way per unit traded)
    turnover = w_lev.diff().abs().fillna(w_lev.abs())
    cost = turnover * (SLIPPAGE_BPS / 1e4)
    port_ret = port_ret - cost

    equity = (1.0 + port_ret).cumprod() * capital

    # benchmarks
    bh_lev = (1.0 + lev_ret).cumprod() * capital
    bh_idx = (1.0 + bench["adj_close"].reindex(cal).pct_change().fillna(0.0)).cumprod() * capital

    yrs = (cal[-1] - cal[0]).days / 365.25
    final = float(equity.iloc[-1])
    cagr = ((final / capital) ** (1 / yrs) - 1) * 100
    mdd = max_drawdown(equity)
    calmar = cagr / max(0.01, mdd)
    switches = int((held != held.shift()).sum())
    tim = float(held.mean() * 100)  # % time in market

    bh_lev_cagr = ((float(bh_lev.iloc[-1]) / capital) ** (1 / yrs) - 1) * 100
    bh_lev_mdd  = max_drawdown(bh_lev)
    bh_idx_cagr = ((float(bh_idx.iloc[-1]) / capital) ** (1 / yrs) - 1) * 100
    bh_idx_mdd  = max_drawdown(bh_idx)

    name = label or (
        f"{lev} gate{sma}" + (f"+{second_sma}" if second_sma else "") +
        (f" p{partial:g}" if partial != 1.0 else "") +
        (f" buf{buffer_pct:g}" if buffer_pct else "") +
        (f" cf{confirm_days}" if confirm_days > 1 else "") +
        (f" {riskoff}" if riskoff != "cash" else "")
    )

    res = {
        "label": name, "lev": lev, "index": index_sym,
        "start": cal[0].date().isoformat(), "end": cal[-1].date().isoformat(),
        "years": round(yrs, 2), "capital": capital, "final_nav": round(final, 0),
        "cagr_pct": round(cagr, 2), "max_dd_pct": round(mdd, 2), "calmar": round(calmar, 2),
        "switches": switches, "time_in_market_pct": round(tim, 1),
        "params": {"sma": sma, "second_sma": second_sma, "partial": partial,
                   "buffer_pct": buffer_pct, "confirm_days": confirm_days, "riskoff": riskoff},
        "bench_buyhold_lev": {"cagr_pct": round(bh_lev_cagr, 2), "max_dd_pct": round(bh_lev_mdd, 2)},
        "bench_buyhold_index": {"cagr_pct": round(bh_idx_cagr, 2), "max_dd_pct": round(bh_idx_mdd, 2)},
    }

    if not quiet:
        print(f"\n## {name}  ({res['start']} -> {res['end']}, {yrs:.1f}y)")
        print(f"  Final NAV: ${final:,.0f}   CAGR {cagr:+.2f}%   MaxDD {mdd:.2f}%   Calmar {calmar:.2f}")
        print(f"  Switches: {switches}   Time in market: {tim:.1f}%")
        print(f"  vs buy-hold {lev}: CAGR {bh_lev_cagr:+.1f}% / DD {bh_lev_mdd:.1f}%   "
              f"vs {index_sym}: CAGR {bh_idx_cagr:+.1f}% / DD {bh_idx_mdd:.1f}%")

    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(res, indent=2))
        equity.rename("equity").to_frame().assign(held=held.astype(int)).to_csv(out_dir / "equity_curve.csv")
        # transaction log = regime switches (buy/sell the leveraged ETF)
        levpx = levdf["close"].reindex(cal).ffill()
        txns, prev = [], False
        trades, open_leg = [], None       # paired entry->exit ledger
        for i, dt in enumerate(cal):
            h = bool(held.loc[dt])
            if h != prev:
                px = float(levpx.loc[dt]); val = float(equity.loc[dt]) * partial
                sh = round(val / px, 4)
                txns.append({"date": dt.date().isoformat(),
                             "action": ("BUY_" + lev) if h else ("SELL_" + lev),
                             "symbol": lev, "price": round(px, 4),
                             "shares": sh, "value": round(val, 2)})
                if h:
                    open_leg = {"symbol": lev, "entry_date": dt.date().isoformat(),
                                "entry_px": round(px, 4), "shares": sh, "entry_i": i}
                elif open_leg is not None:
                    ep = open_leg["entry_px"]
                    trades.append({"symbol": lev, "entry_date": open_leg["entry_date"],
                                   "entry_px": ep, "shares": open_leg["shares"],
                                   "exit_date": dt.date().isoformat(), "exit_px": round(px, 4),
                                   "pnl": round(open_leg["shares"] * (px - ep), 2),
                                   "ret_pct": round((px / ep - 1) * 100, 2),
                                   "bars_held": i - open_leg["entry_i"], "open": False})
                    open_leg = None
            prev = h
        if open_leg is not None:          # still in TQQQ at end -> mark open leg
            dt = cal[-1]; px = float(levpx.loc[dt]); ep = open_leg["entry_px"]
            trades.append({"symbol": lev, "entry_date": open_leg["entry_date"],
                           "entry_px": ep, "shares": open_leg["shares"],
                           "exit_date": dt.date().isoformat(), "exit_px": round(px, 4),
                           "pnl": round(open_leg["shares"] * (px - ep), 2),
                           "ret_pct": round((px / ep - 1) * 100, 2),
                           "bars_held": (len(cal) - 1) - open_leg["entry_i"], "open": True})
        if txns:
            pd.DataFrame(txns).to_csv(out_dir / "transactions.csv", index=False)
        if trades:
            pd.DataFrame(trades, columns=["symbol", "entry_date", "entry_px", "shares",
                                          "exit_date", "exit_px", "pnl", "ret_pct",
                                          "bars_held", "open"]).to_csv(out_dir / "trade_ledger.csv", index=False)

    return res


SWEEP = [
    dict(label="base 200d (all-in)",      sma=200, second_sma=0,  partial=1.0),
    dict(label="200d + 50d gate",         sma=200, second_sma=50, partial=1.0),
    dict(label="200d + 50d + 3d confirm", sma=200, second_sma=50, partial=1.0, confirm_days=3),
    dict(label="200d, 2% buffer, 3d cf",  sma=200, second_sma=0,  partial=1.0, buffer_pct=2.0, confirm_days=3),
    dict(label="200d partial 0.66 (~2x)", sma=200, second_sma=0,  partial=0.66),
    dict(label="200d partial 0.5 (~1.5x)",sma=200, second_sma=0,  partial=0.5),
    dict(label="200d+50d partial 0.66",   sma=200, second_sma=50, partial=0.66),
    dict(label="200d+50d p0.66 BIL",      sma=200, second_sma=50, partial=0.66, riskoff="bil"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to",   dest="end",   default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--lev", default="TQQQ")
    ap.add_argument("--index", default="QQQ")
    ap.add_argument("--sma", type=int, default=200)
    ap.add_argument("--second-sma", type=int, default=0)
    ap.add_argument("--partial", type=float, default=1.0)
    ap.add_argument("--buffer-pct", type=float, default=0.0)
    ap.add_argument("--confirm-days", type=int, default=1)
    ap.add_argument("--target-vol", type=float, default=0.0, help="annualized vol target %% (0=off); scales exposure down when vol spikes")
    ap.add_argument("--riskoff", choices=["cash", "bil"], default="cash")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true", help="Run the preset DD-reduction grid + print a table")
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)

    if a.sweep:
        rows = []
        for cfg in SWEEP:
            r = run(s, e, a.capital, lev=a.lev, index_sym=a.index, quiet=True, **cfg)
            rows.append(r)
        b = rows[0]["bench_buyhold_lev"]; bi = rows[0]["bench_buyhold_index"]
        print(f"\n=== {a.lev} regime sweep  ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<28} {'CAGR%':>8} {'MaxDD%':>8} {'Calmar':>7} {'Switch':>7} {'TIM%':>6}")
        print("-" * 70)
        for r in rows:
            print(f"{r['label']:<28} {r['cagr_pct']:>8.2f} {r['max_dd_pct']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['switches']:>7} {r['time_in_market_pct']:>6.1f}")
        print("-" * 70)
        print(f"{'buy-hold '+a.lev:<28} {b['cagr_pct']:>8.2f} {b['max_dd_pct']:>8.2f}")
        print(f"{'buy-hold '+a.index:<28} {bi['cagr_pct']:>8.2f} {bi['max_dd_pct']:>8.2f}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, lev=a.lev, index_sym=a.index, sma=a.sma,
            second_sma=a.second_sma, partial=a.partial, buffer_pct=a.buffer_pct,
            confirm_days=a.confirm_days, target_vol=a.target_vol, riskoff=a.riskoff,
            out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()
