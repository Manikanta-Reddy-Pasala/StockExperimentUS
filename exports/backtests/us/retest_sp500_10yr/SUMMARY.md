# retest_sp500 — 10-year backtest (spliced yfinance + eToro)

WEEKLY retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d
regime gate. REALISTIC US execution (next-open fills + T+1 settlement, $1/txn).

**Data:** continuous 10-year series built by ratio-splicing real yfinance history
(`data_source='yfinance_real'`, 2016-06-01 → 2021-05-28) onto the eToro feed
(`data_source='yfinance'`, 2021-06-01 →) per symbol at **join 2021-06-01** (adjacent
boundary anchor; auto-corrects the constant-scaled NFLX/BKNG). Pre-join fills use the
spliced close (open backfill not spliced — documented limitation). Regime symbol QQQ
backfilled so the 200d gate is active pre-2021.

| Metric | Value |
|---|---:|
| Window | 2016-06-01 → 2026-06-18 (10.05y) |
| Final NAV ($1,000,000 start) | $17,165,552 |
| CAGR | +32.71% |
| MaxDD (true daily) | 49.71% |
| Calmar | 0.66 |
| Trades | 72 (45 pre-2021) |
| Win rate | 56.9% |

Seam continuity verified: max |daily return| across the 2021-06-01 join is 1.24% (AAPL)
and 0.31% (NFLX) — no phantom jump. Splice statuses: ok=165, only_new=287 (no pre-2021
backfill, recent-era only), only_old=1, bad_ratio=1 (FOX — junk feed, left unscaled).

Reproduce (on the NUC, against the exposed DB):
```
PYTHONPATH=. python tools/models/india_ports_us/backtest.py --model retest --extended \
  --join 2021-06-01 --membership-csv src/data/symbols/sp500_membership.csv \
  --signal blend --regime --from 2016-06-01 --to 2026-06-18 --out <dir>
```
Backfill first: `tools/pull_yfinance_history.py --membership src/data/symbols/sp500_membership.csv --start 2016-06-01 --end 2021-05-31` (plus QQQ/SPY for the regime gate).
