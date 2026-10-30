import json

from analytics.shadow_system_report import (
    build_shadow_system_report,
    persist_shadow_system_report,
    render_shadow_system_markdown,
)


def _system(path):
    return {
        "id": "sample-system",
        "name": "Sample system",
        "category": "decision_candidate",
        "enabled": True,
        "live_enabled": False,
        "path": str(path),
        "record_type": None,
        "outcome_source": "outcome",
        "decision_candidate": True,
        "note": "test",
    }


def test_review_thresholds_count_unique_resolved_outcomes_only(tmp_path):
    log_path = tmp_path / "shadow.jsonl"
    records = [
        {"signal_id": f"trade-{index}", "outcome": "WIN"}
        for index in range(100)
    ]
    records.extend([
        {"signal_id": "trade-0", "outcome": "WIN"},
        {"signal_id": "pending", "outcome": "PENDING"},
        {"signal_id": "hb-old", "outcome": "PENDING"},
        {"signal_id": "virtual", "status": "FILLED"},
    ])
    log_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    report = build_shadow_system_report(systems=[_system(log_path)])
    system = report["systems"][0]

    assert system["log_records"] == 104
    assert system["distinct_resolved_outcome_cases"] == 100
    assert system["distinct_actual_pnl_samples"] == 0
    assert system["pending_records"] == 2
    assert system["pending_outcome_records"] == 2
    assert system["distinct_pending_outcome_ids"] == 1
    assert system["recommendation"] == "FIRST_REVIEW_REQUIRED_AT_100"
    assert system["win_rate_excluding_timeouts"] == 1.0
    assert report["policy"]["live_changes_automatic"] is False


def test_200_resolved_trades_requires_human_decision(tmp_path):
    log_path = tmp_path / "shadow.jsonl"
    log_path.write_text(
        "\n".join(
            json.dumps({"decision_id": f"trade-{i}", "outcome": "LOSS"})
            for i in range(200)
        ),
        encoding="utf-8",
    )

    system = build_shadow_system_report(systems=[_system(log_path)])["systems"][0]

    assert system["recommendation"] == "DECISION_REQUIRED_LINK_ACTUAL_RESULTS_OR_REMOVE"
    assert system["live_enabled"] is False
    assert system["win_rate_excluding_timeouts"] == 0.0
    assert system["actual_win_rate"] is None


def test_200_actual_pnl_outcomes_requires_explicit_human_decision(tmp_path):
    log_path = tmp_path / "shadow.jsonl"
    log_path.write_text(
        "\n".join(
            json.dumps({
                "decision_id": f"trade-{i}",
                "outcome": "WIN",
                "actual_profit": 1.0,
            })
            for i in range(200)
        ),
        encoding="utf-8",
    )

    system = build_shadow_system_report(systems=[_system(log_path)])["systems"][0]

    assert system["recommendation"] == "DECISION_REQUIRED_PROMOTE_TO_DEMO_OR_REMOVE"
    assert system["distinct_actual_pnl_samples"] == 200
    assert system["actual_win_rate"] == 1.0
    assert system["actual_net_pnl"] == 200.0
    assert system["actual_profit_factor_unbounded"] is True


def test_conflicting_outcomes_for_same_id_are_excluded(tmp_path):
    log_path = tmp_path / "shadow.jsonl"
    log_path.write_text(
        "\n".join([
            json.dumps({"signal_id": "same", "outcome": "WIN"}),
            json.dumps({"signal_id": "same", "outcome": "LOSS"}),
        ]),
        encoding="utf-8",
    )

    system = build_shadow_system_report(systems=[_system(log_path)])["systems"][0]

    assert system["distinct_resolved_outcome_cases"] == 0
    assert system["conflicting_outcome_ids"] == 1
    assert system["win_rate_excluding_timeouts"] is None


def test_candidate_ids_deduplicate_and_link_cost_complete_actual_pnl(tmp_path):
    log_path = tmp_path / "shadow.jsonl"
    events_path = tmp_path / "trade_events.jsonl"
    candidate_id = "candidate-1"
    log_path.write_text(
        "\n".join(
            json.dumps({
                "candidate_id": candidate_id,
                "signal_id": f"heartbeat-{index}",
                "outcome": "WIN",
            })
            for index in range(2)
        ) + "\n",
        encoding="utf-8",
    )
    events_path.write_text(
        "\n".join([
            json.dumps({
                "event_type": "DECISION",
                "correlation_id": "decision-1",
                "candidate_id": candidate_id,
            }),
            json.dumps({
                "event_type": "TRADE_CLOSED",
                "correlation_id": "decision-1",
                "entry_cost_complete": True,
                "total_position_net_profit": 5.25,
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    system = build_shadow_system_report(
        systems=[_system(log_path)],
        actual_events_path=str(events_path),
    )["systems"][0]

    assert system["distinct_resolved_outcome_cases"] == 1
    assert system["distinct_actual_pnl_samples"] == 1
    assert system["actual_net_pnl"] == 5.25
    assert system["actual_win_rate"] == 1.0


def test_entry_controller_counts_only_paired_candidate_comparisons(tmp_path):
    log_path = tmp_path / "entry_plans.jsonl"
    records = [
        {
            "candidate_id": "filled",
            "entry_outcome": "WIN",
            "baseline_outcome": "LOSS",
        },
        {
            "candidate_id": "not-filled",
            "entry_outcome": "NOT_FILLED",
            "baseline_outcome": "WIN",
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    system_spec = _system(log_path)
    system_spec["outcome_source"] = "entry_outcome"
    system_spec["comparison_outcome_source"] = "baseline_outcome"
    system = build_shadow_system_report(systems=[system_spec])["systems"][0]

    assert system["distinct_resolved_outcome_cases"] == 1
    assert system["distinct_comparison_outcome_cases"] == 2
    assert system["paired_comparison_outcome_cases"] == 1


def test_heartbeat_ids_are_not_review_samples(tmp_path):
    log_path = tmp_path / "legacy.jsonl"
    log_path.write_text(
        json.dumps({"signal_id": "hb-2026-10-30T09:00:00+00:00", "outcome": "WIN"}) + "\n",
        encoding="utf-8",
    )

    system = build_shadow_system_report(systems=[_system(log_path)])["systems"][0]

    assert system["distinct_resolved_outcome_cases"] == 0
    assert system["unstable_identity_records"] == 1


def test_heartbeat_row_with_closed_bar_time_gets_stable_candidate_identity(tmp_path):
    log_path = tmp_path / "legacy_bar.jsonl"
    log_path.write_text(
        json.dumps({
            "signal_id": "hb-legacy",
            "symbol": "XAUUSD",
            "strategy": "SMC",
            "direction": "BUY",
            "decision_bar_time": "2026-10-30T09:00:00+00:00",
            "outcome": "WIN",
        }) + "\n",
        encoding="utf-8",
    )

    system = build_shadow_system_report(systems=[_system(log_path)])["systems"][0]

    assert system["distinct_resolved_outcome_cases"] == 1
    assert system["unstable_identity_records"] == 0


def test_monitoring_cycles_are_not_trade_samples_and_missing_logs_are_visible(tmp_path):
    log_path = tmp_path / "monitor.jsonl"
    log_path.write_text(
        json.dumps({"timestamp": "t1", "status": "OK"}) + "\n",
        encoding="utf-8",
    )
    monitor = _system(log_path)
    monitor.update(
        id="monitor",
        decision_candidate=False,
        outcome_source=None,
    )
    missing = _system(tmp_path / "missing.jsonl")
    missing["id"] = "missing"

    reports = build_shadow_system_report(systems=[monitor, missing])["systems"]

    assert reports[0]["distinct_resolved_outcome_cases"] == 0
    assert reports[0]["recommendation"] == "KEEP_OR_REMOVE_AS_MONITORING"
    assert reports[1]["recommendation"] == "CHECK_LOGGING_WIRING"


def test_persists_json_and_markdown_report(tmp_path, monkeypatch):
    log_path = tmp_path / "shadow.jsonl"
    log_path.write_text(
        json.dumps({"signal_id": "one", "outcome": "LOSS"}) + "\n",
        encoding="utf-8",
    )
    import core.settings as settings

    monkeypatch.setattr(settings, "SHADOW_COUNTERFACTUAL_LOG_PATH", str(log_path))
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    report = persist_shadow_system_report(
        json_path=str(json_path),
        markdown_path=str(markdown_path),
    )

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert saved["summary"]["system_count"] == report["summary"]["system_count"]
    assert "First mandatory review" in markdown
    assert render_shadow_system_markdown(report) == markdown
