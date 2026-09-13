# AGENTS.md

Specifications only. `tools/` holds the gates that check them; `.github/workflows/` runs the same
script. Nothing that implements the specified system belongs here — the code, its tests, its
runbooks, its conformance results and the tracker for work on the code live in
[`douglaz/fedimint-wallets`](https://github.com/douglaz/fedimint-wallets). Work on the
specification itself is tracked in `.beads/` here (`br`, ids `spec-…`); a bead is a work item,
never a requirement, and nothing in `.beads/` is normative.

## The one rule that shapes every edit

This set is **prescriptive** (`ADR-0032`): a requirement states what a compliant wallet MUST,
MUST NOT, SHOULD or MAY do, completely enough that an implementer who has never seen the existing
code can build one, and precisely enough that any implementation can be reviewed against it. It
presupposes the product's stack — Rust, the Fedimint client SDK, its embedded database, the
hosts — and no particular codebase, and it describes no deployment.

The test for a sentence is the **refactor test**: a rewrite of the code that keeps every byte on
disk, every byte on the wire and every observable behaviour identical must not be able to break
it. On-disk shapes, wire shapes, protocol facts and the names of persisted or serialized types
pass. Function and method names, crate and file paths, line numbers, frameworks, dependency pins
and "where in the code this happens" fail, and do not belong in a requirement.

Behaviour the code does not have is not a reason to soften a requirement. It goes in one of two
other places:

- a **product decision nobody has taken** → `11-open-questions.md`, and the set is silent on the
  behaviour until an ADR answers it;
- an **implementation that falls short** → the code repository's `docs/open-findings.md`
  (`Fn` items, one per tracked issue, each a non-conformance against a requirement here).

## Gates

`bash tools/check-all.sh`, before you start and again before you report done. Run it unpiped and
read its exit code — a pipe reports the pipeline's status, not the gate's. Green is evidence
because CI also breaks a document on every run and asserts each gate rejects it.

The codebase-reference gate is a **ratchet**: `tools/codebase-refs-baseline.txt` holds, per
document, the number of lines that still name the codebase, and the gate fails when a document
has more — or fewer, so the baseline is lowered in the same change that earns it. It reaches
zero when the review that `ADR-0032` started is complete, and stays there.

## Writing a requirement

**State the behaviour, not the mechanism.** A requirement is observable at one of the wallet's
boundaries: what reaches a federation or gateway, what is derived from the seed, what a frontend
sees, what survives a crash. If the only way to check a sentence is to read the code, it is not a
requirement yet.

**Cite the owner.** One rule, one home; everywhere else points at it with the id in backticks.
`DEF-21` is what a second normative copy costs. Arguments have owners too: re-explaining a rule
elsewhere restates it, and the restatement drifts.

**A decision gets its identifier when it is accepted.** Name the id a change lands on — the
requirement it amends, or the next free number in the right namespace — before writing it, so
"did we apply everything?" is a `grep`. Identifiers are append-only; the conventions are in
`README.md`, *Requirement conventions*.

**Quote, don't characterise.** A sentence about what another requirement says carries that
requirement's words.

**Prefer a scenario to an assertion.** When a requirement can be demonstrated, `10-conformance-checklist.md` carries the scenario that demonstrates it, and the requirement cites it.

## Conventions with a home already

- Identifiers, retention, withdrawn ids → `README.md`, *Requirement conventions*.
- Vocabulary, and which words are banned → `CONTEXT.md`.
- Decisions and what was rejected to reach them → `docs/adr/`.
- What a conformant implementation must demonstrate → `10-conformance-checklist.md`.
- What the existing implementation does not yet do → the code repository's `docs/open-findings.md`.
