# Operational Runbook

## Objective
This runbook standardizes startup, health checks, reporting, and recovery steps for the trading system.

## Startup
1. Activate the project environment.
2. Ensure config.env is present and valid.
3. Run the main runtime entrypoint.
4. Confirm the watchdog reports healthy or degraded status.
5. Review the production dashboard and daily report before enabling live exposure.

## Health Checks
- Verify MT5 connection and market data availability.
- Verify memory, telemetry, and Telegram availability.
- Review the production dashboard and daily performance report.
- Confirm no unresolved safety gate blocks or hard-risk constraints.
- Run the regression suite after any major change.

## Recovery
- If the watchdog reports degraded status, inspect logs and recent exceptions.
- Reduce or suspend trading when signal quality or readiness drops below policy thresholds.
- Reset the runtime if the bot becomes unresponsive.
- Re-run the regression test suite before resuming live activity.

## Reporting
- Production dashboard: analytics/production_dashboard.md
- Daily report: analytics/daily_performance_report.md
- Production metrics history: analytics/production_metrics.json

## Deployment Checklist
- Confirm tests pass in CI.
- Review risk policy and current drawdown state.
- Verify configuration values in config.env.
- Keep automation disabled until health checks are green.
