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
included. `ADR-0032` records the change of posture and the review it started; that review
closed on 2026-09-18 with every gated document at zero in `tools/codebase-refs-baseline.txt`,
and the gate keeps it there.

## How to read this

| Document | Contents |
|---|---|
| [`executive-summary.md`](./executive-summary.md) | **Start here.** What the wallet is and the four ideas everything else follows from |
| [`00-overview.md`](./00-overview.md) | The problem, the shape of the solution, the system context, decided non-goals |
| [`01-domain-model.md`](./01-domain-model.md) | Entities and their states: federation, intent, operation, ledger row, move record, policy, candidate, occurrence |
| [`02-fedimint-integration.md`](./02-fedimint-integration.md) | The SDK boundary: clients and partitions, gateways, the two Lightning legs, recovery, the signals a federation emits |
| [`03-operation-lifecycle.md`](./03-operation-lifecycle.md) | How an intent is admitted, executed, resumed and terminalized; the killpoints; supersession; reconcile |
| [`04-api-contract.md`](./04-api-contract.md) | Every HTTP route and field, the error envelope, the CLI verbs and exit codes |
| [`05-persistence.md`](./05-persistence.md) | The two stores, the key tags, every persisted row, the transaction model, the ledger's write discipline, the compatibility rules, and what a move writes into the federation client's operation log |
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

A rule lives in one requirement; everywhere else cites it. What a second normative copy costs:
seven documents kept saying an evacuation sizes off the flat cap after the code stopped doing
so, and the one an operator reads under pressure was among them.

### Withdrawn identifiers

Deleted from the documents. Never reused. Listed so an older citation still resolves.

| Identifier | Was | Why it went |
|---|---|---|
| `FMI-1` | The fedimint dependency pinned to one fork revision, with the crates named and the three patches it carries | A dependency pin is a codebase fact (`ADR-0032`, "The dependency pin goes"); each patch's behaviour is its own requirement — `FMI-38` (bounded federation-API waits), `FMI-30` (recovery complete-or-fail), `FMI-39` (single-share threshold decryption) |
| `FMI-2` | Any repoint of the dependency carries every fork-only patch, proven by a cross-federation move smoke | Dependency management and a build-adoption gate are the code repository's; the behaviours the patches provide are `FMI-38`, `FMI-30` and `FMI-39`, and an implementation that loses one gains a finding |
| `FMI-29` | "Nostr is an enum variant and a label. No Nostr source is implemented." | A codebase fact with no behavioural content; the Nostr rule `ADR-0019` decides (discovery at most, never a trust input) is new behaviour and is `FMI-43` |
| `OPS-34` | "Core `reconcile`": one implementation layer's reconcile entry point, which harness reached it, which verbs did not, and a test-only await refusal | A description of one codebase's call graph; the two behaviours it carried — one drive step per intent per pass, and the optional move-record backfill before stepping — are `OPS-35`'s |
| `CNF-48` | "A restore drill from an app-state snapshot plus seed with in-flight operations explained" | A work item, not a scenario (`ADR-0032`, "`CNF` ids that were work items rather than scenarios are withdrawn"), and one for a facility `STO-28` says is not required: the backup unit is the seed plus invites (`ADR-0025` §1), and a store restore is an operator action outside this set |
| `STO-32` | "The ledger is greenfield in one respect only": `OperationRecord.repaired` and `WatchState.discover_rotation` carry no default, on a claim unverified against one deployment's store | A codebase fact about one build plus a deployment claim (`ADR-0032`, "Nothing about a deployment belongs here"); the behaviour required of the two fields — decode when absent, as `false` and `0` — is `STO-30`'s rule, and they are on its list |
| `ALC-50` | Test-only seams in production files are compile-time gated with no-op twins, except two debug-build seams | How a codebase gates its test seams is a codebase fact with no behavioural content (`ADR-0032`); the one behaviour it carried — a release build ignores the two fault-injection variables — is `SEC-18`'s |
| `SEC-10` | "The seed is **plaintext**": twelve words stored as entropy in the client store, protected by the data directory's mode alone, with no memory hygiene, the encryption `ADR-0026` accepted unbuilt | A codebase fact and a finding (`F11`), the opposite of the prescribed behaviour; the requirement — the seed MUST NOT be stored in plaintext, AEAD under a key held outside the store, fail closed, one-time re-encryption — is new behaviour and is `SEC-25` |
| `SEC-20` | Deployment identity — provider, cluster, namespace, pod, image digest, uptime, balance — MUST NOT appear in tracked files | A hygiene rule about one repository's tree, not a behaviour of the wallet (`ADR-0032`, "Nothing about a deployment belongs here"); the prohibition is the code repository's (`DEF-22`, withdrawn since for the same reason), and the historical leak is the code repository's `F21` |
| `SEC-21` | The dependency is a personal fork at a fixed revision with no reproducible-build attestation and no image signature check | A dependency pin and a build's provenance are codebase facts (`ADR-0032`, "The dependency pin goes"); the behaviours the pin carried are `FMI-38`, `FMI-30` and `FMI-39`, already required |
| `HST-14` | The workspace builds only inside the repository's Nix devshell; the gate command line | A build environment is a codebase fact with no behavioural content (`ADR-0032`: 08 "loses the build, the devshell, CI") |
| `HST-15` | The flake outputs: two binaries, a pinned curl, an OCI image and its registry name | Build artefacts of one repository, not behaviour of the wallet (`ADR-0032`) |
| `HST-16` | CI's two jobs and their steps, including the specification gate run in the code repository's workflow | Continuous-integration policy is the code repository's (`ADR-0032`); nothing in it is observable at a wallet boundary |
| `HST-17` | No live devimint smoke runs in CI; the smokes are manual gates with last-green evidence in issue notes | Test policy and where its evidence lives are the code repository's (`ADR-0032`: "Process discipline … build and unit results … move to the code repository"); the scenarios the smokes realise are `10-conformance-checklist.md`'s |
| `HST-18` | The test count at one commit and the share of test code in one crate | A measurement of one codebase at one commit (`ADR-0032`: "test counts" go) |
| `HST-20` | No Kubernetes manifest and no deployment configuration is tracked; the unit's commented-out timeout line | A statement about one repository's tree and one deployment (`ADR-0032`: "the absence or presence of manifests" goes); the prohibition on deployment identity in tracked files is the code repository's (`DEF-22`, withdrawn) |
| `HST-23` | One instance runs the 2026-07-26 build as a test deployment with a small real-sats balance | A deployment (`ADR-0032`: "Nothing about a deployment belongs here") |
| `HST-24` | `main` is 240 commits past the deployed build; which requirements are unexercised against a real federation | A deployment plus evidence about one implementation; the one non-trivia claim — which requirements have been exercised against a real federation — moves to the code repository's conformance results (`ADR-0032`) |
| `HST-25` | What that deployment demonstrated from its ledger: restart survival, a cross-federation move, an external send and receive, one standing silent condition | A deployment's history (`ADR-0032`); the silent condition it observed is the code repository's `F1` |
| `HST-28` | The operator's four-step response to a stranded move, recorded from the code repository's runbook, with standalone `show` exposing the error, the leg ids and the gateway "and nothing more" | An operator procedure is the code repository's runbook (`ADR-0032`: "what a stranded move leaves for the operator" is the contract that stays); the wallet's guarantees behind it — the records kept unchanged, the client state kept, no second send — are new behaviour and are `HST-32` |
| `HST-22` | The readiness poller: its inputs, environment variables, webhook, alert list and exit codes, with an absent `automation_ready` a note rather than an alert | An operator artefact (`ADR-0032`: "the contract stays and the artefact goes"); the contract, with the opposite rule for an absent field — `API-16`'s "MUST treat readiness as unknown, not healthy" — is new behaviour and is `HST-30` |
| `CNF-49` | "The readiness poller running from a schedule and paging on a transition" | A work item wearing a scenario id (`ADR-0032`: "`CNF` ids that were work items rather than scenarios are withdrawn"), for a facility `HST-30` says the wallet is not required to ship or schedule; the code repository's `F14` is its record |
| `CNF-4` | The formatter, the linter and the specification gate clean in the devshell on every push | A build gate of one repository (`ADR-0032`: "build and unit results … move to the code repository"); nothing in it is observable at a wallet boundary, and `HST-14`–`HST-16` went for the same reason |
| `CNF-5` | The unit and integration suite's test count at one commit, with the command line that ran it | A build and unit result at one commit (`ADR-0032`); the code repository's conformance results own it |
| `CNF-6` | CI asserts the lock file is unchanged before any build step and builds with `--locked` | Continuous-integration policy of one repository (`ADR-0032`), withdrawn with `HST-16` |
| `CNF-7` | The Nix build produces the two binaries and a non-empty image, and both answer `--help` | A build artefact check of one repository (`ADR-0032`), withdrawn with `HST-15` |
| `CNF-44` | "Any build after `b5f46de` against a **real** federation": receive, pay, top-up, standby funding, move, restart, reconcile and the evacuation cap, for the changed path | A conformance result of one implementation's build lineage against one deployment (`ADR-0032`: which requirements have been exercised against a real federation "moves to the code repository with the conformance results"); the behaviours it lists are scenarios elsewhere in this chapter |
| `DEF-19` | The devimint runbook could not produce a green run as written; a runbook's invocation is re-run from a clean shell before it is called correct, with the failure signature recorded verbatim | A defect in one repository's runbook and a process discipline (`ADR-0032`: "Process discipline … move to the code repository"); no requirement in 02–08 cites it, and there is no wallet behaviour behind it |
| `DEF-21` | Seven sites still said an evacuation sizes off the flat cap after it stopped doing so; a rule has one owner and everywhere else cites it | A convention of this set's own text, not a behaviour of the wallet; it lives in `README.md`, *One owner per rule*, and `AGENTS.md` points there |
| `DEF-22` | Deployment identity — provider, namespace, pod name, image digest, uptime, balance — MUST NOT appear in tracked files | A hygiene rule about one repository's tree, withdrawn for the reason `SEC-20` and `HST-20` were (`ADR-0032`: "Nothing about a deployment belongs here"); no requirement cites it, and the leak it recorded is the code repository's `F21` |
| `DEF-23` | A concurrency test that could not fail; a test added for a property is watched to fail against the broken production behaviour first | A defect in one codebase's test, and a test discipline (`ADR-0032`: "Process discipline … move to the code repository"); no requirement cites it, and the discipline belongs in the code repository's `AGENTS.md` |
| `DEF-24` | A fence test that planted its poison row outside the partition the wallet reads, and passed against nothing | The same test discipline as `DEF-23`, and it belongs in the same place, the code repository's `AGENTS.md`; the partition rule it cited is `STO-1`'s |
| `DEF-25` | The live evacuation smoke could not detect a regression to the flat cap; a live gate's parameters are chosen so the old behaviour fails and the new one passes | A gap in one implementation's conformance evidence (`F22`), not a wallet behaviour; the scenario that closes it — an evacuation whose cap discriminates the basis — is `CNF-43` |
| `CNF-2` | A test added for a property is watched to fail against the broken production behaviour first, one mutation per property | A test discipline of one repository (`ADR-0032`: "Process discipline (how a gate is run, that a test is watched to fail first) … move to the code repository"), withdrawn with `DEF-23` and `DEF-24`, which cited it; nothing in it is observable at a wallet boundary |
| `CNF-3` | A live gate's parameters discriminate: the old behaviour fails and the new one passes; which smokes did and did not | A test discipline of one repository and one implementation's gate results (`ADR-0032`), withdrawn with `DEF-25`, which cited it; the one scenario it pointed at is `CNF-43` |
| `CNF-40` | A runbook claim about what a procedure does is re-run from a clean shell before it is called correct, with the failure signature recorded verbatim | A process discipline of one repository's documentation (`ADR-0032`), withdrawn with `DEF-19`, which cited it; nothing in it is observable at a wallet boundary |
| `CNF-1` | The gate is one command, run unpiped, with its own exit code captured and grepped from the log | A process discipline (`ADR-0032`: "Process discipline (how a gate is run …) … move to the code repository"); it belongs in the code repository's `AGENTS.md` |
| `CNF-30` | The smoke's real exit is captured, not the trailing command's | The same discipline as `CNF-1`, for the live gates; withdrawn with it |
| `CNF-39` | Every smoke header records its complete launch block and its last green run with the figures observed, and which of one repository's smokes did so | Where one repository keeps its gate results is that repository's (`ADR-0032`: "checkboxes, commit hashes and test names move to the code repository"); the results themselves are its conformance-results file |
| `CNF-25` | The misbehaving-gateway double accepts a connection and never answers; what it does and does not prove | A description of one harness's instrument (`ADR-0032`: a scenario is stated against the wallet's environment, "never against a harness"); the behaviour it exercised is the *given* of `CNF-21` |
| `CNF-27` | The two-federation harness is a patch applied to a checkout at the pinned SDK revision, and the four things a harness must provide to be equivalent | How one repository builds its harness (`ADR-0032`); any harness that produces a scenario's *given* state is admissible, and the environment every scenario presumes is stated once at the head of `10-conformance-checklist.md` |
| `CNF-28` | The harness environment exports the three module-enabling variables, without which every balance read dies | A harness configuration fact of one repository (`ADR-0032`); the modules a federation must expose are `FMI-3`'s |
| `CNF-29` | Wallet binaries are rebuilt through a fixed Nix child-environment allowlist with a fresh temporary source home before each certifying run | A build-provenance discipline of one repository (`ADR-0032`: "build and unit results … move to the code repository"), withdrawn with `HST-14` and `SEC-21` |
| `CNF-31` | Binaries are rebuilt before every smoke; a stale binary has invalidated a gate twice | The same discipline as `CNF-29`; withdrawn with it |
| `CNF-52` | Every routed smoke registers the gateway on every guardian of each federation right after bring-up, with two named exceptions, and how registration is done | Harness set-up of one repository (`ADR-0032`: "never against a harness"); the behaviour it protected — automated routing resolves from the threshold-vetted list and nothing else, so an empty list refuses every automated route — is `FMI-10`'s and `FMI-14`'s, and the *given* of `CNF-53` |
| `CNF-45` | A human reading of the four supersession money-path boundaries | A review work item wearing a scenario id (`ADR-0032`: "`CNF` ids that were work items rather than scenarios are withdrawn"); the code repository's `F26` is its record |
| `CNF-46` | The browser sidecar's route manifest and live gate | A work item for a facility the code repository has not built (`ADR-0032`); its record is the code repository's `F27`, a non-conformance against `HST-26` and `HST-31`; the sidecar's scenario is `CNF-54`, which that implementation does not yet pass |

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
  fewer, so the baseline is lowered in the change that earns it and never drifts upward. Every
  line has been 0 since the `ADR-0032` review closed, so the gate is now a plain prohibition, and
  CI's mutation step keeps proving it rejects a reference.

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
