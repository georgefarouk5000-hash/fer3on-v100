# Risk Policy

## Core Rules
- Never risk more than the configured daily and weekly drawdown limits.
- Reduce exposure immediately when signal quality or production readiness drops.
- Avoid trading during unsafe market or news conditions.
- Respect cooldowns, hard-risk caps, and execution pressure safeguards.
- Prefer smaller size or stand-by mode over forcing a weak setup.

## Monitoring
- Review the production dashboard on every trading session.
- Treat repeated degraded watchdog states as a stop condition until reviewed.
- Keep the automation gate closed whenever readiness criteria are not met.
- Reassess risk parameters after any major model, execution, or market regime change.

## Escalation
- Escalate to manual review if the watchdog reports repeated degraded states.
- Pause live trading immediately if safety rules are violated or confidence falls sharply.
