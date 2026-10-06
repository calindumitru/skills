"""Rule catalog and engine for db-migration-review.

Severity levels are defined by consequence during a blue-green deploy on a hot
Postgres 16 database (Azure Flexible Server, HA, no superuser):

  CRITICAL  breaks production, halts the deploy, or breaks the old app version
            that is still serving traffic.
  HIGH      likely stall or outage under load; needs a plan before deploying.
  MEDIUM    deploys, but violates expand/contract, leaves a trap, or cannot be undone.
  LOW       hygiene.

Each rule maps to exactly one level. A repo config may override levels or
disable rules, and may list small tables (lock findings on those drop to LOW).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable

from liquibase_parser import (ChangeSet, Statement, DDL_KINDS, LOCKING_DDL_KINDS, DML_KINDS)

LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
LEVEL_RANK = {lv: i for i, lv in enumerate(LEVELS)}


@dataclass
class Finding:
    rule: str
    level: str
    title: str
    file: str
    line: int
    changeset: str
    consequence: str
    fix: str
    table: str | None = None
    column: str | None = None
    needs_model_review: bool = False
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Context:
    """Facts shared across all analysed files."""
    new_tables: set[str]                     # created in the analysed files => cold
    small_tables: set[str]                   # from config => lock findings downgraded to LOW
    lock_timeout: str = "3s"
    new_columns: set[tuple[str, str]] = field(default_factory=set)   # (table, column) added in the analysed files
    validated_constraints: set[str] = field(default_factory=set)   # names seen in VALIDATE CONSTRAINT
    not_null_checks: set[tuple[str, str]] = field(default_factory=set)  # (table, col) with CHECK ... IS NOT NULL NOT VALID
    not_valid_constraints: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (table, kind)
    level_overrides: dict[str, str] = field(default_factory=dict)
    disabled: set[str] = field(default_factory=set)

    def is_hot(self, table: str | None) -> bool:
        if table is None:
            return True
        return table not in self.new_tables and table not in self.small_tables

    def is_new(self, table: str | None) -> bool:
        return table is not None and table in self.new_tables


RuleFn = Callable[[ChangeSet, Context], list[Finding]]
RULES: list[tuple[str, str, RuleFn]] = []   # (id, default level, fn)


def rule(rule_id: str, level: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        RULES.append((rule_id, level, fn))
        return fn
    return deco


def _f(cs: ChangeSet, rule_id: str, level: str, title: str, consequence: str, fix: str,
       st: Statement | None = None, **kw: Any) -> Finding:
    return Finding(rule=rule_id, level=level, title=title, file=cs.file, line=cs.line, changeset=cs.key,
                   consequence=consequence, fix=fix, table=st.table if st else None,
                   column=(st.columns[0] if st and st.columns else None), **kw)


def _lt(ctx: Context) -> str:
    return f"SET lock_timeout = '{ctx.lock_timeout}';"


# =============================================================================== CRITICAL

@rule("PG-IDX-001", "CRITICAL")
def index_not_concurrent(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind == "create_index" and not st.attrs.get("concurrently") and not ctx.is_new(st.table):
            cols = ", ".join(st.columns) or "<columns>"
            idx = st.index or f"idx_{st.table}_{'_'.join(st.columns)}"
            uniq = "UNIQUE " if st.attrs.get("unique") else ""
            out.append(_f(cs, "PG-IDX-001", "CRITICAL", "Index created without CONCURRENTLY on an existing table",
                f"CREATE INDEX on `{st.table}` holds a SHARE lock for the whole build: every INSERT/UPDATE/DELETE "
                f"from REST and batch workers blocks until it finishes. On a hot table that is an outage; the "
                f"synchronous HA replica makes the build slower.",
                f"Build it concurrently in its own non-transactional changeset:\n"
                f"```xml\n<changeSet id=\"{cs.id}\" author=\"{cs.author}\" runInTransaction=\"false\">\n"
                f"    <preConditions onFail=\"MARK_RAN\">\n        <not><indexExists indexName=\"{idx}\"/></not>\n"
                f"    </preConditions>\n"
                f"    <sql>CREATE {uniq}INDEX CONCURRENTLY IF NOT EXISTS {idx} ON {st.table} ({cols});</sql>\n"
                f"    <rollback>DROP INDEX CONCURRENTLY IF EXISTS {idx};</rollback>\n</changeSet>\n```\n"
                f"A failed CONCURRENTLY build leaves an INVALID index behind; add a preceding changeset that drops "
                f"`{idx}` if it exists and is invalid (`runOnChange=\"true\"`, query pg_index.indisvalid).", st))
    return out


@rule("PG-IDX-002", "CRITICAL")
def concurrently_in_transaction(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    if not cs.run_in_transaction:
        return out
    for st in cs.statements:
        if st.kind in ("create_index", "drop_index", "reindex") and st.attrs.get("concurrently"):
            hdr = ("`--changeset author:id runInTransaction:false`" if cs.fmt == "sql"
                   else "`runInTransaction=\"false\"` on the changeSet" if cs.fmt == "xml"
                   else "`runInTransaction: false` on the changeSet")
            out.append(_f(cs, "PG-IDX-002", "CRITICAL", "CONCURRENTLY inside a transaction: Liquibase will fail and halt the deploy",
                "Liquibase wraps every changeset in a transaction by default. Postgres rejects CONCURRENTLY inside a "
                "transaction block, so the changeset errors, Liquibase stops, the app does not start and the "
                "blue-green switch never happens.",
                f"Add {hdr} and keep this statement alone in its changeset.", st))
    return out


@rule("BG-CONTRACT-001", "CRITICAL")
def drop_table(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind in ("drop_table", "truncate") and not ctx.is_new(st.table):
            what = "Table dropped" if st.kind == "drop_table" else "Table truncated"
            out.append(_f(cs, "BG-CONTRACT-001", "CRITICAL", f"{what} while the old app version may still use it",
                f"During blue-green the previous version keeps serving traffic after this runs. Any entity or mapper "
                f"still touching `{st.table}` fails on every call. TRUNCATE also takes ACCESS EXCLUSIVE.",
                f"Contract in a later release: first ship code that no longer uses `{st.table}`, deploy it fully, "
                f"then drop the table in the next release. Keep a `<rollback>` that recreates it, or accept it is irreversible.",
                st, needs_model_review=True))
    return out


@rule("BG-CONTRACT-002", "CRITICAL")
def drop_column(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind == "drop_column" and not ctx.is_new(st.table):
            out.append(_f(cs, "BG-CONTRACT-002", "CRITICAL", "Column dropped while the old app version may still read it",
                f"During blue-green the previous version keeps serving traffic after this runs. If any Hibernate entity "
                f"or MyBatis mapper still selects or inserts `{st.table}.{st.columns[0]}`, every query on `{st.table}` "
                f"fails with `column does not exist`. Hibernate `select *`-style entity loads fail even if the field is unused.",
                f"Remove the drop from this PR. Release N: stop reading/writing the column in code (for Hibernate, remove "
                f"the field or mark it `@Transient`). Release N+1, once no deployed version references it: drop it.",
                st, needs_model_review=True))
    return out


@rule("BG-CONTRACT-003", "CRITICAL")
def rename(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind in ("rename_column", "rename_table") and not ctx.is_new(st.table):
            old = f"{st.table}.{st.columns[0]}" if st.kind == "rename_column" else st.table
            out.append(_f(cs, "BG-CONTRACT-003", "CRITICAL", "Rename breaks the old app version immediately",
                f"A rename is a drop and a create from the point of view of the running old version: `{old}` disappears "
                f"while that version still serves traffic, so its queries fail until the switch completes.",
                f"Use expand/contract instead: add the new name as a new {'column' if st.kind == 'rename_column' else 'table'}, "
                f"dual-write from the app (or a trigger) for one release, backfill in batches, switch reads, then drop the old one "
                f"in a later release.", st, needs_model_review=True))
    return out


@rule("PG-LOCK-004", "CRITICAL")
def set_not_null_direct(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind != "set_not_null" or ctx.is_new(st.table):
            continue
        col = st.columns[0] if st.columns else "<col>"
        if (st.table, col) in ctx.not_null_checks:
            continue   # the NOT VALID + VALIDATE pattern is present in the analysed files
        cname = f"{st.table}_{col}_nn"
        out.append(_f(cs, "PG-LOCK-004", "CRITICAL", "NOT NULL set directly on an existing table",
            f"`ALTER TABLE {st.table} ALTER COLUMN {col} SET NOT NULL` takes ACCESS EXCLUSIVE and scans the whole table "
            f"while holding it. REST and batch traffic on `{st.table}` stalls for the duration; on 2 vCores with HA this "
            f"is minutes on a large table. Liquibase `addNotNullConstraint` emits exactly this statement.",
            f"Postgres 12+: prove it with a NOT VALID check first, validate under a weak lock, then SET NOT NULL (PG16 "
            f"skips the rescan when a validated constraint proves it):\n```sql\n"
            f"--changeset {cs.author}:{cs.id}-a\n{_lt(ctx)}\n"
            f"ALTER TABLE {st.table} ADD CONSTRAINT {cname} CHECK ({col} IS NOT NULL) NOT VALID;\n"
            f"--changeset {cs.author}:{cs.id}-b\nALTER TABLE {st.table} VALIDATE CONSTRAINT {cname};\n"
            f"--changeset {cs.author}:{cs.id}-c\n{_lt(ctx)}\n"
            f"ALTER TABLE {st.table} ALTER COLUMN {col} SET NOT NULL;\nALTER TABLE {st.table} DROP CONSTRAINT {cname};\n```\n"
            f"Backfill NULLs in batches before step b, and make sure the old app version already writes this column, "
            f"otherwise its INSERTs fail after step c.", st))
    return out


@rule("PG-LOCK-005", "CRITICAL")
def alter_type(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind != "alter_column_type" or ctx.is_new(st.table):
            continue
        new_type = (st.attrs.get("new_type") or "").lower()
        widening = new_type.startswith(("varchar", "character varying", "text")) and not st.attrs.get("using")
        level = "HIGH" if widening else "CRITICAL"
        note = (" Widening a varchar(n) or converting to text is metadata-only on Postgres; if that is the case here, "
                "note it in the PR and this drops to a lock_timeout concern." if widening else "")
        out.append(_f(cs, "PG-LOCK-005", level, "Column type changed on an existing table (table rewrite)",
            f"`ALTER COLUMN ... TYPE` rewrites `{st.table}` under ACCESS EXCLUSIVE and rebuilds its indexes. Every query "
            f"on the table waits for the rewrite; the HA replica must replay the full rewrite too. The old app version "
            f"may also send values the new type rejects.{note}",
            f"Expand/contract: add a new column with the new type, dual-write, backfill in batches, switch reads, drop the old "
            f"column in a later release. For a pure widening, keep `{_lt(ctx)}` in front of the ALTER.", st))
    return out


@rule("PG-LOCK-006", "CRITICAL")
def fk_without_not_valid(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind == "add_fk" and not st.attrs.get("not_valid") and not ctx.is_new(st.table):
            name = st.constraint or f"fk_{st.table}_{'_'.join(st.columns)}"
            out.append(_f(cs, "PG-LOCK-006", "CRITICAL", "Foreign key added without NOT VALID on an existing table",
                f"Adding a validated FK scans `{st.table}` under SHARE ROW EXCLUSIVE on both `{st.table}` and the "
                f"referenced table, blocking writes on both for the whole scan.",
                f"Add it NOT VALID (Liquibase: `validate=\"false\"` on addForeignKeyConstraint) and validate in a separate "
                f"changeset, which only takes SHARE UPDATE EXCLUSIVE:\n```sql\n{_lt(ctx)}\n"
                f"ALTER TABLE {st.table} ADD CONSTRAINT {name} FOREIGN KEY (...) REFERENCES ... NOT VALID;\n"
                f"-- next changeset\nALTER TABLE {st.table} VALIDATE CONSTRAINT {name};\n```", st))
    return out


@rule("PG-REWRITE-001", "CRITICAL")
def volatile_default(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind == "add_column" and st.attrs.get("default_volatile") and not ctx.is_new(st.table):
            out.append(_f(cs, "PG-REWRITE-001", "CRITICAL", "Column added with a volatile default (full table rewrite)",
                f"Postgres stores a non-volatile default as metadata, but `{st.attrs.get('default')}` is volatile, so "
                f"`{st.table}` is rewritten row by row under ACCESS EXCLUSIVE.",
                f"Add the column nullable with no default (or a constant default), backfill in batches, then set the "
                f"volatile default for new rows with `ALTER COLUMN ... SET DEFAULT` (metadata-only).", st))
    return out


@rule("PG-COL-001", "CRITICAL")
def not_null_without_default(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if (st.kind == "add_column" and st.attrs.get("not_null") and st.attrs.get("default") is None
                and not st.attrs.get("generated_identity") and not ctx.is_new(st.table)):
            out.append(_f(cs, "PG-COL-001", "CRITICAL", "NOT NULL column added without a default: fails on a populated table",
                f"`ALTER TABLE {st.table} ADD COLUMN {st.columns[0]} ... NOT NULL` errors with `column contains null values` "
                f"as soon as the table has rows. Liquibase halts, the app does not start. Even with a default, the old app "
                f"version must not insert explicit NULLs.",
                f"Add it nullable (expand), backfill in batches, have the new app version write it, then tighten with the "
                f"NOT VALID check pattern (see PG-LOCK-004) in a later release. If a constant default is acceptable, "
                f"`DEFAULT <const> NOT NULL` is metadata-only on Postgres 11+.", st))
    return out


@rule("PG-MAINT-001", "CRITICAL")
def maintenance(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind in ("cluster", "vacuum_full") or (st.kind == "reindex" and not st.attrs.get("concurrently")):
            if st.kind == "reindex" and st.attrs.get("target") == "index" and not ctx.is_hot(None):
                continue
            verb = {"cluster": "CLUSTER", "vacuum_full": "VACUUM FULL", "reindex": "REINDEX"}[st.kind]
            out.append(_f(cs, "PG-MAINT-001", "CRITICAL", f"{verb} takes ACCESS EXCLUSIVE for its whole duration",
                f"{verb} rewrites the relation and blocks all reads and writes until done. Azure Flexible Server gives "
                f"you no way to cancel it from the app side without DB access.",
                "Do not run maintenance from a migration. Use `REINDEX ... CONCURRENTLY` (PG12+) if an index must be "
                "rebuilt, and schedule VACUUM FULL / CLUSTER as an operations task in a maintenance window.", st))
    return out


@rule("LB-CHK-001", "CRITICAL")
def modified_changeset(cs: ChangeSet, ctx: Context) -> list[Finding]:
    # Populated by review.py when it compares against the git base; the rule exists so the
    # id/level participates in overrides and documentation.
    return []


# =============================================================================== HIGH

@rule("PG-LOCK-001", "HIGH")
def missing_lock_timeout(cs: ChangeSet, ctx: Context) -> list[Finding]:
    if not cs.run_in_transaction:
        # lock_timeout still applies, but aborting a CONCURRENTLY build leaves an invalid index; keep quiet here.
        return []
    locking = [s for s in cs.statements if s.kind in LOCKING_DDL_KINDS and ctx.is_hot(s.table)
               and s.kind not in ("cluster", "vacuum_full")]
    if not locking:
        return []
    if any(s.kind == "set_lock_timeout" for s in cs.statements):
        return []
    first = locking[0]
    return [_f(cs, "PG-LOCK-001", "HIGH", "DDL on a hot table without lock_timeout",
        f"The ALTER needs ACCESS EXCLUSIVE on `{first.table}`. If a batch transaction still holds the table, the ALTER "
        f"waits for it, and every new query on `{first.table}` (REST included) queues behind the waiting ALTER. With no "
        f"timeout the stall lasts as long as the longest batch transaction. Azure Flexible Server has no superuser, so "
        f"this is the only place the developer can set it.",
        f"Make `{_lt(ctx)}` the first statement of this changeset (it is session-scoped, so repeat it in every DDL "
        f"changeset). A timed-out changeset fails fast and can be retried at a quieter moment instead of stalling production.",
        first)]


def _is_backfill(st: Statement, ctx: Context) -> bool:
    """An UPDATE whose WHERE only filters on a column added in this change set is a full-table backfill."""
    where = (st.attrs.get("where") or "").lower()
    return any(t == st.table and c in where for (t, c) in ctx.new_columns)


@rule("PG-DML-001", "HIGH")
def unbounded_dml(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind not in ("update", "delete") or ctx.is_new(st.table):
            continue
        backfill = st.attrs.get("has_where") and not st.attrs.get("batched") and _is_backfill(st, ctx)
        if st.attrs.get("has_where") and not backfill:
            continue
        title = (f"{st.kind.upper()} without WHERE on a hot table" if not st.attrs.get("has_where")
                 else f"Full-table backfill of a new column on a hot table, not batched")
        out.append(_f(cs, "PG-DML-001", "HIGH", title,
                f"One transaction row-locks every row of `{st.table}` until commit. Your batch workers lock rows in the "
                f"same table, so both sides wait on each other while REST calls queue behind them; the WAL burst hits "
                f"the HA replica at once.",
                f"Backfill in bounded batches, each its own transaction (`runInTransaction=\"false\"` and a DO block with "
                f"COMMIT per batch, or `WHERE ctid IN (SELECT ctid FROM {st.table} WHERE ... LIMIT 5000)` repeated), "
                f"or move the data fix to an application job that runs after deploy.", st))
    return out


@rule("PG-IDX-003", "HIGH")
def drop_index_not_concurrent(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind == "drop_index" and not st.attrs.get("concurrently"):
            out.append(_f(cs, "PG-IDX-003", "HIGH", "Index dropped without CONCURRENTLY",
                "DROP INDEX takes ACCESS EXCLUSIVE on the table. Short, but it queues behind any running batch "
                "transaction and everything else queues behind it.",
                f"`DROP INDEX CONCURRENTLY IF EXISTS {st.index};` in a `runInTransaction=\"false\"` changeset.", st))
    return out


@rule("PG-UNIQ-001", "HIGH")
def unique_pk_inline(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind in ("add_unique", "add_pk") and not st.attrs.get("using_index") and not ctx.is_new(st.table):
            cols = ", ".join(st.columns) or "<cols>"
            idx = f"{st.table}_{'_'.join(st.columns) or 'key'}_uidx"
            kind = "PRIMARY KEY" if st.kind == "add_pk" else "UNIQUE"
            out.append(_f(cs, "PG-UNIQ-001", "HIGH", f"{kind} constraint builds its index under ACCESS EXCLUSIVE",
                f"`ADD CONSTRAINT ... {kind} ({cols})` builds the backing index while holding ACCESS EXCLUSIVE on "
                f"`{st.table}`, so all traffic waits for the full build.",
                f"Build the index first, then attach it:\n```sql\n-- changeset 1, runInTransaction:false\n"
                f"CREATE UNIQUE INDEX CONCURRENTLY {idx} ON {st.table} ({cols});\n-- changeset 2\n{_lt(ctx)}\n"
                f"ALTER TABLE {st.table} ADD CONSTRAINT {st.constraint or idx} {kind} USING INDEX {idx};\n```\n"
                f"Liquibase: `forIndexName=\"{idx}\"` on addUniqueConstraint / addPrimaryKey.", st))
    return out


@rule("PG-CHECK-001", "HIGH")
def check_without_not_valid(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind == "add_check" and not st.attrs.get("not_valid") and not ctx.is_new(st.table):
            out.append(_f(cs, "PG-CHECK-001", "HIGH", "CHECK constraint added without NOT VALID",
                f"Adding a validated CHECK scans all of `{st.table}` under ACCESS EXCLUSIVE.",
                f"Add it `NOT VALID`, then `ALTER TABLE {st.table} VALIDATE CONSTRAINT ...` in its own changeset "
                f"(SHARE UPDATE EXCLUSIVE only).", st))
    return out


# =============================================================================== MEDIUM

@rule("LB-TXN-001", "MEDIUM")
def multiple_ddl_one_txn(cs: ChangeSet, ctx: Context) -> list[Finding]:
    if not cs.run_in_transaction:
        return []
    locking = [s for s in cs.statements if s.kind in LOCKING_DDL_KINDS and ctx.is_hot(s.table)]
    extra = sum(max(0, int(s.attrs.get("actions", 1)) - 1) for s in locking)
    if len(locking) + extra < 2:
        return []
    tables = sorted({s.table for s in locking if s.table})
    return [_f(cs, "LB-TXN-001", "MEDIUM", "Several locking DDL statements in one transactional changeset",
        f"The lock taken by the first ALTER on {', '.join(f'`{t}`' for t in tables)} is held until the last statement "
        f"commits, and a failure halfway rolls everything back while having stalled traffic for nothing.",
        "One locking statement per changeset, each prefixed with lock_timeout. Keep non-locking statements "
        "(VALIDATE CONSTRAINT, batched DML) in their own changesets too.", locking[0])]


@rule("PG-DML-002", "MEDIUM")
def unbatched_dml(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if (st.kind in ("update", "delete") and not ctx.is_new(st.table) and st.attrs.get("has_where")
                and not st.attrs.get("batched") and not _is_backfill(st, ctx)):
            out.append(_f(cs, "PG-DML-002", "MEDIUM", f"{st.kind.upper()} with WHERE but not batched",
                f"If the WHERE matches many rows of `{st.table}`, the row locks are held until commit and collide with "
                f"the batch workers' own row locks. Fine for a handful of rows; a problem for a backfill.",
                "State the expected row count in the changeset comment. If it is more than a few thousand rows, batch "
                "it (ctid/LIMIT loop or an application job).", st))
    return out


@rule("LB-PRE-001", "MEDIUM")
def non_txn_without_preconditions(cs: ChangeSet, ctx: Context) -> list[Finding]:
    if cs.run_in_transaction or cs.has_preconditions:
        return []
    if not any(s.kind in DDL_KINDS for s in cs.statements):
        return []
    return [_f(cs, "LB-PRE-001", "MEDIUM", "Non-transactional changeset without preconditions",
        "With runInTransaction=false a failure halfway leaves partial state (for example an INVALID index) and the "
        "changeset re-runs on the next start, which then fails on `already exists` and halts the deploy.",
        "Add `<preConditions onFail=\"MARK_RAN\">` (indexExists / columnExists / sqlCheck) so a retry is safe, and "
        "use IF NOT EXISTS / IF EXISTS in the SQL.")]


@rule("PG-FK-002", "MEDIUM")
def not_valid_never_validated(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if st.kind in ("add_fk", "add_check") and st.attrs.get("not_valid") and st.constraint \
                and st.constraint not in ctx.validated_constraints:
            out.append(_f(cs, "PG-FK-002", "MEDIUM", "NOT VALID constraint is never validated",
                f"`{st.constraint}` is enforced for new rows only; existing rows are unchecked until VALIDATE runs. "
                f"Planner and future NOT NULL tightening cannot rely on it.",
                f"Add a follow-up changeset: `ALTER TABLE {st.table} VALIDATE CONSTRAINT {st.constraint};`", st))
    return out


@rule("LB-ROLLBACK-001", "MEDIUM")
def missing_rollback_ddl(cs: ChangeSet, ctx: Context) -> list[Finding]:
    if cs.has_rollback:
        return []
    irreversible = [s for s in cs.statements if s.kind in ("drop_table", "drop_column", "truncate", "alter_column_type")
                    or (s.source == "sql" and s.kind in DDL_KINDS)]
    if not irreversible:
        return []
    return [_f(cs, "LB-ROLLBACK-001", "MEDIUM", "No rollback for DDL that Liquibase cannot reverse automatically",
        "Raw SQL DDL, drops and type changes have no auto-generated rollback. If the blue-green switch is aborted, "
        "the schema stays ahead of the app version that gets traffic.",
        "Add an explicit `<rollback>` (or `--rollback` in formatted SQL). For a drop, either recreate it or write "
        "`<rollback/>` / `--rollback empty` deliberately and say in the PR that it is irreversible.", irreversible[0])]


@rule("BG-EXPAND-001", "MEDIUM")
def new_not_null_column_old_writers(cs: ChangeSet, ctx: Context) -> list[Finding]:
    out = []
    for st in cs.statements:
        if (st.kind == "add_column" and st.attrs.get("not_null") and st.attrs.get("default") is not None
                and not ctx.is_new(st.table)):
            out.append(_f(cs, "BG-EXPAND-001", "MEDIUM", "New NOT NULL column: old app version relies on the default",
                f"The old version still inserts into `{st.table}` without knowing `{st.columns[0]}`. That works only "
                f"while every insert path omits the column; an explicit NULL (MyBatis `<insert>` listing all columns, "
                f"Hibernate with the field present but null) fails.",
                "Verify no deployed version inserts an explicit NULL for this column. If unsure, add it nullable now "
                "and tighten in a later release.", st, needs_model_review=True))
    return out


# =============================================================================== LOW

@rule("LB-HYG-001", "LOW")
def run_on_change_ddl(cs: ChangeSet, ctx: Context) -> list[Finding]:
    if not (cs.run_on_change or cs.run_always):
        return []
    if not any(s.kind in DDL_KINDS and s.kind not in ("create_view", "create_function") for s in cs.statements):
        return []
    return [_f(cs, "LB-HYG-001", "LOW", "runOnChange / runAlways on a DDL changeset",
        "The DDL re-executes whenever the changeset text changes (or on every start), taking its locks again in production.",
        "Reserve runOnChange for idempotent views, functions and reference data. Keep DDL in append-only changesets.")]


@rule("LB-ROLLBACK-002", "LOW")
def missing_rollback_dml(cs: ChangeSet, ctx: Context) -> list[Finding]:
    if cs.has_rollback:
        return []
    dml = [s for s in cs.statements if s.source == "sql" and s.kind in DML_KINDS]
    if not dml or any(s.kind in DDL_KINDS for s in cs.statements):
        return []
    return [_f(cs, "LB-ROLLBACK-002", "LOW", "Raw SQL data change without a rollback",
        "Liquibase cannot auto-generate a rollback for `<sql>`.",
        "Add a `<rollback>` that reverses the data change, or an explicit empty one.", dml[0])]


# =============================================================================== engine

def build_context(changesets: list[ChangeSet], config: dict[str, Any]) -> Context:
    ctx = Context(new_tables=set(), small_tables=set(str(t).lower() for t in (config.get("tables", {}).get("small") or [])),
                  lock_timeout=str(config.get("database", {}).get("lock_timeout", "3s")))
    rules_cfg = config.get("rules", {}) or {}
    ctx.disabled = set(rules_cfg.get("disabled") or [])
    ctx.level_overrides = {k: str(v).upper() for k, v in (rules_cfg.get("levels") or {}).items()}
    for cs in changesets:
        for st in cs.statements:
            if st.kind == "create_table" and st.table:
                ctx.new_tables.add(st.table)
            if st.kind == "add_column" and st.table:
                for c in st.columns:
                    ctx.new_columns.add((st.table, c))
            if st.kind == "validate_constraint" and st.constraint:
                ctx.validated_constraints.add(st.constraint)
            if st.kind == "add_check" and st.attrs.get("not_valid") and st.attrs.get("is_not_null_check"):
                for c in st.columns:
                    ctx.not_null_checks.add((st.table, c))
    return ctx


def apply_overrides(f: Finding, ctx: Context) -> Finding | None:
    if f.rule in ctx.disabled:
        return None
    if f.rule in ctx.level_overrides and f.level in LEVELS and f.rule not in ("PG-LOCK-005",):
        f.level = ctx.level_overrides[f.rule]
    if f.table and f.table in ctx.small_tables and f.rule.startswith(("PG-LOCK", "PG-IDX", "PG-UNIQ", "PG-CHECK", "PG-REWRITE", "PG-DML", "LB-TXN")):
        if LEVEL_RANK[f.level] < LEVEL_RANK["LOW"]:
            f.notes.append(f"`{f.table}` is listed as a small table in the config; downgraded to LOW.")
            f.level = "LOW"
    return f


def run_rules(changesets: list[ChangeSet], ctx: Context) -> list[Finding]:
    findings: list[Finding] = []
    for cs in changesets:
        for rule_id, _default, fn in RULES:
            if rule_id in ctx.disabled:
                continue
            for f in fn(cs, ctx):
                f2 = apply_overrides(f, ctx)
                if f2:
                    findings.append(f2)
    findings.sort(key=lambda f: (LEVEL_RANK.get(f.level, 9), f.file, f.line, f.rule))
    return findings


def catalog() -> list[dict[str, str]]:
    return [{"id": rid, "level": lvl, "name": fn.__name__} for rid, lvl, fn in RULES]
