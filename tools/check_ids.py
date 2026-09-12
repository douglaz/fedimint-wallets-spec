#!/usr/bin/env python3
"""Requirement-identifier gate for the specification set.

Enforces the README's append-only convention mechanically:

  * every requirement id is defined exactly once      (duplicate ids)
  * every cited id is defined somewhere               (dangling citations)
  * no id is missing from a namespace's sequence      (renumbering / gaps)
  * every cited ADR exists on disk                    (bad ADR references)
  * codebase references per document match baseline  (ratchet, ADR-0032)

Identifiers are append-only. Deleting a requirement is permitted -- the gap in
the sequence IS the tombstone -- so a withdrawn id may be absent, but it must be
listed in the README's withdrawn-identifier index, which this gate checks.

Run from anywhere; it locates the repository root from its own path.
Exit status 0 = clean, 1 = failures.
"""

import glob
import os
import re
import sys

SPEC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADR_DIR = os.path.join(SPEC, "docs", "adr")

NAMESPACES = [
    "OVR", "DOM", "FMI", "OPS", "API", "STO",
    "ALC", "SEC", "HST", "DEF", "CNF",
]
NS = "|".join(NAMESPACES)

# A requirement is *defined* in one of three shapes the set uses:
#   **API-7** ...                 (most namespaces)
#   - [ ] **CNF-1** ...           (conformance items)
#   ### DEF-1 - ...               (defect prohibitions, as headings)
DEF_RE = re.compile(
    r"^(?:[-*]\s+(?:\[[ x]\]\s+)?)?\*\*((?:%s)-\d+[a-z]?)\*\*"
    r"|^#{1,6}\s+\**((?:%s)-\d+[a-z]?)\**" % (NS, NS),
    re.M,
)
CITE_RE = re.compile(r"`((?:%s)-\d+[a-z]?)`" % NS)
ADR_RE = re.compile(r"`?ADR-(\d{4})`?")
WITHDRAWN_RE = re.compile(r"^\|\s*`?((?:%s)-\d+[a-z]?)`?\s*\|" % NS, re.M)


def docs():
    spec_md = sorted(glob.glob(os.path.join(SPEC, "*.md")))
    adr_md = sorted(glob.glob(os.path.join(ADR_DIR, "*.md")))
    return spec_md, adr_md


def main():
    spec_md, adr_md = docs()

    defined, dupes = {}, []
    for f in spec_md:
        for m in DEF_RE.finditer(open(f, encoding="utf-8").read()):
            rid = m.group(1) or m.group(2)
            if rid in defined:
                dupes.append((rid, os.path.basename(defined[rid]), os.path.basename(f)))
            else:
                defined[rid] = f

    cited = set()
    for f in spec_md + adr_md:
        cited.update(m.group(1) for m in CITE_RE.finditer(open(f, encoding="utf-8").read()))

    withdrawn = set()
    readme = os.path.join(SPEC, "README.md")
    if os.path.exists(readme):
        text = open(readme, encoding="utf-8").read()
        idx = text.find("Withdrawn identifiers")
        if idx != -1:
            withdrawn = {m.group(1) for m in WITHDRAWN_RE.finditer(text[idx:])}

    dangling = sorted(c for c in cited if c not in defined and c not in withdrawn)
    # Never reused: an id in the withdrawn index must not be defined again.
    reused = sorted(defined.keys() & withdrawn)

    gaps, outliers = {}, {}
    for ns in NAMESPACES:
        nums = sorted(
            int(re.match(r"[A-Z]+-(\d+)", k).group(1))
            for k in defined
            if k.startswith(ns + "-")
        )
        if not nums:
            continue
        body = nums
        while len(body) > 1 and body[-1] - body[-2] > 50:
            outliers.setdefault(ns, []).append(body[-1])
            body = body[:-1]
        missing = [
            n for n in range(1, max(body) + 1)
            if n not in body and f"{ns}-{n}" not in withdrawn
        ]
        if missing:
            gaps[ns] = missing if len(missing) <= 20 else (
                missing[:20] + [f"... and {len(missing) - 20} more"]
            )

    adrs = {os.path.basename(p)[:4] for p in adr_md}
    bad_adrs = set()
    for f in spec_md:
        for m in ADR_RE.finditer(open(f, encoding="utf-8").read()):
            if m.group(1) not in adrs:
                bad_adrs.add(m.group(1))

    ratchet = codebase_refs(spec_md)

    print(f"requirements: {len(defined)} | spec files: {len(spec_md)} | ADRs: {len(adrs)}")
    print(f"withdrawn ids indexed: {len(withdrawn)}")
    print("DUPES:", dupes or "none")
    print("DANGLING:", dangling or "none")
    print("REUSED WITHDRAWN:", reused or "none")
    print("NUMBER GAPS:", gaps or "none")
    print("OUTLIER IDS:", outliers or "none")
    print("BAD ADR REFS:", sorted(bad_adrs) or "none")
    print("CODEBASE REFS vs baseline:", ratchet or "at baseline")

    return 1 if (dupes or dangling or reused or gaps or outliers or bad_adrs or ratchet) else 0


# --- codebase-reference ratchet (ADR-0032) ---------------------------------
#
# A requirement may not name the codebase: a function or method path, a source
# file, a crate directory, a pull request, an issue id, or a file:line cite.
# The count of offending lines per document is pinned in a baseline file and
# may only go down; a document with MORE lines than its baseline fails, and so
# does one with FEWER, so the baseline is lowered in the same change that earns
# it. The review ends when every baseline is zero.

BASELINE = os.path.join(SPEC, "tools", "codebase-refs-baseline.txt")
GATED = re.compile(r"^(\d\d-.*|CONTEXT)\.md$")
CODEBASE_REF = re.compile(
    r"`[^`]*::[^`]*`"                        # `Type::method`, `module::item`
    r"|\b[a-z_][a-z0-9_]*\.rs\b"             # source files, with or without :line
    r"|\bwallet-(?:core|fedimint|api|cli|web)/"  # crate directories
    r"|\bPR #\d+"                            # pull requests
    r"|`br-[a-z0-9][a-z0-9.-]*`"             # issue ids
)


def codebase_refs(spec_md):
    """Return {doc: (actual, baseline)} for every document off its baseline."""
    baseline = {}
    if os.path.exists(BASELINE):
        for line in open(BASELINE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                name, n = line.split()
                baseline[name] = int(n)

    off = {}
    for f in spec_md:
        name = os.path.basename(f)
        if not GATED.match(name):
            continue
        actual = sum(
            1 for line in open(f, encoding="utf-8") if CODEBASE_REF.search(line)
        )
        allowed = baseline.get(name, 0)
        if actual != allowed:
            off[name] = (actual, allowed)
    return off


if __name__ == "__main__":
    sys.exit(main())
