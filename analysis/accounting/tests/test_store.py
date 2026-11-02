"""Store tests. Only a fictional company and invented numbers are used."""
import logging
import os
import sqlite3
import stat

import pytest

from accounting.store import AccessDenied, AccountingStore, StoreError
from accounting.store.backup import backup
from accounting.store.db import from_ore, to_ore

SENTINEL = "ZQX-SECRET-DESC-7781"


@pytest.fixture
def store(tmp_path):
    s = AccountingStore(tmp_path / "acc.db")
    yield s
    s.close()


def _setup(store, user, org, name="Testfirma Fiktiv AS"):
    cid = store.create_company(user, org, name, is_test=True)
    store.upsert_accounts(user, cid, [
        {"account_id": "1920", "description": "Bank", "grouping_category": "1", "grouping_code": "19"},
        {"account_id": "3000", "description": "Salg", "grouping_category": "3", "grouping_code": "30"},
    ])
    store.upsert_tax_codes(user, cid, [{"tax_code": "3", "description": "Utg. mva", "standard_tax_code": "3"}])
    return cid


def _entry(tid="T1", debit="1250.00", credit="1250.00", desc="Salg"):
    return {"transaction_id": tid, "period": "01", "period_year": "2027", "transaction_date": "2027-01-05",
            "description": desc, "system_entry_date": "2027-01-05", "gl_posting_date": "2027-01-05",
            "lines": [{"account_id": "1920", "debit": debit}, {"account_id": "3000", "credit": credit}]}


def test_post_and_trial_balance(store):
    cid = _setup(store, "u1", "999000001")
    store.post_entry("u1", cid, _entry())
    assert store.trial_balance("u1", cid) == {"1920": 125000, "3000": -125000}
    assert from_ore(125000) == from_ore(to_ore("1250.00"))


def test_unbalanced_and_bad_amounts_rejected(store):
    cid = _setup(store, "u1", "999000001")
    for bad in (_entry(credit="1249.99"), _entry(debit="0"), _entry(debit="10.001", credit="10.001")):
        with pytest.raises(StoreError):
            store.post_entry("u1", cid, bad)
    assert store.list_entries("u1", cid) == []


def test_unknown_account_and_duplicate_transaction_rejected(store):
    cid = _setup(store, "u1", "999000001")
    e = _entry()
    e["lines"][0]["account_id"] = "9999"
    with pytest.raises(StoreError):
        store.post_entry("u1", cid, e)
    store.post_entry("u1", cid, _entry())
    with pytest.raises(StoreError):
        store.post_entry("u1", cid, _entry())


def test_users_only_reach_their_own_company(store):
    a = _setup(store, "alice", "999000001")
    b = _setup(store, "bob", "999000002", "Annen Fiktiv AS")
    store.post_entry("alice", a, _entry())
    assert [c["id"] for c in store.list_companies("alice")] == [a]
    assert [c["id"] for c in store.list_companies("bob")] == [b]
    for call in (lambda: store.list_entries("bob", a), lambda: store.list_accounts("bob", a),
                 lambda: store.trial_balance("bob", a), lambda: store.post_entry("bob", a, _entry("T2")),
                 lambda: store.upsert_accounts("bob", a, [])):
        with pytest.raises(AccessDenied):
            call()
    # a company that does not exist gives the same answer as one that is not yours
    with pytest.raises(AccessDenied, match="no access"):
        store.list_entries("bob", 9999)


def test_rows_cannot_cross_companies_even_via_sql(store):
    a = _setup(store, "alice", "999000001")
    b = store.create_company("bob", "999000002", "Annen Fiktiv AS", is_test=True)  # bob has no accounts
    store.post_entry("alice", a, _entry())
    with pytest.raises(sqlite3.IntegrityError):  # composite FK: bob's line cannot use alice's account
        store._conn.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (b, 1, "X", "01", "2027", "2027-01-01", "d", "2027-01-01", "2027-01-01", "manual"))
        store._conn.execute("INSERT INTO lines VALUES(?,?,?,?,?,?,?)", (b, 1, "1", "1920", "d", 100, None))


def test_roles(store):
    cid = _setup(store, "owner1", "999000001")
    store.add_member("owner1", cid, "view1", "viewer")
    store.add_member("owner1", cid, "acc1", "accountant")
    assert store.list_entries("view1", cid) == []
    with pytest.raises(AccessDenied):
        store.post_entry("view1", cid, _entry())
    store.post_entry("acc1", cid, _entry())
    with pytest.raises(AccessDenied):
        store.add_member("acc1", cid, "x", "viewer")


def test_posted_entries_are_immutable(store):
    cid = _setup(store, "u1", "999000001")
    store.post_entry("u1", cid, _entry())
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("UPDATE lines SET amount_ore=1 WHERE company_id=?", (cid,))
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("UPDATE entries SET description='x' WHERE company_id=?", (cid,))


def test_no_accounting_data_in_logs_or_errors(store, caplog):
    caplog.set_level(logging.DEBUG)
    cid = store.create_company("u1", "999000001", SENTINEL, is_test=True)
    store.upsert_accounts("u1", cid, [{"account_id": "1920", "description": SENTINEL,
                                       "grouping_category": "1", "grouping_code": "19"},
                                      {"account_id": "3000", "description": SENTINEL,
                                       "grouping_category": "3", "grouping_code": "30"}])
    store.post_entry("u1", cid, _entry(desc=SENTINEL, debit="777.77", credit="777.77"))
    with pytest.raises(StoreError) as ei:
        store.post_entry("u1", cid, _entry("T2", debit="777.77", credit="1.00", desc=SENTINEL))
    with pytest.raises(StoreError) as ej:
        store.post_entry("u1", cid, _entry(desc=SENTINEL, debit="777.77", credit="777.77"))
    blob = caplog.text + str(ei.value) + str(ej.value)
    for secret in (SENTINEL, "777.77", "77777", "1920", "999000001"):
        assert secret not in blob


def test_db_file_permissions(tmp_path):
    s = AccountingStore(tmp_path / "x" / "acc.db")
    assert stat.S_IMODE(os.stat(tmp_path / "x" / "acc.db").st_mode) == 0o600
    s.close()


def test_backup_is_consistent_rotated_and_private(store, tmp_path):
    cid = _setup(store, "u1", "999000001")
    store.post_entry("u1", cid, _entry())
    dest = tmp_path / "bk"
    made = [backup(store.path, dest, keep=2) for _ in range(4)]
    assert len(list(dest.glob("accounting-*.db"))) == 2
    assert stat.S_IMODE(os.stat(made[-1]).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(dest).st_mode) == 0o700
    restored = AccountingStore(made[-1])
    assert restored.trial_balance("u1", cid) == {"1920": 125000, "3000": -125000}
    restored.close()
