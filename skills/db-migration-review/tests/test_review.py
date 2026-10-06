#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "pytest>=8"]
# ///
"""Run with:  uv run tests/test_review.py   (from the skill directory)"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)

from liquibase_parser import classify_sql, split_sql, parse_file  # noqa: E402
from rules import build_context, run_rules  # noqa: E402


def review(*files: str, extra: list[str] | None = None) -> dict:
    cmd = [sys.executable, os.path.join(SCRIPTS, "review.py"), "--no-git", "--root", SKILL, "--format", "json",
           "--fail-on", "none", *(extra or []), *files]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=SKILL)
    return json.loads(out.stdout)


def rules_for(report: dict) -> set[str]:
    return {f["rule"] for f in report["findings"]}


def analyse_sql(sql: str, header: str = "") -> list:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as tmp:
        tmp.write("--liquibase formatted sql\n\n--changeset t:1 " + header + "\n" + textwrap.dedent(sql))
        path = tmp.name
    try:
        css = parse_file(path)
        ctx = build_context(css, {})
        return run_rules(css, ctx)
    finally:
        os.unlink(path)


# ----------------------------------------------------------------------------- parser

def test_split_respects_dollar_quotes_and_strings():
    sql = "DO $$ BEGIN PERFORM 1; END $$; UPDATE t SET a = 'x;y'; SELECT 1"
    assert len(split_sql(sql)) == 3


def test_classify_create_index_concurrently():
    st = classify_sql("CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix ON public.orders (a, b)")
    assert st.kind == "create_index" and st.attrs["concurrently"] and st.attrs["unique"]
    assert st.table == "orders" and st.columns == ["a", "b"] and st.index == "ix"


def test_classify_alter_forms():
    assert classify_sql("ALTER TABLE o ALTER COLUMN c SET NOT NULL").kind == "set_not_null"
    assert classify_sql("ALTER TABLE o DROP COLUMN c").kind == "drop_column"
    assert classify_sql("ALTER TABLE o RENAME COLUMN a TO b").kind == "rename_column"
    assert classify_sql("ALTER TABLE o RENAME TO p").kind == "rename_table"
    fk = classify_sql("ALTER TABLE o ADD CONSTRAINT fk FOREIGN KEY (x) REFERENCES p (id) NOT VALID")
    assert fk.kind == "add_fk" and fk.attrs["not_valid"] and fk.constraint == "fk"
    uq = classify_sql("ALTER TABLE o ADD CONSTRAINT u UNIQUE USING INDEX u_idx")
    assert uq.kind == "add_unique" and uq.attrs["using_index"]
    ty = classify_sql("ALTER TABLE o ALTER COLUMN c TYPE text")
    assert ty.kind == "alter_column_type" and ty.attrs["new_type"] == "text"
    assert classify_sql("ALTER TABLE o VALIDATE CONSTRAINT fk").kind == "validate_constraint"


def test_classify_add_column_defaults():
    st = classify_sql("ALTER TABLE o ADD COLUMN c uuid DEFAULT gen_random_uuid() NOT NULL")
    assert st.kind == "add_column" and st.attrs["default_volatile"] and st.attrs["not_null"]
    st = classify_sql("ALTER TABLE o ADD COLUMN c timestamptz DEFAULT now()")
    assert not st.attrs["default_volatile"]


def test_classify_misc():
    assert classify_sql("SET lock_timeout = '3s'").kind == "set_lock_timeout"
    assert classify_sql("VACUUM FULL orders").kind == "vacuum_full"
    assert classify_sql("REINDEX INDEX CONCURRENTLY ix").attrs["concurrently"]
    assert classify_sql("UPDATE o SET a = 1").attrs["has_where"] is False
    assert classify_sql("SELECT pg_sleep(1)").kind == "select"


# ----------------------------------------------------------------------------- rules on fixtures

def test_bad_fixtures_block():
    r = review("fixtures/bad/orders-shipping.xml", "fixtures/bad/audit-index.sql", "fixtures/bad/mixed.yaml")
    assert r["verdict"] == "BLOCK"
    assert {"PG-IDX-001", "PG-IDX-002", "BG-CONTRACT-002", "BG-CONTRACT-003", "PG-LOCK-004", "PG-LOCK-006",
            "PG-REWRITE-001", "PG-MAINT-001", "PG-LOCK-001", "PG-UNIQ-001", "PG-DML-001", "LB-TXN-001",
            "LB-ROLLBACK-001"} <= rules_for(r)
    # index on a table created in the same file is cold: no PG-IDX-001 for invoice_notes
    assert not any(f["rule"] == "PG-IDX-001" and f["table"] == "invoice_notes" for f in r["findings"])
    # lock_timeout findings are merged per file
    assert sum(1 for f in r["findings"] if f["rule"] == "PG-LOCK-001") == 2


def test_good_fixtures_pass():
    r = review("fixtures/good/safe-expand.xml", "fixtures/good/safe-data.sql")
    assert r["verdict"] == "SAFE", r["findings"]
    assert r["counts"] == {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    assert len(r["passed"]) == 7


def test_exit_code_threshold():
    cmd = [sys.executable, os.path.join(SCRIPTS, "review.py"), "--no-git", "--root", SKILL,
           "fixtures/bad/orders-shipping.xml"]
    assert subprocess.run(cmd, capture_output=True, cwd=SKILL).returncode == 2
    assert subprocess.run(cmd + ["--fail-on", "none"], capture_output=True, cwd=SKILL).returncode == 0
    good = [sys.executable, os.path.join(SCRIPTS, "review.py"), "--no-git", "--root", SKILL,
            "fixtures/good/safe-expand.xml"]
    assert subprocess.run(good, capture_output=True, cwd=SKILL).returncode == 0


# ----------------------------------------------------------------------------- individual rules

def test_concurrently_requires_non_transactional():
    f = analyse_sql("CREATE INDEX CONCURRENTLY ix ON orders (a);")
    assert any(x.rule == "PG-IDX-002" for x in f)
    f = analyse_sql("CREATE INDEX CONCURRENTLY ix ON orders (a);", header="runInTransaction:false")
    assert not any(x.rule == "PG-IDX-002" for x in f)
    assert any(x.rule == "LB-PRE-001" for x in f)   # non-transactional without preconditions


def test_not_null_pattern_is_recognised():
    sql = """
    SET lock_timeout = '3s';
    ALTER TABLE orders ADD CONSTRAINT nn CHECK (c IS NOT NULL) NOT VALID;
    ALTER TABLE orders VALIDATE CONSTRAINT nn;
    ALTER TABLE orders ALTER COLUMN c SET NOT NULL;
    --rollback empty
    """
    f = analyse_sql(sql)
    assert not any(x.rule in ("PG-LOCK-004", "PG-CHECK-001", "PG-FK-002") for x in f)
    assert any(x.rule == "LB-TXN-001" for x in f)   # still two locking DDLs in one changeset


def test_widening_varchar_is_high_not_critical():
    f = analyse_sql("SET lock_timeout='3s'; ALTER TABLE orders ALTER COLUMN c TYPE varchar(200); --rollback empty")
    lv = [x.level for x in f if x.rule == "PG-LOCK-005"]
    assert lv == ["HIGH"]
    f = analyse_sql("ALTER TABLE orders ALTER COLUMN c TYPE bigint;")
    assert [x.level for x in f if x.rule == "PG-LOCK-005"] == ["CRITICAL"]


def test_not_null_column_without_default_is_critical():
    f = analyse_sql("ALTER TABLE orders ADD COLUMN c int NOT NULL;")
    assert any(x.rule == "PG-COL-001" for x in f)
    f = analyse_sql("ALTER TABLE orders ADD COLUMN c int NOT NULL DEFAULT 0;")
    assert not any(x.rule == "PG-COL-001" for x in f)
    assert any(x.rule == "BG-EXPAND-001" for x in f)


def test_backfill_of_new_column_is_high():
    sql = """
    ALTER TABLE orders ADD COLUMN region text;
    UPDATE orders SET region = 'EU' WHERE region IS NULL;
    """
    f = analyse_sql(sql)
    assert any(x.rule == "PG-DML-001" for x in f)
    f = analyse_sql("UPDATE orders SET region = 'EU' WHERE id = 42;")
    assert any(x.rule == "PG-DML-002" for x in f) and not any(x.rule == "PG-DML-001" for x in f)


def test_config_small_table_downgrades_and_disables(tmp_path):
    cfg = tmp_path / "cfg.toml"
    cfg.write_text('[tables]\nsmall = ["country"]\n[rules]\ndisabled = ["LB-ROLLBACK-001"]\n')
    chg = tmp_path / "c.sql"
    chg.write_text("--liquibase formatted sql\n--changeset t:1\nCREATE INDEX ix ON country (code);\n")
    r = review(str(chg), extra=["--config", str(cfg)])
    idx = [f for f in r["findings"] if f["rule"] == "PG-IDX-001"]
    assert idx and idx[0]["level"] == "LOW"
    assert "LB-ROLLBACK-001" not in rules_for(r)


def test_yaml_and_xml_parse_equivalently():
    xml = parse_file(os.path.join(SKILL, "fixtures/bad/orders-shipping.xml"))
    assert [cs.id for cs in xml] == ["2026-10-06-01", "2026-10-06-02", "2026-10-06-03", "2026-10-06-04"]
    assert xml[1].statements[0].kind == "create_index" and not xml[1].statements[0].attrs["concurrently"]
    yml = parse_file(os.path.join(SKILL, "fixtures/bad/mixed.yaml"))
    assert yml[0].statements[0].attrs["default_volatile"]
    assert yml[1].statements[0].kind == "add_fk" and not yml[1].statements[0].attrs["not_valid"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
