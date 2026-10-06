"""Parse Liquibase changelogs (XML, YAML, formatted SQL) into a neutral changeset model.

Every change type and every raw SQL statement is normalised into a `Statement`
with a `kind` drawn from a small shared vocabulary, so the rules engine never
has to care which file format a changeset came from.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- model

VOLATILE_DEFAULT_RE = re.compile(
    r"\b(random|gen_random_uuid|uuid_generate_v\d|clock_timestamp|timeofday|nextval)\s*\(",
    re.I,
)


@dataclass
class Statement:
    kind: str                      # see KINDS below
    table: str | None = None
    columns: list[str] = field(default_factory=list)
    index: str | None = None
    constraint: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    raw: str = ""                  # SQL text or a synthetic description
    source: str = "change"         # "change" (Liquibase tag) or "sql" (raw)

    def signature(self) -> str:
        cols = ",".join(self.columns)
        attrs = ",".join(f"{k}={v}" for k, v in sorted(self.attrs.items()))
        return f"{self.kind}|{self.table}|{cols}|{self.index}|{self.constraint}|{attrs}|{self.raw.strip()}"


KINDS = {
    "create_table", "drop_table", "rename_table", "truncate",
    "add_column", "drop_column", "rename_column", "alter_column_type",
    "set_not_null", "drop_not_null", "set_default", "drop_default",
    "create_index", "drop_index", "reindex", "cluster", "vacuum_full",
    "add_fk", "add_unique", "add_pk", "add_check", "validate_constraint", "drop_constraint",
    "update", "delete", "insert", "select",
    "set_lock_timeout", "set_statement_timeout", "set_other",
    "create_sequence", "create_view", "create_function", "comment",
    "noop", "unknown",
}

DDL_KINDS = {
    "create_table", "drop_table", "rename_table", "truncate",
    "add_column", "drop_column", "rename_column", "alter_column_type",
    "set_not_null", "drop_not_null", "set_default", "drop_default",
    "create_index", "drop_index", "reindex", "cluster", "vacuum_full",
    "add_fk", "add_unique", "add_pk", "add_check", "validate_constraint", "drop_constraint",
}
# DDL kinds that take a lock on an *existing* table and therefore want lock_timeout.
LOCKING_DDL_KINDS = DDL_KINDS - {"create_table", "create_index", "drop_index", "reindex", "validate_constraint"}
DML_KINDS = {"update", "delete", "insert"}


@dataclass
class ChangeSet:
    id: str
    author: str
    file: str
    line: int
    fmt: str                                   # xml | yaml | sql
    run_in_transaction: bool = True
    run_on_change: bool = False
    run_always: bool = False
    context: str | None = None
    labels: str | None = None
    dbms: str | None = None
    has_rollback: bool = False
    has_preconditions: bool = False
    valid_checksums: list[str] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    parse_notes: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.author}:{self.id}"

    def signature(self) -> str:
        return "\n".join(s.signature() for s in self.statements)


# --------------------------------------------------------------------------- SQL splitting

def split_sql(text: str) -> list[str]:
    """Split SQL on ';' while respecting single quotes, dollar quotes and comments."""
    out, buf, i, n = [], [], 0, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            buf.append(text[i:j + 1])
            i = j + 1
            continue
        if ch == "$":
            m = re.match(r"\$[A-Za-z_]*\$", text[i:])
            if m:
                tag = m.group(0)
                j = text.find(tag, i + len(tag))
                if j < 0:
                    buf.append(text[i:])
                    i = n
                else:
                    buf.append(text[i:j + len(tag)])
                    i = j + len(tag)
                continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    stmt = "".join(buf).strip()
    if stmt:
        out.append(stmt)
    return out


# --------------------------------------------------------------------------- SQL classification

_ident = r'("?[A-Za-z_][\w$]*"?(?:\s*\.\s*"?[A-Za-z_][\w$]*"?)?)'


def _clean_ident(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.replace('"', "").strip()
    return s.split(".")[-1].lower()


def _cols_from_paren(s: str) -> list[str]:
    m = re.search(r"\(([^)]*)\)", s)
    if not m:
        return []
    return [_clean_ident(c.split()[0]) for c in m.group(1).split(",") if c.strip()]


def classify_sql(sql: str) -> Statement:
    """Map one SQL statement to a Statement. Postgres dialect."""
    s = re.sub(r"\s+", " ", sql.strip())
    u = s.upper()
    st = Statement(kind="unknown", raw=sql.strip(), source="sql")

    m = re.match(r"SET\s+(LOCAL\s+)?LOCK_TIMEOUT\s*(=|TO)\s*(.+)", s, re.I)
    if m:
        st.kind = "set_lock_timeout"
        st.attrs["value"] = m.group(3).strip().strip("'\"")
        return st
    m = re.match(r"SET\s+(LOCAL\s+)?STATEMENT_TIMEOUT\s*(=|TO)\s*(.+)", s, re.I)
    if m:
        st.kind = "set_statement_timeout"
        st.attrs["value"] = m.group(3).strip().strip("'\"")
        return st
    if re.match(r"SET\s+", s, re.I):
        st.kind = "set_other"
        return st

    m = re.match(r"CREATE\s+(UNIQUE\s+)?INDEX\s+(CONCURRENTLY\s+)?(IF\s+NOT\s+EXISTS\s+)?" + _ident + r"?\s*ON\s+(ONLY\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "create_index"
        st.attrs["unique"] = bool(m.group(1))
        st.attrs["concurrently"] = bool(m.group(2))
        st.attrs["if_not_exists"] = bool(m.group(3))
        st.index = _clean_ident(m.group(4))
        st.table = _clean_ident(m.group(6))
        st.columns = _cols_from_paren(s[m.end():])
        return st
    m = re.match(r"DROP\s+INDEX\s+(CONCURRENTLY\s+)?(IF\s+EXISTS\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "drop_index"
        st.attrs["concurrently"] = bool(m.group(1))
        st.index = _clean_ident(m.group(3))
        return st
    m = re.match(r"REINDEX\s+(\(.*?\)\s*)?(INDEX|TABLE|SCHEMA|DATABASE|SYSTEM)\s+(CONCURRENTLY\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "reindex"
        st.attrs["concurrently"] = bool(m.group(3)) or "CONCURRENTLY" in (m.group(1) or "").upper()
        st.attrs["target"] = m.group(2).lower()
        if m.group(2).upper() == "TABLE":
            st.table = _clean_ident(m.group(4))
        else:
            st.index = _clean_ident(m.group(4))
        return st
    m = re.match(r"CLUSTER\s+(VERBOSE\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "cluster"
        st.table = _clean_ident(m.group(2))
        return st
    if re.match(r"VACUUM\b.*\bFULL\b", u):
        st.kind = "vacuum_full"
        m = re.search(r"VACUUM\s*(\([^)]*\))?\s*(FULL\s+)?(VERBOSE\s+)?(ANALYZE\s+)?" + _ident, s, re.I)
        st.table = _clean_ident(m.group(5)) if m and m.group(5) else None
        return st

    m = re.match(r"CREATE\s+(GLOBAL\s+|LOCAL\s+)?(TEMP(?:ORARY)?\s+|UNLOGGED\s+)?TABLE\s+(IF\s+NOT\s+EXISTS\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "create_table"
        st.table = _clean_ident(m.group(4))
        return st
    m = re.match(r"DROP\s+TABLE\s+(IF\s+EXISTS\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "drop_table"
        st.table = _clean_ident(m.group(2))
        return st
    m = re.match(r"TRUNCATE\s+(TABLE\s+)?(ONLY\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "truncate"
        st.table = _clean_ident(m.group(3))
        return st

    m = re.match(r"ALTER\s+TABLE\s+(IF\s+EXISTS\s+)?(ONLY\s+)?" + _ident + r"\s+(.*)$", s, re.I | re.S)
    if m:
        st.table = _clean_ident(m.group(3))
        rest = m.group(4).strip()
        ru = rest.upper()
        # Multiple sub-actions in one ALTER TABLE: keep the first for classification but note the count.
        st.attrs["actions"] = len(re.findall(r"(?:^|,\s*)(ADD|DROP|ALTER|RENAME|VALIDATE)\b", ru))
        mm = re.match(r"RENAME\s+TO\s+" + _ident, rest, re.I)
        if mm:
            st.kind = "rename_table"
            st.attrs["new_name"] = _clean_ident(mm.group(1))
            return st
        mm = re.match(r"RENAME\s+(COLUMN\s+)?" + _ident + r"\s+TO\s+" + _ident, rest, re.I)
        if mm:
            st.kind = "rename_column"
            st.columns = [_clean_ident(mm.group(2))]
            st.attrs["new_name"] = _clean_ident(mm.group(3))
            return st
        mm = re.match(r"DROP\s+(COLUMN\s+)?(IF\s+EXISTS\s+)?" + _ident, rest, re.I)
        if mm and not ru.startswith("DROP CONSTRAINT"):
            st.kind = "drop_column"
            st.columns = [_clean_ident(mm.group(3))]
            return st
        mm = re.match(r"DROP\s+CONSTRAINT\s+(IF\s+EXISTS\s+)?" + _ident, rest, re.I)
        if mm:
            st.kind = "drop_constraint"
            st.constraint = _clean_ident(mm.group(2))
            return st
        mm = re.match(r"VALIDATE\s+CONSTRAINT\s+" + _ident, rest, re.I)
        if mm:
            st.kind = "validate_constraint"
            st.constraint = _clean_ident(mm.group(1))
            return st
        mm = re.match(r"ADD\s+(COLUMN\s+)?(IF\s+NOT\s+EXISTS\s+)?" + _ident + r"\s+(.*)$", rest, re.I | re.S)
        if mm and not re.match(r"ADD\s+(CONSTRAINT|PRIMARY|UNIQUE|FOREIGN|CHECK|EXCLUDE)\b", rest, re.I):
            st.kind = "add_column"
            st.columns = [_clean_ident(mm.group(3))]
            tail = mm.group(4)
            st.attrs["not_null"] = bool(re.search(r"\bNOT\s+NULL\b", tail, re.I))
            dm = re.search(r"\bDEFAULT\s+(.+?)(?:\s+(?:NOT\s+NULL|NULL|CONSTRAINT|CHECK|REFERENCES|UNIQUE|PRIMARY|GENERATED|COLLATE)\b|$)", tail, re.I)
            if dm:
                st.attrs["default"] = dm.group(1).strip()
                st.attrs["default_volatile"] = bool(VOLATILE_DEFAULT_RE.search(dm.group(1)))
            st.attrs["generated_identity"] = bool(re.search(r"GENERATED\s+(ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY", tail, re.I))
            st.attrs["type"] = tail.split()[0].lower() if tail.split() else None
            return st
        mm = re.match(r"ADD\s+(CONSTRAINT\s+" + _ident + r"\s+)?(PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK|EXCLUDE)\b(.*)$", rest, re.I | re.S)
        if mm:
            st.constraint = _clean_ident(mm.group(2)) if mm.group(2) else None
            ctype = re.sub(r"\s+", " ", mm.group(3).upper())
            tail = mm.group(4)
            st.attrs["not_valid"] = bool(re.search(r"\bNOT\s+VALID\b", tail, re.I))
            st.attrs["using_index"] = bool(re.search(r"\bUSING\s+INDEX\b", tail, re.I))
            if ctype == "PRIMARY KEY":
                st.kind = "add_pk"
            elif ctype == "UNIQUE":
                st.kind = "add_unique"
            elif ctype == "FOREIGN KEY":
                st.kind = "add_fk"
            elif ctype == "CHECK":
                st.kind = "add_check"
                st.attrs["is_not_null_check"] = bool(re.search(r"\bIS\s+NOT\s+NULL\b", tail, re.I))
            else:
                st.kind = "add_check"
            st.columns = _cols_from_paren(tail)
            return st
        mm = re.match(r"ALTER\s+(COLUMN\s+)?" + _ident + r"\s+(.*)$", rest, re.I | re.S)
        if mm:
            st.columns = [_clean_ident(mm.group(2))]
            action = mm.group(3)
            au = action.upper()
            if re.match(r"SET\s+NOT\s+NULL", au):
                st.kind = "set_not_null"
            elif re.match(r"DROP\s+NOT\s+NULL", au):
                st.kind = "drop_not_null"
            elif re.match(r"(SET\s+DATA\s+)?TYPE\b", au):
                st.kind = "alter_column_type"
                tm = re.match(r"(?:SET\s+DATA\s+)?TYPE\s+(.+?)(?:\s+USING\b|$)", action, re.I | re.S)
                st.attrs["new_type"] = tm.group(1).strip().lower() if tm else None
                st.attrs["using"] = bool(re.search(r"\bUSING\b", action, re.I))
            elif re.match(r"SET\s+DEFAULT", au):
                st.kind = "set_default"
                st.attrs["default"] = action[len("SET DEFAULT"):].strip()
                st.attrs["default_volatile"] = bool(VOLATILE_DEFAULT_RE.search(action))
            elif re.match(r"DROP\s+DEFAULT", au):
                st.kind = "drop_default"
            else:
                st.kind = "unknown"
            return st
        st.kind = "unknown"
        return st

    m = re.match(r"UPDATE\s+(ONLY\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "update"
        st.table = _clean_ident(m.group(2))
        st.attrs["has_where"] = bool(re.search(r"\bWHERE\b", u))
        wm = re.search(r"\bWHERE\b(.*)$", s, re.I | re.S)
        st.attrs["where"] = wm.group(1).strip() if wm else ""

        st.attrs["batched"] = bool(re.search(r"\bLIMIT\b|\bCTID\b|\bBETWEEN\b", u))
        return st
    m = re.match(r"DELETE\s+FROM\s+(ONLY\s+)?" + _ident, s, re.I)
    if m:
        st.kind = "delete"
        st.table = _clean_ident(m.group(2))
        st.attrs["has_where"] = bool(re.search(r"\bWHERE\b", u))
        wm = re.search(r"\bWHERE\b(.*)$", s, re.I | re.S)
        st.attrs["where"] = wm.group(1).strip() if wm else ""

        st.attrs["batched"] = bool(re.search(r"\bLIMIT\b|\bCTID\b|\bBETWEEN\b", u))
        return st
    m = re.match(r"INSERT\s+INTO\s+" + _ident, s, re.I)
    if m:
        st.kind = "insert"
        st.table = _clean_ident(m.group(1))
        st.attrs["from_select"] = bool(re.search(r"\bSELECT\b", u))
        return st
    if re.match(r"(SELECT|WITH)\b", u):
        st.kind = "select"
        return st
    if re.match(r"CREATE\s+(OR\s+REPLACE\s+)?(VIEW|MATERIALIZED\s+VIEW)\b", u):
        st.kind = "create_view"
        st.attrs["materialized"] = "MATERIALIZED" in u
        return st
    if re.match(r"CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE|TRIGGER)\b", u):
        st.kind = "create_function"
        return st
    if re.match(r"CREATE\s+SEQUENCE\b", u):
        st.kind = "create_sequence"
        return st
    if re.match(r"COMMENT\s+ON\b", u):
        st.kind = "comment"
        return st
    if re.match(r"(BEGIN|COMMIT|END|START\s+TRANSACTION)\b", u):
        st.kind = "noop"
        return st
    return st


# --------------------------------------------------------------------------- Liquibase change tags

def _bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")


def change_to_statements(tag: str, a: dict[str, Any], cols: list[dict[str, Any]], text: str | None,
                         base_dir: str, notes: list[str]) -> list[Statement]:
    """Translate one Liquibase change (XML tag / YAML key) into Statements.

    `a` are the change attributes, `cols` the <column> children as dicts
    (each with 'name', 'type', 'constraints', 'defaultValue*' keys), `text` the
    element text for <sql>.
    """
    t = a.get("tableName") or a.get("baseTableName")
    table = _clean_ident(t) if t else None
    out: list[Statement] = []

    def st(kind: str, **kw: Any) -> Statement:
        s = Statement(kind=kind, table=table, raw=f"<{tag}> {sorted(a.items())} {cols}", source="change")
        for k, v in kw.items():
            setattr(s, k, v)
        return s

    if tag == "sql":
        for piece in split_sql(text or ""):
            out.append(classify_sql(piece))
        return out
    if tag == "sqlFile":
        path = a.get("path", "")
        candidates = [os.path.join(base_dir, path), path]
        for c in candidates:
            if os.path.isfile(c):
                with open(c, encoding=a.get("encoding", "utf-8"), errors="replace") as fh:
                    for piece in split_sql(fh.read()):
                        s = classify_sql(piece)
                        s.attrs["from_file"] = path
                        out.append(s)
                return out
        notes.append(f"sqlFile '{path}' not found; its statements were NOT analysed")
        s = st("unknown")
        s.raw = f"sqlFile path={path} (unresolved)"
        return [s]

    if tag == "createTable":
        return [st("create_table", columns=[_clean_ident(c.get("name")) for c in cols])]
    if tag == "dropTable":
        return [st("drop_table")]
    if tag == "renameTable":
        s = st("rename_table")
        s.table = _clean_ident(a.get("oldTableName"))
        s.attrs["new_name"] = _clean_ident(a.get("newTableName"))
        return [s]
    if tag == "addColumn":
        for c in cols:
            s = st("add_column", columns=[_clean_ident(c.get("name"))])
            cons = c.get("constraints") or {}
            s.attrs["not_null"] = not _bool(cons.get("nullable"), True)
            s.attrs["type"] = (c.get("type") or "").lower()
            default = None
            for k in ("defaultValue", "defaultValueNumeric", "defaultValueBoolean", "defaultValueDate",
                      "defaultValueComputed", "defaultValueSequenceNext"):
                if c.get(k) is not None:
                    default = str(c.get(k))
                    break
            if default is not None:
                s.attrs["default"] = default
                s.attrs["default_volatile"] = bool(VOLATILE_DEFAULT_RE.search(default)) or c.get("defaultValueSequenceNext") is not None
            s.attrs["generated_identity"] = _bool(c.get("autoIncrement"))
            out.append(s)
        return out
    if tag == "dropColumn":
        names = [_clean_ident(a["columnName"])] if a.get("columnName") else [_clean_ident(c.get("name")) for c in cols]
        return [st("drop_column", columns=[n]) for n in names]
    if tag == "renameColumn":
        s = st("rename_column", columns=[_clean_ident(a.get("oldColumnName"))])
        s.attrs["new_name"] = _clean_ident(a.get("newColumnName"))
        return [s]
    if tag == "modifyDataType":
        s = st("alter_column_type", columns=[_clean_ident(a.get("columnName"))])
        s.attrs["new_type"] = (a.get("newDataType") or "").lower()
        return [s]
    if tag == "addNotNullConstraint":
        s = st("set_not_null", columns=[_clean_ident(a.get("columnName"))])
        s.attrs["default_null_value"] = a.get("defaultNullValue")
        s.attrs["validate"] = _bool(a.get("validate"), True)
        return [s]
    if tag == "dropNotNullConstraint":
        return [st("drop_not_null", columns=[_clean_ident(a.get("columnName"))])]
    if tag == "addDefaultValue":
        s = st("set_default", columns=[_clean_ident(a.get("columnName"))])
        d = a.get("defaultValueComputed") or a.get("defaultValue") or ""
        s.attrs["default"] = d
        s.attrs["default_volatile"] = bool(VOLATILE_DEFAULT_RE.search(str(d)))
        return [s]
    if tag == "dropDefaultValue":
        return [st("drop_default", columns=[_clean_ident(a.get("columnName"))])]
    if tag == "createIndex":
        s = st("create_index", index=_clean_ident(a.get("indexName")), columns=[_clean_ident(c.get("name")) for c in cols])
        s.attrs["unique"] = _bool(a.get("unique"))
        s.attrs["concurrently"] = False   # plain createIndex never emits CONCURRENTLY; modifySql may append it
        return [s]
    if tag == "dropIndex":
        s = st("drop_index", index=_clean_ident(a.get("indexName")))
        s.attrs["concurrently"] = False
        return [s]
    if tag == "addForeignKeyConstraint":
        s = st("add_fk", constraint=_clean_ident(a.get("constraintName")))
        s.columns = [_clean_ident(c) for c in (a.get("baseColumnNames") or "").split(",") if c.strip()]
        s.attrs["not_valid"] = not _bool(a.get("validate"), True)
        s.attrs["referenced_table"] = _clean_ident(a.get("referencedTableName"))
        return [s]
    if tag == "dropForeignKeyConstraint":
        return [st("drop_constraint", constraint=_clean_ident(a.get("constraintName")))]
    if tag == "addUniqueConstraint":
        s = st("add_unique", constraint=_clean_ident(a.get("constraintName")))
        s.columns = [_clean_ident(c) for c in (a.get("columnNames") or "").split(",") if c.strip()]
        s.attrs["using_index"] = bool(a.get("forIndexName"))
        return [s]
    if tag == "dropUniqueConstraint":
        return [st("drop_constraint", constraint=_clean_ident(a.get("constraintName")))]
    if tag == "addPrimaryKey":
        s = st("add_pk", constraint=_clean_ident(a.get("constraintName")))
        s.columns = [_clean_ident(c) for c in (a.get("columnNames") or "").split(",") if c.strip()]
        s.attrs["using_index"] = bool(a.get("forIndexName"))
        return [s]
    if tag == "dropPrimaryKey":
        return [st("drop_constraint", constraint=_clean_ident(a.get("constraintName")))]
    if tag == "addCheckConstraint":
        s = st("add_check", constraint=_clean_ident(a.get("constraintName")))
        s.attrs["not_valid"] = not _bool(a.get("validate"), True)
        return [s]
    if tag == "update":
        s = st("update")
        s.attrs["has_where"] = bool(a.get("where"))
        s.attrs["where"] = str(a.get("where") or "")
        s.attrs["batched"] = False
        return [s]
    if tag == "delete":
        s = st("delete")
        s.attrs["has_where"] = bool(a.get("where"))
        s.attrs["where"] = str(a.get("where") or "")
        s.attrs["batched"] = False
        return [s]
    if tag in ("insert", "loadData", "loadUpdateData"):
        return [st("insert")]
    if tag in ("createSequence", "alterSequence", "dropSequence"):
        return [st("create_sequence")]
    if tag in ("createView", "dropView"):
        return [st("create_view")]
    if tag in ("createProcedure", "dropProcedure"):
        return [st("create_function")]
    if tag in ("setTableRemarks", "setColumnRemarks", "tagDatabase", "empty", "output", "stop"):
        return [st("noop")]
    if tag in ("customChange", "executeCommand", "mergeColumns", "addLookupTable", "addAutoIncrement"):
        notes.append(f"<{tag}> cannot be analysed statically")
        return [st("unknown")]
    notes.append(f"unrecognised change <{tag}>")
    return [st("unknown")]


# --------------------------------------------------------------------------- XML

def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _line_of(text: str, needle_patterns: list[str]) -> int:
    for pat in needle_patterns:
        m = re.search(pat, text)
        if m:
            return text.count("\n", 0, m.start()) + 1
    return 1


def _xml_column_dicts(el: ET.Element) -> list[dict[str, Any]]:
    cols = []
    for c in el:
        if _strip_ns(c.tag) != "column":
            continue
        d: dict[str, Any] = dict(c.attrib)
        for cc in c:
            if _strip_ns(cc.tag) == "constraints":
                d["constraints"] = dict(cc.attrib)
        cols.append(d)
    return cols


def parse_xml(path: str) -> list[ChangeSet]:
    text = open(path, encoding="utf-8", errors="replace").read()
    root = ET.fromstring(text)
    base_dir = os.path.dirname(os.path.abspath(path))
    out: list[ChangeSet] = []
    for el in root.iter():
        if _strip_ns(el.tag) != "changeSet":
            continue
        a = el.attrib
        cs = ChangeSet(
            id=a.get("id", "?"), author=a.get("author", "?"), file=path,
            line=_line_of(text, [rf'id\s*=\s*"{re.escape(a.get("id", "?"))}"']), fmt="xml",
            run_in_transaction=_bool(a.get("runInTransaction"), True),
            run_on_change=_bool(a.get("runOnChange")), run_always=_bool(a.get("runAlways")),
            context=a.get("context") or a.get("contextFilter"), labels=a.get("labels"), dbms=a.get("dbms"),
        )
        modify_sql_text = ""
        for child in el:
            tag = _strip_ns(child.tag)
            if tag == "preConditions":
                cs.has_preconditions = True
            elif tag == "rollback":
                cs.has_rollback = True
            elif tag == "validCheckSum":
                cs.valid_checksums.append((child.text or "").strip())
            elif tag == "comment":
                pass
            elif tag == "modifySql":
                modify_sql_text += " ".join((g.attrib.get("value") or "") + (g.text or "") for g in child.iter())
            else:
                attrs = dict(child.attrib)
                for g in child:
                    if _strip_ns(g.tag) == "where":
                        attrs["where"] = (g.text or "").strip()
                cs.statements.extend(change_to_statements(tag, attrs, _xml_column_dicts(child),
                                                          child.text, base_dir, cs.parse_notes))
        if "CONCURRENTLY" in modify_sql_text.upper():
            for s in cs.statements:
                if s.kind in ("create_index", "drop_index"):
                    s.attrs["concurrently"] = True
        out.append(cs)
    return out


# --------------------------------------------------------------------------- YAML

def parse_yaml(path: str) -> list[ChangeSet]:
    import yaml  # provided by the PEP 723 header of the entry script
    text = open(path, encoding="utf-8", errors="replace").read()
    doc = yaml.safe_load(text) or {}
    base_dir = os.path.dirname(os.path.abspath(path))
    out: list[ChangeSet] = []
    for entry in doc.get("databaseChangeLog") or []:
        if not isinstance(entry, dict) or "changeSet" not in entry:
            continue
        c = entry["changeSet"] or {}
        cid = str(c.get("id", "?"))
        cs = ChangeSet(
            id=cid, author=str(c.get("author", "?")), file=path,
            line=_line_of(text, [rf"id:\s*['\"]?{re.escape(cid)}['\"]?\s*$", rf"id:\s*['\"]?{re.escape(cid)}"]), fmt="yaml",
            run_in_transaction=_bool(c.get("runInTransaction"), True),
            run_on_change=_bool(c.get("runOnChange")), run_always=_bool(c.get("runAlways")),
            context=c.get("context") or c.get("contextFilter"), labels=c.get("labels"), dbms=c.get("dbms"),
        )
        cs.has_preconditions = bool(c.get("preConditions"))
        cs.has_rollback = "rollback" in c
        vc = c.get("validCheckSum")
        if vc:
            cs.valid_checksums = [str(v) for v in (vc if isinstance(vc, list) else [vc])]
        modify_sql_text = ""
        for ms in c.get("modifySql") or []:
            modify_sql_text += str(ms)
        for change in c.get("changes") or []:
            if not isinstance(change, dict):
                continue
            for tag, body in change.items():
                attrs: dict[str, Any] = {}
                cols: list[dict[str, Any]] = []
                sql_text = None
                if isinstance(body, str):
                    sql_text = body
                elif isinstance(body, dict):
                    attrs = {k: v for k, v in body.items() if k != "columns"}
                    for col in body.get("columns") or []:
                        cd = col.get("column", col) if isinstance(col, dict) else {}
                        cols.append(cd)
                    if tag == "sql":
                        sql_text = body.get("sql", "")
                cs.statements.extend(change_to_statements(tag, attrs, cols, sql_text, base_dir, cs.parse_notes))
        if "CONCURRENTLY" in modify_sql_text.upper():
            for s in cs.statements:
                if s.kind in ("create_index", "drop_index"):
                    s.attrs["concurrently"] = True
        out.append(cs)
    return out


# --------------------------------------------------------------------------- formatted SQL

_CS_RE = re.compile(r"^\s*--\s*changeset\s+([^:\s]+):(\S+)(.*)$", re.I)


def parse_formatted_sql(path: str) -> list[ChangeSet]:
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = text.splitlines()
    out: list[ChangeSet] = []
    cur: ChangeSet | None = None
    body: list[str] = []
    split_statements = True

    def flush() -> None:
        nonlocal cur, body
        if cur is None:
            return
        sql = "\n".join(body)
        pieces = split_sql(sql) if split_statements else ([sql.strip()] if sql.strip() else [])
        for p in pieces:
            cur.statements.append(classify_sql(p))
        out.append(cur)
        cur, body = None, []

    for i, line in enumerate(lines, start=1):
        m = _CS_RE.match(line)
        if m:
            flush()
            attrs = dict(re.findall(r"(\w+):(\S+)", m.group(3)))
            cur = ChangeSet(
                id=m.group(2), author=m.group(1), file=path, line=i, fmt="sql",
                run_in_transaction=_bool(attrs.get("runInTransaction"), True),
                run_on_change=_bool(attrs.get("runOnChange")), run_always=_bool(attrs.get("runAlways")),
                context=attrs.get("context") or attrs.get("contextFilter"), labels=attrs.get("labels"), dbms=attrs.get("dbms"),
            )
            split_statements = _bool(attrs.get("splitStatements"), True)
            continue
        if cur is None:
            continue
        s = line.strip()
        if re.match(r"--\s*rollback\b", s, re.I):
            cur.has_rollback = True
            continue
        if re.match(r"--\s*precondition", s, re.I):
            cur.has_preconditions = True
            continue
        mm = re.match(r"--\s*validCheckSum:?\s*(\S+)", s, re.I)
        if mm:
            cur.valid_checksums.append(mm.group(1))
            continue
        if s.startswith("--"):
            continue
        body.append(line)
    flush()
    return out


# --------------------------------------------------------------------------- entry

def detect_format(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xml":
        return "xml"
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext == ".sql":
        try:
            head = open(path, encoding="utf-8", errors="replace").read(4096)
        except OSError:
            return None
        return "sql" if re.search(r"--\s*liquibase\s+formatted\s+sql", head, re.I) else None
    return None


def looks_like_changelog(path: str) -> bool:
    fmt = detect_format(path)
    if fmt is None:
        return False
    if fmt == "sql":
        return True
    try:
        head = open(path, encoding="utf-8", errors="replace").read(8192)
    except OSError:
        return False
    return "databaseChangeLog" in head


def parse_file(path: str) -> list[ChangeSet]:
    fmt = detect_format(path)
    if fmt == "xml":
        return parse_xml(path)
    if fmt == "yaml":
        return parse_yaml(path)
    if fmt == "sql":
        return parse_formatted_sql(path)
    return []
