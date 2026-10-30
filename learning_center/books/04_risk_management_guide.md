# Risk Management — Practical Guide

## ملخص سريع (عربي)
إدارة رأس المال هي العامل الأهم في بقاء أي متداول على المدى الطويل، أكثر من دقة استراتيجية الدخول نفسها. القاعدة الذهبية: تحديد نسبة مخاطرة ثابتة وصغيرة من رأس المال لكل صفقة (عادة 0.5%-2%)، وضع حد أقصى للخسارة اليومي/الأسبوعي يوقف التداول تلقائيًا عند بلوغه، والتفكير بالعائد على المخاطرة (R-multiple) بدلاً من الأرباح المطلقة.

---

## 1. Position Sizing
- **Fixed fractional risk:** risk a fixed percentage of account equity per trade (commonly 0.5%–2% for discretionary trading; often lower for higher-frequency or higher-leverage systems). This automatically scales position size down after losses and up after gains, which smooths the equity curve compared to fixed lot sizes.
- **Formula:** `position size = (account equity × risk %) / (stop-loss distance in price × contract value per point)`.
- **Volatility-adjusted sizing:** using ATR (or similar) to set stop distance means the same risk % translates to a smaller position in high-volatility conditions and a larger position in low-volatility conditions — this keeps dollar risk consistent even as market conditions change.

## 2. R-Multiples (Thinking in Risk Units)
- Define **1R** as the dollar (or percentage) amount risked on a trade (entry to stop-loss distance).
- Express every trade's outcome as a multiple of R (e.g., "+2R", "-1R") rather than in raw currency — this makes performance comparable across different position sizes and account sizes.
- A strategy's long-run expectancy = `(win rate × average winning R) − (loss rate × average losing R)`. A system can be profitable with a win rate under 50% if average winners are sufficiently larger than average losers, and unprofitable with a win rate over 50% if losers are allowed to run larger than winners.

## 3. Daily / Weekly Loss Limits
- Setting a hard maximum loss (e.g., -3% to -5% of equity in a day, -8% to -10% in a week) that triggers an automatic stop to trading for that period is a common discipline tool to prevent a single bad session from spiraling via emotional decision-making.
- This is distinct from a single trade's stop-loss — it caps the *cumulative* damage from a string of losses or from revenge trading after a loss.

## 4. Reward-to-Risk Expectations
- Reward-to-risk ratio (RRR) describes the *planned* target relative to the *planned* stop, decided before entry — not a guarantee of the outcome.
- A common mistake is choosing an RRR that is structurally incompatible with the strategy's realistic win rate for the setup being traded (e.g., demanding a 1:5 RRR on a setup that historically reverses at the first sign of resistance, well short of that target).
- Partial profit-taking (closing a portion of the position at a nearer target, moving the stop to break-even, and letting the remainder run) is a common way to bank some R while preserving upside participation.

## 5. Correlation & Concentration Risk
- Holding multiple simultaneous positions that are highly correlated (e.g., long gold and long silver at the same time, or multiple USD pairs all betting on dollar weakness) effectively multiplies the real risk taken beyond what each individual position's stated risk % suggests.
- Being aware of net directional exposure across all open positions (not just per-trade risk) is important when running more than one setup or strategy concurrently — this is directly relevant to a multi-strategy system that runs several "agents" simultaneously.

## 6. Drawdown Recovery Math
- A loss requires a disproportionately larger gain to recover: a 20% drawdown requires a 25% gain to recover; a 50% drawdown requires a 100% gain. This asymmetry is the mathematical justification for prioritizing capital preservation over any single trade's upside.
- Increasing risk per trade *after* a drawdown to "win it back faster" (a common emotional response) mathematically increases the probability of ruin rather than reducing it.

## 7. Practical Checklist Before Every Trade
1. What is my stop-loss level, and does the resulting position size keep risk within my fixed %?
2. Have I hit my daily/weekly loss limit already?
3. Does this trade correlate strongly with any position I already hold?
4. Is my target realistic given how this setup has behaved historically, not just what I hope will happen?
5. Am I sizing based on conviction/emotion, or based on the fixed rule?

## Important Caveat
No risk-management framework eliminates the possibility of loss; it only shapes the *distribution* of outcomes to favor long-term survival and consistency. Position sizing formulas here are educational illustrations, not personalized financial advice — actual risk tolerance, account size, and regulatory/broker constraints vary per individual.
