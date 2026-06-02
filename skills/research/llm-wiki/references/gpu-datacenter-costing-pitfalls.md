# GPU Datacenter Investment Pricing Pitfalls

Lessons from building a Malaysia/Hengqin datacenter investment proposal (May 2026).

## Critical Pricing Traps

### 1. Per-Card vs Whole-Machine Pricing
**TRAP:** User gives a price like "$50万 for B300" — is this per GPU card or per 8-GPU DGX server?

**RESOLUTION:** Always clarify explicitly. Ask "Is this the 8-card DGX whole machine price, or per individual GPU card?" Don't assume.

### 2. System Components Not In Card Price
**TRAP:** A DGX server is NOT just 8×GPU cards. It includes:
- Dual Intel/AMD CPU (~$2万)
- NVSwitch module (~$1.5万)
- System memory 2TB (~$1万)
- NVMe storage 30TB (~$1万)
- 8×ConnectX-7 NICs (~$0.8万)
- Chassis/power/cooling (~$1.5万)

**Rule:** System components add **25-35%** to card-only cost.

**Example:** H200 cards $24万 → DGX H200 whole machine ~$36万

### 3. Market Price vs List Price
**TRAP:** User-provided prices may be outdated. B300 went from $50万 (early quote) to $70万 (market 2026).

**RESOLUTION:** Whenever possible, verify with web search for current market prices.

### 4. Rental Price Must Track Hardware Cost
**TRAP:** Using old rental prices ($2.50/h) after GPU price increases makes ROI unrealistic.

**Cost-plus pricing formula:**
```
Cost/GPU·h = (CardCost / (DepreciationYears × 365 × 24)) + PowerCost + OPEXAlloc
TargetRental = Cost/GPU·h / ((1 - Margin) × Utilization)
```

**May 2026 benchmarks:**
| GPU | Whole Machine | Cost/GPU·h | Market Rental |
|-----|:---:|:---:|:---:|
| H200 | $36万 | $1.36 | $2.50-3.50 |
| B300 | $70万 | $2.43 | $4.50-7.00 |

### 5. Token Pricing as Alternative Model
Token-based inference can yield 30-50% more revenue than hourly GPU rental at $1.00/1M tokens, but token prices are falling fast (DeepSeek effect). Mixed model recommended: rental for baseline + token for upside.

## Malaysia-Specific Parameters (Confirmed)
- Import tax: 8%
- Corporate tax: 24%
- SST: 7%
- Electricity: $0.12/kWh
- Colocation: $120-150/kW/month (small), ~$80/kW/month (>15MW)
- PUE: 1.6 (tropical, conservative)

## Hengqin/Macau-Specific Parameters
- Import tax: 0% (free port via Macau)
- Corporate tax: 15% (cooperation zone)
- VAT: 0%
- Electricity: ~$0.09/kWh
- Colocation: ~$100/kW/month
- PUE: 1.5 (cooler climate, newer build)
- ⚠️ GPU export control risk: must verify with NVIDIA before investment
