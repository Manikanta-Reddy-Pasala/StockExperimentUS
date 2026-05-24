# $5,000 Book — Backtest Summary + Transaction Ledgers

Locked 3-model book (v2) run at **$5,000 starting capital**, split 45/15/40 into three
independent buckets (each sleeve manages its own cash, no cross-sleeve rebalancing —
"let the buckets run"). Fractional shares (IBKR supports). Costs: $0 commission + 8 bps
slippage. True daily MTM drawdown.

| Sleeve | Bucket | Live config | Rebalance cadence |
|--------|-------:|-------------|-------------------|
| MOM | $2,250 (45%) | `--top 3 --regime --mom-mode blend` | monthly (1st trading day); cash when QQQ<200d |
| TQQQ | $750 (15%) | `--sma 200` | daily regime check; switch on QQQ 200d cross |
| BRK | $2,000 (40%) | `--donchian 50 --trail 20 --maxn 5 --regime` | event-driven: breakout entry, 20% trailing-stop exit |

## Results — $5,000 grows to

### Last 3 years (2023-05-24 → 2026-05-22)
| Sleeve | Start | Final | CAGR | MaxDD | Txns |
|--------|------:|------:|-----:|------:|-----:|
| MOM | $2,250 | $40,700 | 162.9% | 39.2% | 144 |
| TQQQ | $750 | $3,544 | 67.9% | 37.4% | 5 |
| BRK | $2,000 | $9,183 | 66.3% | 25.5% | 82 |
| **TOTAL** | **$5,000** | **$53,427** | **~120%** | — | 231 |

### Last 10 years (2016-05-24 → 2026-05-22)
| Sleeve | Start | Final | CAGR | MaxDD | Txns |
|--------|------:|------:|-----:|------:|-----:|
| MOM | $2,250 | $838,622 | 80.9% | 47.0% | 431 |
| TQQQ | $750 | $30,221 | 44.8% | 54.9% | 41 |
| BRK | $2,000 | $21,544 | 26.9% | 36.7% | 242 |
| **TOTAL** | **$5,000** | **$890,387** | **~68%** | — | 714 |

## Transaction ledgers (dates + prices + shares + value)
Per-sleeve `transactions.csv` — columns: `date, action, symbol, price, shares, value`.

- 3yr: `exports/backtests/us/book_5000_3yr/{mom,tqqq,brk}/transactions.csv`
- 10yr: `exports/backtests/us/book_5000/{mom,tqqq,brk}/transactions.csv`

Actions: `BUY` / `SELL` (MOM, BRK), `SELL_TRAIL` (MOM trailing stop if enabled),
`BUY_TQQQ` / `SELL_TQQQ` (TQQQ regime switches). Prices are split-adjusted.

Example (MOM, first rebalance 2016-05-24, $750/name across top-3):
```
date,action,symbol,price,shares,value
2016-05-24,BUY,NVDA,1.134,661.38,750.00
2016-05-24,BUY,AXON,21.86,34.31,750.00
2016-05-24,BUY,AMD,4.20,178.57,750.00
```

## Read this — the 10yr number is a survivorship mirage
The 10yr $890k is dominated by MOM's **$838k**, which is dominated by a single line:
**NVDA bought at $1.13 (split-adjusted) on 2016-05-24.** The current Nasdaq-100 universe
only contains NVDA *because* it became the decade's biggest winner — the backtest "knew"
to hold it. Real-world, you could not have known. **Discount the 10yr heavily.**

- **3yr (~120%) and 10yr (~68%)** are both survivorship + bull inflated.
- **Honest forward expectation: ~40-55% CAGR.**
- **DD:** these are *fixed-bucket* totals → as MOM compounds it dominates the book, so
  book DD drifts toward MOM's (~39-47%). The **daily-rebalanced blend** (`3MODEL_BOOK.md`,
  45/15/40 held constant) is the lower-DD way to run it: 3yr 24.9% DD, 10yr 37.7% DD, at
  somewhat lower CAGR. Choose: let-buckets-run (higher CAGR, MOM concentration creep) vs
  rebalanced (steadier, lower DD).
- At $5k, single MOM names can be $1,000+ share price (e.g. SNDK $1,187) — **fractional
  shares required**; IBKR supports them.

## Reproduce
```bash
export DATABASE_URL="postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system"
F=2023-05-24; T=2026-05-24; B=exports/backtests/us/book_5000_3yr
PYTHONPATH=. python3 tools/models/momentum_n100_regime_top3/backtest.py --top 3 --regime --mom-mode blend --capital 2250 --from $F --to $T --out $B/mom
PYTHONPATH=. python3 tools/models/leveraged_regime_tqqq/backtest.py --sma 200 --capital 750 --from $F --to $T --out $B/tqqq
PYTHONPATH=. python3 tools/models/breakout_n100/backtest.py --donchian 50 --trail 20 --maxn 5 --regime --capital 2000 --from $F --to $T --out $B/brk
```
