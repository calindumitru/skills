# Rule catalog

Target: Postgres 16 on Azure Database for PostgreSQL Flexible Server (zone-redundant HA, small vCore count,
no superuser), hot tables with REST traffic and batch jobs holding row locks, Cloud Foundry blue-green deploys
where the **old app version keeps running against the new schema**.

A table is **cold** when it is created in the reviewed files; rules about locks and compatibility skip cold
tables. Tables listed under `[tables] small` in the config get lock findings downgraded to LOW.

## Lock primer

| Statement | Lock on the table | Blocks |
|---|---|---|
| `CREATE INDEX` | SHARE | all writes, for the whole build |
| `CREATE INDEX CONCURRENTLY` | SHARE UPDATE EXCLUSIVE | other DDL only; needs `runInTransaction=false`; leaves an INVALID index on failure |
| `ALTER TABLE ... ADD COLUMN` (constant default) | ACCESS EXCLUSIVE, milliseconds | everything, briefly, **but queues behind any open transaction** |
| `ALTER TABLE ... SET NOT NULL`, `ADD CONSTRAINT` (validated), `ALTER TYPE` | ACCESS EXCLUSIVE for a full scan or rewrite | everything, for minutes |
| `ADD CONSTRAINT ... NOT VALID` | ACCESS EXCLUSIVE, milliseconds | everything, briefly |
| `VALIDATE CONSTRAINT` | SHARE UPDATE EXCLUSIVE | other DDL only |
| `DROP INDEX` | ACCESS EXCLUSIVE, brief | everything, briefly |
| `VACUUM FULL`, `CLUSTER`, `REINDEX` | ACCESS EXCLUSIVE for the duration | everything |

The queue effect is the real danger: an ALTER waiting for ACCESS EXCLUSIVE behind a batch transaction makes every
new query on that table wait behind the ALTER. `SET lock_timeout = '3s'` at the start of the changeset turns that
stall into a fast, retryable failure. It is session-scoped and must be repeated per changeset.

## CRITICAL — breaks production, halts the deploy, or breaks the old app version

| Id | Trigger | Why | Fix |
|---|---|---|---|
| PG-IDX-001 | `createIndex` / `CREATE INDEX` without CONCURRENTLY on an existing table | SHARE lock blocks all writes for the build | `CREATE INDEX CONCURRENTLY IF NOT EXISTS` in its own `runInTransaction=false` changeset with an `indexExists` precondition; handle INVALID leftovers |
| PG-IDX-002 | CONCURRENTLY (create/drop index, reindex) in a transactional changeset | Postgres rejects it inside a transaction; Liquibase errors and the app does not start | `runInTransaction="false"` (XML/YAML) or `runInTransaction:false` (formatted SQL); one statement per changeset |
| BG-CONTRACT-001 | `dropTable`, `TRUNCATE` on an existing table | The old version still queries it | Contract one release later; `<rollback>` recreating it or an explicit empty rollback |
| BG-CONTRACT-002 | `dropColumn` | Old version's entity loads / mapper selects fail with `column does not exist` | Remove from this PR; stop referencing in code first; drop next release |
| BG-CONTRACT-003 | `renameColumn`, `renameTable` | A rename is a drop for the running old version | Add new, dual-write, backfill, switch, drop old later |
| PG-LOCK-004 | `addNotNullConstraint` / `SET NOT NULL` on an existing table without a validated `CHECK (col IS NOT NULL) NOT VALID` in the same files | Full scan under ACCESS EXCLUSIVE | NOT VALID check → VALIDATE → SET NOT NULL (PG16 skips the rescan) |
| PG-LOCK-005 | `modifyDataType` / `ALTER COLUMN TYPE` | Table rewrite plus index rebuild under ACCESS EXCLUSIVE; old version may send incompatible values. Widening varchar/text is HIGH (metadata-only but still locks) | Expand/contract with a new column |
| PG-LOCK-006 | `addForeignKeyConstraint` without `validate="false"` / FK without NOT VALID | Scans both tables under SHARE ROW EXCLUSIVE | NOT VALID, then `VALIDATE CONSTRAINT` in its own changeset |
| PG-REWRITE-001 | `addColumn` with a volatile default (`gen_random_uuid()`, `random()`, `clock_timestamp()`, `nextval`, `uuid_generate_v4()`) | Volatile defaults force a full rewrite (non-volatile ones like `now()` are metadata-only) | Add nullable, backfill in batches, then `SET DEFAULT` |
| PG-COL-001 | `addColumn` NOT NULL with no default on an existing table | `column contains null values` error; Liquibase halts | Add nullable (expand), backfill, tighten later; or a constant default |
| PG-MAINT-001 | `VACUUM FULL`, `CLUSTER`, non-concurrent `REINDEX` | ACCESS EXCLUSIVE for the duration, cannot be cancelled without DB access | Operations task in a maintenance window; `REINDEX CONCURRENTLY` |
| LB-CHK-001 | An already-applied changeset's body differs from the base branch (explicit-file mode) and has no `validCheckSum` | Checksum mismatch at startup halts the deploy | Revert and add a new changeset |

## HIGH — likely stall or outage under load; needs a plan

| Id | Trigger | Why | Fix |
|---|---|---|---|
| PG-LOCK-001 | Locking DDL on a hot table in a transactional changeset without `SET lock_timeout` | ALTER queues behind batch transactions, everything queues behind the ALTER | `SET lock_timeout = '3s';` first in every DDL changeset |
| PG-DML-001 | `UPDATE`/`DELETE` without WHERE, or a WHERE that only filters on a column added in the same files (full backfill), unbatched | Row-locks the whole table until commit; collides with batch workers; WAL burst to the HA replica | Batches of a few thousand rows, each its own transaction, or an application job |
| PG-IDX-003 | `dropIndex` / `DROP INDEX` without CONCURRENTLY | Brief ACCESS EXCLUSIVE that queues behind open transactions | `DROP INDEX CONCURRENTLY IF EXISTS` in a non-transactional changeset |
| PG-UNIQ-001 | `addUniqueConstraint` / `addPrimaryKey` without `forIndexName`, `ADD CONSTRAINT ... UNIQUE/PRIMARY KEY` without `USING INDEX` | Index built while holding ACCESS EXCLUSIVE | `CREATE UNIQUE INDEX CONCURRENTLY` first, then `ADD CONSTRAINT ... USING INDEX` |
| PG-CHECK-001 | CHECK constraint added without NOT VALID on an existing table | Full scan under ACCESS EXCLUSIVE | NOT VALID, then VALIDATE |

## MEDIUM — deploys, but violates expand/contract, leaves a trap, or cannot be undone

| Id | Trigger | Why | Fix |
|---|---|---|---|
| LB-TXN-001 | Two or more locking DDL statements in one transactional changeset on hot tables | First lock held until the last statement commits; partial failure stalls traffic for nothing | One locking statement per changeset |
| PG-DML-002 | `UPDATE`/`DELETE` with WHERE but no batching pattern (`LIMIT`, `ctid`, `BETWEEN`) | Fine for few rows, a problem for many | State the row count; batch if large |
| LB-PRE-001 | `runInTransaction=false` changeset with DDL and no preconditions | Partial failure leaves state, retry fails on `already exists` | `preConditions onFail="MARK_RAN"` plus `IF [NOT] EXISTS` |
| PG-FK-002 | NOT VALID constraint with no `VALIDATE CONSTRAINT` in the reviewed files | Existing rows unchecked; planner cannot use it | Follow-up VALIDATE changeset |
| LB-ROLLBACK-001 | No rollback for raw-SQL DDL, drops or type changes | Liquibase cannot generate one; an aborted switch leaves the schema ahead | Explicit `<rollback>` or a deliberate empty one |
| BG-EXPAND-001 | New NOT NULL column with a default on an existing table | Old version's inserts rely on omitting the column; an explicit NULL fails | Verify insert paths; or add nullable first |

## LOW — hygiene

| Id | Trigger | Fix |
|---|---|---|
| LB-HYG-001 | `runOnChange` / `runAlways` on DDL | Reserve for idempotent views, functions, reference data |
| LB-ROLLBACK-002 | Raw-SQL data change without rollback | Add one or an explicit empty one |

## Deliberately not rules

- Connection pool, thread and timeout tuning: out of scope unless a finding cannot be fixed in the changeset.
- `addColumn` nullable with no or constant default: metadata-only on PG11+, passes (lock_timeout still applies).
- `dropNotNullConstraint`, `dropDefaultValue`, `SET DEFAULT` with a non-volatile value: metadata-only, pass.
- Index on a table created in the same files: cold, passes.
