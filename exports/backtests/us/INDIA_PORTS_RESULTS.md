# India models ported to US Nasdaq — results

Ran the three India model **selection rules** on US data (`tools/models/india_ports_us/backtest.py`)
to "see for US". Same daily mark-to-market engine as the US v2 book (true peak-to-trough DD,
8 bps slippage). Static current Nasdaq universes (survivorship-accepted; US has no point-in-time
membership data, unlike India's PIT `eligible_at`).

| Model | Concentration | Universe |
|---|---|---|
| emerging_momentum | 1 name (rotate on top-3 drop) | top-100 ADV of (nasdaq500 − nasdaq100) = mids |
| momentum_retest_n500 | 2 names (hold top-4) | top-120 ADV of nasdaq500, near 20-EMA |
| n40_large_weekly | 1 name, weekly | top-40 ADV ∩ nasdaq100 large caps |

## 5.2yr (2021-03-01 → 2026-05-22)
| Model | CAGR | TrueDD | Calmar |
|---|---|---|---|
| emerging (no gate) | 16.3% | 81.6% | 0.20 |
| emerging (QQQ 200d gate) | 15.8% | 79.6% | 0.20 |
| retest (gate) | −9.3% | 87.6% | −0.11 |
| n40 large weekly (gate) | 20.0% | 62.3% | 0.32 |

## 3yr (2023-05-24 → 2026-05-22, bull)
| Model | CAGR | TrueDD | Calmar |
|---|---|---|---|
| emerging (gate) | 51.4% | 74.7% | 0.69 |
| retest (gate) | 14.9% | 71.7% | 0.21 |
| n40 large weekly (gate) | 66.2% | 54.9% | 1.21 |

## Verdict
**These do NOT translate to US.** The drawdowns are real (verified price-path bleeds, not
glitches — e.g. emerging peak $1.39M 2021-11 → trough $283k 2023-11; worst single trade −53%),
driven by **1–2 name concentration** on a far more speculative US mid/small pool (recent volatile
IPOs: PSKY, VFS, SMMT, SMCI…). The QQQ 200d gate barely helps (81.6%→79.6%) because monthly/weekly
rebalances still re-enter on bear rallies.

The US edge is the **diversified top-3 book** (v2: 10yr 53% CAGR / 38% DD), NOT concentration.
n40 (large-cap top-1 weekly) is the least-bad concentrated variant (62% DD / 20% CAGR 5yr) but
still ~2× the book's DD. Recommendation: keep the locked v2 book; do not adopt these as sleeves.
Concentration is the wrong lever for US; the mapped frontier says US high-CAGR needs diversified
momentum + a low-correlation diversifier, not single-name rotation.
