# AGENTS.md

Specifications only. `tools/` holds the gate that checks them; `.github/workflows/` runs the same
script. Nothing that implements the specified system belongs here — the code, its tests, its
runbooks and its issue tracker live in
[`douglaz/fedimint-wallets`](https://github.com/douglaz/fedimint-wallets).

## The one rule that shapes every edit

This set is **descriptive**: a requirement records what the code does today, including its
defects, and a change that stops it doing so is a regression against the document — not a
statement that someone decided it ought to. Behaviour the code does not have goes in one of two
other places, never in a requirement:

- a **decision** that the code should do it → `docs/adr/`, and the requirement that describes
  today's behaviour cites the ADR as the target;
- the **gap** between that decision and the code → the code repository's `docs/open-findings.md`
  (`Fn` items, one per tracked issue), which the requirement cites.

`11-open-questions.md` holds product decisions nobody has taken; it is the only forward-looking
document here.

## Gates

`bash tools/check-all.sh`, before you start and again before you report done. Run it unpiped and
read its exit code — a pipe reports the pipeline's status, not the gate's. Green is evidence
because CI also breaks a document on every run and asserts the gate rejects it.

## Writing a requirement

**Verify against the code, then write.** Every claim about behaviour names the function that
has it. When a reviewer challenges one, the answer is a re-read of that function, not a reworded
sentence; and a claim about *runtime* behaviour (an exit code, a stream, a third-party library's
reaction) carries the command that measured it, its version and its result — a reviewer will
otherwise ask for it, correctly.

**Cite the owner.** One rule, one home; everywhere else points at it with the id in backticks.
`DEF-21` is what a second normative copy costs. Arguments have owners too: re-explaining a rule
elsewhere restates it, and the restatement drifts.

**A decision gets its identifier when it is accepted.** Name the id a change lands on — the
requirement it amends, or the next free number in the right namespace — before writing it, so
"did we apply everything?" is a `grep`. Identifiers are append-only; the conventions are in
`README.md`, *Requirement conventions*.

**Quote, don't characterise.** A sentence about what another requirement says carries that
requirement's words.

## Conventions with a home already

- Identifiers, retention, withdrawn ids → `README.md`, *Requirement conventions*.
- Vocabulary, and which words are banned → `CONTEXT.md`.
- Decisions and what was rejected to reach them → `docs/adr/`.
- What has been demonstrated, by which gate → `10-conformance-checklist.md`.
- What the code does not yet do → the code repository's `docs/open-findings.md`.
