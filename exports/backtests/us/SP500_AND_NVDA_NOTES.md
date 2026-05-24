# S&P 500 port + NVDA-exclusion stress (notes)

Two diagnostics on the locked momentum book. Models gained `--universe-csv` and
`--regime-sym` flags so they run on any universe + regime index.

## 1. Same book on S&P 500 (universe = sp500.csv, regime = SPY; UPRO = 3× S&P sleeve)

| | S&P 3yr | Nasdaq 3yr | S&P 10yr | Nasdaq 10yr |
|---|--------:|-----------:|---------:|------------:|
| Book CAGR | 87.7% | **108.7%** | 37.7% | **55.2%** |
| Book MaxDD | 30.1% | **24.9%** | 38.9% | **37.7%** |
| Book Calmar | 2.91 | **4.36** | 0.97 | **1.46** |

Sleeves (S&P): MOM 3yr 169.7%/45.1% · 10yr 53.3%/52.6% ; UPRO 3yr 44.5%/28.6% ·
10yr 21.1%/53.6% ; BRK 3yr 38.3%/38.0% · 10yr 22.9%/27.5%.

**Finding:** the Nasdaq book beats the S&P book on every metric, both windows.
Momentum/trend is a Nasdaq edge (tech concentration + dispersion); S&P diversification
dilutes it. S&P MOM 3yr CAGR (170%) tops Nasdaq MOM (163%) but is far worse over 10yr
(higher variance). No S&P config beats the locked Nasdaq book. (Sector-rotation / low-vol
would suit S&P but are low-CAGR — see US_3MODEL_RESULTS.md scan.)

## 2. Nasdaq book excluding NVDA (survivorship single-name stress)

| | 3yr CAGR/DD/Calmar | 10yr CAGR/DD/Calmar |
|---|--------------------|---------------------|
| With NVDA | 108.7 / 24.9 / 4.36 | 55.2 / 37.7 / 1.46 |
| **Ex-NVDA** | 90.9 / 26.2 / 3.47 | 50.6 / 38.8 / 1.31 |
| NVDA contribution | +17.8pp CAGR | **+4.6pp CAGR** |

Sleeves ex-NVDA: MOM 3yr 146.8%/39.2% · 10yr 72.2%/47.5% ; BRK 3yr 42.6%/21.2% ·
10yr 24.5%/38.5% (BRK leaned on NVDA more — 66→43 on 3yr).

**Finding:** NVDA was a boost, not the engine. Remove it and the 10yr book still does
50.6% (vs 55.2%) — momentum rotates into whatever's trending (AMD/AVGO/SMCI...), so the
edge is breadth, not one name. Caveat: ex-NVDA is still survivorship-biased (the other
current-N100 names are also survivors); the truly-clean number needs point-in-time data.

Artifacts: `sp500_book/{3yr,10yr}/`, `exnvda/{3yr,10yr}/`, `src/data/symbols/sp500.csv`,
`src/data/symbols/nasdaq100_no_nvda.csv`.
