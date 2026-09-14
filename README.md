# fedimint-wallets — specification

The specification of the wallet implemented in
[`douglaz/fedimint-wallets`](https://github.com/douglaz/fedimint-wallets): what a compliant
wallet MUST, MUST NOT, SHOULD and MAY do, completely enough that an implementer who has never seen
that code can build one, and precisely enough that any implementation can be reviewed against it
and found compliant or not (`ADR-0032`). It presupposes the product's stack — Rust, the Fedimint
client SDK, its embedded database, the hosts named in `08-hosts-and-deployment.md` — and no
particular codebase, and it describes no deployment.

This repository holds **specifications only**: the requirement documents, the conformance
scenarios, the ADRs, the glossary and the gates that check them. The code, its tests, its
runbooks, its conformance results and its issue tracker live in the code repository, and a
`docs/…` path in this set that is not `docs/adr/` names a file there. Where the implementation falls
short of a requirement, the code repository says so in its
[`docs/open-findings.md`](https://github.com/douglaz/fedimint-wallets/blob/main/docs/open-findings.md),
one `Fn` item per tracked issue.

Until 2026-09-12 this set was descriptive — a record of what one codebase did, function names
included. `ADR-0032` records the change of posture and the review it started; while that review
runs, a chapter may still carry sentences that fail the refactor test below, and
`tools/codebase-refs-baseline.txt` says how many.

## How to read this

| Document | Contents |
|---|---|
| [`executive-summary.md`](./executive-summary.md) | **Start here.** What the wallet is and the four ideas everything else follows from |
| [`00-overview.md`](./00-overview.md) | The problem, the shape of the solution, the system context, decided non-goals |
| [`01-domain-model.md`](./01-domain-model.md) | Entities and their states: federation, intent, operation, ledger row, move record, policy, candidate, occurrence |
| [`02-fedimint-integration.md`](./02-fedimint-integration.md) | The SDK boundary: clients and partitions, gateways, the two Lightning legs, recovery, the signals a federation emits |
| [`03-operation-lifecycle.md`](./03-operation-lifecycle.md) | How an intent is admitted, executed, resumed and terminalized; the killpoints; supersession; reconcile |
| [`04-api-contract.md`](./04-api-contract.md) | Every HTTP route and field, the error envelope, the CLI verbs and exit codes |
| [`05-persistence.md`](./05-persistence.md) | The two stores, the key tags, every persisted row, the transaction model, the ledger's write discipline, the compatibility rules |
| [`06-allocator-and-automation.md`](./06-allocator-and-automation.md) | The pure decision core, route economics, scoring, probes, discovery, evacuation, the tick, the scheduler cycle, and the readiness signal |
| [`07-security-requirements.md`](./07-security-requirements.md) | The threat model and what MUST be enforced against it |
| [`08-hosts-and-deployment.md`](./08-hosts-and-deployment.md) | The daemon, the standalone mode, the CLI as a frontend, the browser sidecar, and the operator-facing contracts of each |
| [`09-known-defects.md`](./09-known-defects.md) | Prohibitions written from defects this system has had, each with the failure it prevents |
| [`10-conformance-checklist.md`](./10-conformance-checklist.md) | The scenarios a conformant implementation MUST pass, and the requirements each demonstrates |
| [`11-open-questions.md`](./11-open-questions.md) | Product decisions nobody has taken; the set is silent on what they govern until an ADR answers them |
| [`docs/open-findings.md`](https://github.com/douglaz/fedimint-wallets/blob/main/docs/open-findings.md) *(code repository)* | Where the implementation does not meet this set, `F1`…, each tied to the issue that tracks it |
| [`CONTEXT.md`](CONTEXT.md) | The glossary: the vocabulary the requirements are written in, and the words they avoid |
| [`docs/adr/`](docs/adr/) | The thirty-two decisions and what was rejected to reach them. Canonical where they conflict with older prose. Those before `ADR-0032` were written about one implementation and say so; a requirement cites one as its owner only where the decision is a behaviour of the wallet |

Read `00`, `01` and `03` first. `03` is the part that distinguishes this wallet from a thin
fedimint client: a money operation is a durable, idempotency-keyed intent that survives a crash
at any of four named points without double-paying, and everything else is built around that.

## How compliance is measured

A requirement is a claim about the wallet, not about any codebase. Three things follow.

- **A requirement is observable at a boundary** — what reaches a federation or gateway, what is
  derived from the seed, what a frontend sees, what survives a crash. Where it can be demonstrated,
  `10-conformance-checklist.md` carries the scenario that demonstrates it, and a conformant
  implementation passes every scenario there.
- **The code repository owns the evidence.** Which scenarios its implementation has passed, at
  which commit, and which requirements it does not yet meet (`docs/open-findings.md`) are facts
  about that tree and live beside it. A requirement here is never weakened to match an
  implementation; the implementation gains a finding.
- **Nothing here is a test.** A MUST is met when a scenario or a review shows it is met, by the
  implementation under review, not by the sentence existing.

## Requirement conventions

Requirements use RFC 2119 keywords — **MUST**, **MUST NOT**, **SHOULD**, **MAY** — in their
ordinary sense: a MUST is required of every compliant wallet, whether or not any implementation
meets it today. Each is tagged with a stable identifier:

| Prefix | Domain |
|---|---|
| `OVR-n` | Overview and scope |
| `DOM-n` | Domain model |
| `FMI-n` | Fedimint SDK integration |
| `OPS-n` | Operation and intent lifecycle |
| `API-n` | HTTP API and CLI contract |
| `STO-n` | Persistence |
| `ALC-n` | Allocator, scoring, probes, discovery, tick and scheduler |
| `SEC-n` | Security |
| `HST-n` | Hosts and frontends |
| `DEF-n` | Defect prohibitions |
| `CNF-n` | Conformance scenarios |
| `Fn` | Non-conformances of the implementation — defined in the code repository's `docs/open-findings.md`, cited from here; not gated; tracked one-to-one with that repository's issues |

### The refactor test

A sentence belongs in a requirement only if a rewrite of the code that keeps every byte on disk,
every byte on the wire and every observable behaviour identical **cannot** violate it. On-disk
shapes, wire shapes, protocol facts and the names of persisted or serialized types pass. Function
and method names, crate and file paths, line numbers, frameworks and dependency pins fail
(`ADR-0032`). The codebase-reference gate counts the lines that fail it.

### Identifiers are append-only. Text is not.

An identifier is never reused and never renumbered. Deleting a requirement is permitted — the
gap in the sequence is the tombstone — but a withdrawn id must be listed in the index below so an
old citation still resolves. `tools/check_ids.py` enforces most of this: duplicate ids, dangling
citations, sequence gaps not listed as withdrawn, and references to ADRs that do not exist all
fail the gate. It cannot see a deleted **highest** id in a namespace — the range simply shrinks —
so that one case rests on the convention and on review, not on the gate.

A requirement whose prescribed behaviour is the behaviour it already described keeps its id. One
that described only a codebase fact with no behavioural content is withdrawn and not replaced.
New behaviour gets the next free id in its namespace.

### A decision gets its identifier when it is accepted

When a change to the system is accepted, name the identifier that will carry it — the requirement
it amends, or the next free number in the right namespace. Then "did we apply everything?" is a
`grep`, not a memory exercise.

### One owner per rule

A rule lives in one requirement; everywhere else cites it. `DEF-21` is what a second normative
copy costs: seven documents kept saying an evacuation sizes off the flat cap after the code
stopped doing so, and the one an operator reads under pressure was among them.

### Withdrawn identifiers

Deleted from the documents. Never reused. Listed so an older citation still resolves.

| Identifier | Was | Why it went |
|---|---|---|
| `FMI-1` | The fedimint dependency pinned to one fork revision, with the crates named and the three patches it carries | A dependency pin is a codebase fact (`ADR-0032`, "The dependency pin goes"); each patch's behaviour is its own requirement — `FMI-38` (bounded federation-API waits), `FMI-30` (recovery complete-or-fail), `FMI-39` (single-share threshold decryption) |
| `FMI-2` | Any repoint of the dependency carries every fork-only patch, proven by a cross-federation move smoke | Dependency management and a build-adoption gate are the code repository's; the behaviours the patches provide are `FMI-38`, `FMI-30` and `FMI-39`, and an implementation that loses one gains a finding |

## Gates

```
bash tools/check-all.sh
```

runs every gate. It exits non-zero on any failure and captures each gate's own exit code rather
than the last command's in a pipe. Run it before and after editing this set.
`.github/workflows/ci.yml` runs the same script on every push and, on every run, breaks a
scratch copy of a document and asserts each gate rejects it, so its green check is evidence
rather than decoration.

- **Identifiers** — duplicates, dangling citations, sequence gaps, reused withdrawn ids, ADR
  references that do not exist.
- **Codebase references** — per document, the number of lines naming the codebase, checked
  against `tools/codebase-refs-baseline.txt`. A ratchet: more than the baseline fails, and so does
  fewer, so the baseline is lowered in the change that earns it and never drifts upward.

## Relationship to the code repository

This set was extracted from `docs/spec/` in the code repository on 2026-09-12 and moved here so
that a specification change and a code change are two different pull requests against two
different gates. The code repository keeps: `docs/open-findings.md` (the non-conformances, one
per tracked issue); the conformance results (which `CNF` scenarios pass, at which commit); the
runbooks, which are operator procedure and remain authoritative for procedure; the roadmap and
the phase plans; the reference design (how its implementation meets the requirements here, the
actor and its commands included); and `docs/archive/`, the record of *why* the code is the way it
is. The ADRs and the glossary are here because they are the decisions and the vocabulary the
requirements are written in.

A change to what the wallet must do lands here first, under a named identifier. The code follows
in its own pull request, and until it does, the findings file records the gap. A change to the
code that does not change what a requirement says needs no change here.
