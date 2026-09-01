from audit_store import AuditStore


def test_paper_account_is_server_owned_and_not_resettable(tmp_path):
    store = AuditStore(str(tmp_path / "audit.sqlite3"))

    first = store.ensure_paper_account(user_id="user-a", initial_cash=100_000_000)
    second = store.ensure_paper_account(user_id="user-a", initial_cash=999_000_000)

    assert first["initialCash"] == 100_000_000.0
    assert first["cashBalance"] == 100_000_000.0
    assert second["initialCash"] == 100_000_000.0
    assert second["cashBalance"] == 100_000_000.0
    assert second["positions"] == []


def test_paper_accounts_are_isolated_by_user(tmp_path):
    store = AuditStore(str(tmp_path / "audit.sqlite3"))

    account_a = store.ensure_paper_account(user_id="user-a", initial_cash=100_000_000)
    account_b = store.ensure_paper_account(user_id="user-b", initial_cash=200_000_000)

    assert account_a["userId"] == "user-a"
    assert account_b["userId"] == "user-b"
    assert store.get_paper_account(user_id="missing") is None


def test_ai_dry_run_decision_is_persisted_with_risk_and_event(tmp_path):
    store = AuditStore(str(tmp_path / "audit.sqlite3"))
    proposal = {
        "code": "فولاد",
        "horizon": "short",
        "action": "BUY",
        "confidence": 0.55,
        "positionPct": 2.5,
        "thesis": "verified-data thesis",
        "risks": ["market closed"],
        "model": "test-model",
        "executionAllowed": False,
    }
    risk = {
        "allowed": False,
        "reasons": ["TSE is closed"],
        "checks": {"marketSessionOpen": False},
    }
    result = {
        "allowed": False,
        "reasons": ["TSE is closed"],
        "proposal": proposal,
        "risk": risk,
        "intent": None,
        "receipt": None,
        "paperExecution": False,
        "liveExecution": False,
        "dryRun": True,
    }

    decision_id = store.save_kiasha_ai_decision(
        user_id="user-a",
        code="فولاد",
        horizon="short",
        proposal=proposal,
        risk=risk,
        result=result,
        reference_price=2698.0,
        reference_source="verified-market-quote",
        dry_run=True,
    )

    decisions = store.list_kiasha_ai_decisions(user_id="user-a")
    events = store.list_events(user_id="user-a")

    assert len(decisions) == 1
    assert decisions[0]["decisionId"] == decision_id
    assert decisions[0]["proposal"]["action"] == "BUY"
    assert decisions[0]["risk"]["allowed"] is False
    assert decisions[0]["referencePrice"] == 2698.0
    assert decisions[0]["dryRun"] is True
    assert events[0]["eventType"] == "KIASHA_AI_PAPER_DRY_RUN"
    assert events[0]["payload"]["decisionId"] == decision_id
