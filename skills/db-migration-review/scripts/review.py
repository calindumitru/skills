#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""db-migration-review: grade Liquibase changesets by blue-green risk on a hot Postgres database.

Usage (run from the repo root):
  review.py                              # new changelog files vs the base branch (default mode)
  review.py path/to/changelog.xml ...    # explicit files (also detects edits to already-applied changesets)
  review.py --format md --output report.md --fail-on critical

Exit code: 0 when no finding reaches --fail-on, 2 otherwise, 1 on usage/parse errors.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liquibase_parser import ChangeSet, parse_file, looks_like_changelog, detect_format  # noqa: E402
from rules import (Finding, LEVELS, LEVEL_RANK, build_context, run_rules, catalog)  # noqa: E402

CONFIG_NAMES = [".db-migration-review.toml", "db-migration-review.toml"]
DEFAULT_SOURCE_DIRS = ["src/main/kotlin", "src/main/java", "src/main/resources"]
SOURCE_EXTS = (".kt", ".java", ".xml", ".sql", ".kts", ".properties", ".yml", ".yaml")


# --------------------------------------------------------------------------- helpers

def git(root: str, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def find_root(start: str) -> str:
    top = git(start, "rev-parse", "--show-toplevel").strip()
    return top or os.path.abspath(start)


def load_config(root: str, explicit: str | None) -> dict[str, Any]:
    paths = [explicit] if explicit else [os.path.join(root, n) for n in CONFIG_NAMES]
    for p in paths:
        if p and os.path.isfile(p):
            with open(p, "rb") as fh:
                return tomllib.load(fh)
    return {}


def detect_base(root: str, configured: str | None) -> str | None:
    if configured:
        return configured
    head = git(root, "symbolic-ref", "refs/remotes/origin/HEAD").strip()
    if head:
        return head.replace("refs/remotes/", "")
    for cand in ("origin/main", "origin/master", "origin/develop", "main", "master", "develop"):
        if git(root, "rev-parse", "--verify", "--quiet", cand).strip():
            return cand
    return None


def discover_new_files(root: str, base: str | None, changelog_dirs: list[str]) -> list[str]:
    files: set[str] = set()
    if base:
        mb = git(root, "merge-base", base, "HEAD").strip() or base
        files.update(git(root, "diff", "--name-only", "--diff-filter=A", mb, "HEAD").split())
    files.update(git(root, "diff", "--name-only", "--diff-filter=A", "--cached").split())
    files.update(git(root, "ls-files", "--others", "--exclude-standard").split())
    out = []
    for rel in sorted(files):
        if changelog_dirs and not any(rel.startswith(d.rstrip("/") + "/") or rel == d for d in changelog_dirs):
            continue
        abs_p = os.path.join(root, rel)
        if os.path.isfile(abs_p) and looks_like_changelog(abs_p):
            out.append(abs_p)
    return out


def modified_changesets(root: str, path: str, base: str | None, current: list[ChangeSet]) -> list[Finding]:
    """Compare an explicitly named file with its version on the base branch."""
    if not base:
        return []
    rel = os.path.relpath(path, root)
    mb = git(root, "merge-base", base, "HEAD").strip() or base
    old_text = git(root, "show", f"{mb}:{rel}")
    if not old_text:
        return []
    import tempfile
    suffix = os.path.splitext(path)[1]
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as tmp:
        tmp.write(old_text)
        tmp_path = tmp.name
    try:
        old = {cs.key: cs for cs in parse_file(tmp_path)}
    finally:
        os.unlink(tmp_path)
    out = []
    for cs in current:
        prev = old.get(cs.key)
        if prev is None or prev.signature() == cs.signature() or cs.run_on_change:
            continue
        if cs.valid_checksums:
            continue
        out.append(Finding(rule="LB-CHK-001", level="CRITICAL", title="Already-applied changeset was modified",
            file=cs.file, line=cs.line, changeset=cs.key,
            consequence=f"`{cs.key}` exists on `{base}` with a different body. If it has run in any environment, "
                        f"Liquibase fails validation with a checksum mismatch at startup and the deploy halts.",
            fix="Revert the edit and add a new changeset with the intended change. Only if the changeset has never run "
                "anywhere may it be edited; if it must be, add `<validCheckSum>ANY</validCheckSum>` deliberately and say why.",
            evidence=["old: " + prev.signature()[:300], "new: " + cs.signature()[:300]]))
    return out


def grep_evidence(root: str, source_dirs: list[str], needle: str, exclude_paths: set[str], limit: int = 12) -> list[str]:
    """Cheap code lookup: where does the identifier appear in application sources?"""
    if not needle:
        return []
    pat = re.compile(r"(?<![\w$])" + re.escape(needle) + r"(?![\w$])", re.I)
    camel = re.compile(r"(?<![\w$])" + re.escape(_snake_to_camel(needle)) + r"(?![\w$])")
    hits: list[str] = []
    for d in source_dirs:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in ("build", "target", ".git", "node_modules")]
            for fn in filenames:
                if not fn.endswith(SOURCE_EXTS):
                    continue
                p = os.path.join(dirpath, fn)
                if os.path.abspath(p) in exclude_paths or "changelog" in p.lower() or "migration" in p.lower():
                    continue
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        for i, line in enumerate(fh, start=1):
                            if pat.search(line) or (needle != _snake_to_camel(needle) and camel.search(line)):
                                hits.append(f"{os.path.relpath(p, root)}:{i}: {line.strip()[:140]}")
                                if len(hits) >= limit:
                                    return hits
                except OSError:
                    continue
    return hits


def _snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# --------------------------------------------------------------------------- report

MERGEABLE_RULES = {"PG-LOCK-001"}


def merge_repeats(findings: list[Finding]) -> list[Finding]:
    """Collapse identical-advice findings (e.g. missing lock_timeout) into one per file."""
    out: list[Finding] = []
    groups: dict[tuple[str, str], Finding] = {}
    for f in findings:
        if f.rule not in MERGEABLE_RULES:
            out.append(f)
            continue
        key = (f.rule, f.file)
        if key in groups:
            g = groups[key]
            g.changeset += f", {f.changeset}"
            if f.table and f.table != g.table:
                g.notes.append(f"also `{f.table}` in `{f.changeset}`")
        else:
            groups[key] = f
            out.append(f)
    return out


def verdict_for(findings: list[Finding]) -> str:
    if any(f.level == "CRITICAL" for f in findings):
        return "BLOCK"
    if any(f.level == "HIGH" for f in findings):
        return "NEEDS PLAN"
    if any(f.level == "MEDIUM" for f in findings):
        return "REVIEW"
    return "SAFE"


def tldr(findings: list[Finding], n_files: int, n_cs: int, verdict: str) -> str:
    counts = {lv: sum(1 for f in findings if f.level == lv) for lv in LEVELS}
    if verdict == "SAFE":
        return (f"Safe to deploy blue-green. {n_cs} changeset(s) in {n_files} file(s) reviewed, nothing beyond hygiene"
                + (f" ({counts['LOW']} low)." if counts["LOW"] else "."))
    top = []
    seen = set()
    for f in findings:
        if f.level in ("CRITICAL", "HIGH") and f.title not in seen:
            seen.add(f.title)
            t = f.title
            top.append(t[0].lower() + t[1:] if len(t) > 1 and t[1].islower() else t)
        if len(top) == 3:
            break
    lead = {"BLOCK": "Do not deploy as is.", "NEEDS PLAN": "Deployable only with a plan.",
            "REVIEW": "Deployable, but review the medium findings."}[verdict]
    what = "; ".join(top) if top else "see medium findings"
    return (f"{lead} Main problems: {what}. Fix the critical and high findings first; the fixes below are "
            f"copy-ready and keep the old app version working during the switch.")


def render_md(report: dict[str, Any]) -> str:
    L = []
    c = report["counts"]
    L.append("# DB migration review (blue-green safety)\n")
    L.append(f"**Verdict: {report['verdict']}** — {c['CRITICAL']} critical, {c['HIGH']} high, {c['MEDIUM']} medium, "
             f"{c['LOW']} low across {len(report['files'])} file(s) / {report['changeset_count']} changeset(s).  ")
    L.append(f"Target: {report['target']}. Mode: {report['mode']}.\n")
    L.append("| Level | Count | Meaning during blue-green deploy |")
    L.append("|---|---|---|")
    L.append(f"| CRITICAL | {c['CRITICAL']} | Breaks production, halts the deploy, or breaks the old app version still serving traffic |")
    L.append(f"| HIGH | {c['HIGH']} | Likely stall or outage under load; needs a plan |")
    L.append(f"| MEDIUM | {c['MEDIUM']} | Deploys, but violates expand/contract, leaves a trap, or cannot be undone |")
    L.append(f"| LOW | {c['LOW']} | Hygiene |\n")
    L.append(f"**TL;DR:** {report['tldr']}\n")
    if report.get("notes"):
        L.append("> " + "\n> ".join(report["notes"]) + "\n")
    L.append("---\n")
    counters = {lv: 0 for lv in LEVELS}
    for lv in LEVELS:
        fs = [f for f in report["findings"] if f["level"] == lv]
        if not fs:
            continue
        L.append(f"## {lv}\n")
        for f in fs:
            counters[lv] += 1
            tag = f"{lv[0]}{counters[lv]}"
            L.append(f"### {tag} · {f['title']} — `{f['rule']}`")
            L.append(f"`{f['file']}:{f['line']}` · changeset `{f['changeset']}`"
                     + (f" · table `{f['table']}`" if f.get("table") else "")
                     + (f" · column `{f['column']}`" if f.get("column") else "") + "\n")
            L.append(f"**What happens in production:** {f['consequence']}\n")
            L.append(f"**Fix:** {f['fix']}\n")
            if f.get("evidence"):
                L.append("**Code lookup:**")
                for e in f["evidence"]:
                    L.append(f"- `{e}`")
                L.append("")
            if f.get("needs_model_review"):
                L.append("_Needs a human/model judgement: confirm whether the still-deployed app version references this._\n")
            for n in f.get("notes", []):
                L.append(f"_Note: {n}_\n")
    if report["unreviewed"]:
        L.append("## Unreviewed statements (manual check needed)\n")
        for u in report["unreviewed"]:
            L.append(f"- `{u['file']}:{u['line']}` `{u['changeset']}`: {u['reason']}\n  ```sql\n  {u['raw'][:300]}\n  ```")
        L.append("")
    if report["passed"]:
        L.append("## Passed\n")
        for p in report["passed"]:
            L.append(f"- `{p['file']}:{p['line']}` · `{p['changeset']}` — {p['summary']} ✔")
        L.append("")
    if report.get("rollout"):
        L.append("## Suggested rollout order\n")
        for i, step in enumerate(report["rollout"], start=1):
            L.append(f"{i}. {step}")
        L.append("")
    return "\n".join(L)


def summarize_changeset(cs: ChangeSet) -> str:
    kinds = []
    for s in cs.statements:
        label = s.kind.replace("_", " ")
        if s.table:
            label += f" {s.table}"
        if s.columns and s.kind != "create_table":
            label += f".{','.join(s.columns)}"
        if s.attrs.get("concurrently"):
            label += " (concurrently)"
        kinds.append(label)
    return ", ".join(kinds) or "no statements"


def rollout_plan(findings: list[Finding], changesets: list[ChangeSet]) -> list[str]:
    contract = {f.changeset for f in findings if f.rule.startswith("BG-CONTRACT")}
    if not contract:
        return []
    expand = [cs.key for cs in changesets if cs.key not in contract]
    steps = []
    if expand:
        steps.append("Release N (expand): " + ", ".join(f"`{k}`" for k in expand) + " with the fixes above applied.")
    steps.append("Release N+1 (contract), only after no deployed version references the dropped/renamed objects: "
                 + ", ".join(f"`{k}`" for k in sorted(contract)) + ".")
    return steps


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="changelog files to review (default: new files vs base branch)")
    ap.add_argument("--root", default=".", help="repo root or any path inside it")
    ap.add_argument("--base", help="base branch/ref (default: config, origin/HEAD, main, master, develop)")
    ap.add_argument("--config", help="path to a .db-migration-review.toml")
    ap.add_argument("--format", choices=["json", "md", "both"], default="json")
    ap.add_argument("--output", help="write the report here (with --format both: <output>.json and <output>.md)")
    ap.add_argument("--fail-on", choices=[lv.lower() for lv in LEVELS] + ["none"], default="critical")
    ap.add_argument("--no-git", action="store_true", help="never call git (explicit files only)")
    ap.add_argument("--no-grep", action="store_true", help="skip the source-code lookup for contract changes")
    ap.add_argument("--list-rules", action="store_true")
    args = ap.parse_args(argv)

    if args.list_rules:
        for r in catalog():
            print(f"{r['id']:16} {r['level']:9} {r['name']}")
        return 0

    root = find_root(args.root) if not args.no_git else os.path.abspath(args.root)
    config = load_config(root, args.config)
    base = None if args.no_git else detect_base(root, args.base or config.get("git", {}).get("base_branch"))
    changelog_dirs = list(config.get("changelogs", {}).get("dirs") or [])
    source_dirs = list(config.get("source", {}).get("dirs") or DEFAULT_SOURCE_DIRS)
    notes: list[str] = []

    if args.files:
        files = [os.path.abspath(f) for f in args.files]
        mode = "explicit files"
        missing = [f for f in files if not os.path.isfile(f)]
        if missing:
            print("not found: " + ", ".join(missing), file=sys.stderr)
            return 1
    else:
        if args.no_git:
            print("--no-git requires explicit files", file=sys.stderr)
            return 1
        files = discover_new_files(root, base, changelog_dirs)
        mode = f"new changelog files vs {base or 'working tree'}"
        if not files:
            notes.append("No new changelog files found. Pass file paths explicitly to review specific files.")

    changesets: list[ChangeSet] = []
    extra_findings: list[Finding] = []
    for f in files:
        if detect_format(f) is None:
            notes.append(f"{os.path.relpath(f, root)}: not a recognised Liquibase changelog (xml/yaml/formatted sql); skipped.")
            continue
        try:
            parsed = parse_file(f)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{os.path.relpath(f, root)}: parse error: {exc}")
            continue
        changesets.extend(parsed)
        if args.files and not args.no_git:
            extra_findings.extend(modified_changesets(root, f, base, parsed))

    ctx = build_context(changesets, config)
    findings = extra_findings + run_rules(changesets, ctx)
    findings = merge_repeats(findings)
    findings.sort(key=lambda x: (LEVEL_RANK.get(x.level, 9), x.file, x.line, x.rule))

    if not args.no_grep:
        exclude = {os.path.abspath(f) for f in files}
        for fd in findings:
            if fd.needs_model_review:
                needle = fd.column or fd.table
                fd.evidence.extend(grep_evidence(root, source_dirs, needle, exclude))
                if fd.column and fd.table:
                    fd.evidence.extend(h for h in grep_evidence(root, source_dirs, fd.table, exclude, limit=4)
                                       if h not in fd.evidence)
                if not fd.evidence:
                    fd.notes.append(f"No reference to `{needle}` found under {', '.join(source_dirs)}. Confirm the "
                                    f"currently deployed version does not use it either (check the release branch).")

    flagged = {f.changeset for f in findings}
    passed = [{"file": os.path.relpath(cs.file, root), "line": cs.line, "changeset": cs.key, "summary": summarize_changeset(cs)}
              for cs in changesets if cs.key not in flagged]
    unreviewed = []
    for cs in changesets:
        for s in cs.statements:
            if s.kind == "unknown":
                unreviewed.append({"file": os.path.relpath(cs.file, root), "line": cs.line, "changeset": cs.key,
                                   "reason": "statement not classified; judge it against rules/CATALOG.md", "raw": s.raw})
        for n in cs.parse_notes:
            unreviewed.append({"file": os.path.relpath(cs.file, root), "line": cs.line, "changeset": cs.key,
                               "reason": n, "raw": ""})

    for fd in findings:
        fd.file = os.path.relpath(fd.file, root)
    verdict = verdict_for(findings)
    counts = {lv: sum(1 for f in findings if f.level == lv) for lv in LEVELS}
    report = {
        "verdict": verdict,
        "counts": counts,
        "target": config.get("database", {}).get("description", "Postgres 16, Azure Database for PostgreSQL Flexible Server (HA)"),
        "mode": mode,
        "base": base,
        "files": [os.path.relpath(f, root) for f in files],
        "changeset_count": len(changesets),
        "tldr": tldr(findings, len(files), len(changesets), verdict),
        "notes": notes,
        "findings": [f.to_dict() for f in findings],
        "unreviewed": unreviewed,
        "passed": passed,
        "rollout": rollout_plan(findings, changesets),
        "new_tables": sorted(ctx.new_tables),
    }

    json_text = json.dumps(report, indent=2)
    md_text = render_md(report)
    if args.output:
        if args.format == "both":
            with open(args.output + ".json", "w", encoding="utf-8") as fh:
                fh.write(json_text)
            with open(args.output + ".md", "w", encoding="utf-8") as fh:
                fh.write(md_text)
        else:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(json_text if args.format == "json" else md_text)
        print(f"{verdict}: {counts}  -> {args.output}")
    else:
        print(json_text if args.format == "json" else md_text if args.format == "md" else json_text + "\n\n" + md_text)

    if args.fail_on == "none":
        return 0
    threshold = LEVEL_RANK[args.fail_on.upper()]
    return 2 if any(LEVEL_RANK[f.level] <= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
