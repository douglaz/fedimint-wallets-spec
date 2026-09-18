---
status: accepted
---
# The specification is prescriptive and implementation-agnostic

Until 2026-09-12 this set was **descriptive**: a requirement recorded what one Rust
implementation did today, defects included, named the function that did it, and cited the
code repository's findings file for the gap between that and any accepted decision. It also
described one running instance of that implementation (`HST-23`, `HST-24`, question 1 of
`11-open-questions.md`). That posture made the set a regression baseline for one codebase, not
a specification of the wallet.

**Decided:** the set is **prescriptive** and **implementation-agnostic**. It states what a
compliant wallet MUST, MUST NOT, SHOULD and MAY do, completely enough that an implementer who
has never seen the existing code can build one, and precisely enough that any existing
implementation can be reviewed against it and found compliant or not. It presupposes the
product's **stack** — Rust, the Fedimint client SDK, its embedded database, the hosts (a
daemon, an Android app, a browser sidecar, wasm where named) — because those are decisions
about the product, not accidents of one codebase. It presupposes no particular **codebase**:
nothing that a rewrite could change while leaving every byte on disk, every byte on the wire
and every observable behaviour the same. And it describes no deployment of any implementation.

## Consequences

- **RFC 2119 keywords take their ordinary meaning.** `README.md`'s "descriptive sense" is
  withdrawn: MUST means the wallet is required to do it, whether or not any implementation does.
- **Traceability inverts.** The specification never cites code. The code repository owns the
  map from requirement id to the code that satisfies it, and its `docs/open-findings.md`
  becomes the list of **non-conformances**: requirements the implementation does not meet.
  `Fn` items keep their numbering; their sense changes from "gap between code and decision" to
  "gap between code and specification".
- **Nothing about a deployment belongs here.** `HST-23`, `HST-24`, question 1 of
  `11-open-questions.md` and every sentence that leans on them are removed in the review. The
  one claim they carried that is not deployment trivia — which requirements have and have not
  been exercised against a real federation — is evidence about an implementation and moves to
  the code repository with the conformance results.
- **Every requirement is re-read, not re-moded.** Flipping "does" to "MUST" is not the review.
  Each requirement is checked for three things: that it states a behaviour observable at the
  wallet's boundary rather than a mechanism inside one implementation; that it is what the
  wallet *should* do, so that where today's code differs the requirement changes and the code
  gains a finding, not the reverse; and that an implementer could build from it alone.
- **Identifiers stay append-only.** A requirement whose prescribed behaviour is the behaviour it
  already described keeps its id. A requirement that described only an implementation fact with
  no behavioural content is withdrawn, listed in `README.md`'s index, and not replaced. New
  behaviour a re-read exposes as missing gets the next free id in its namespace.
- **`09-known-defects.md` keeps its prohibitions and loses its provenance.** A defect
  prohibition is a legitimate prescriptive requirement ("a wallet MUST NOT …") with one or two
  sentences on the failure it prevents; the pull requests, issues, functions and "tests that
  proved nothing" that explain how one codebase got there move to the code repository.
- **`10-conformance-checklist.md` becomes the normative scenario suite.** Each `CNF-n` is a
  scenario — given, when, then — at the wallet's boundaries, naming the requirements it
  demonstrates and carrying no result. A conformant implementation MUST pass every scenario.
  Process discipline (how a gate is run, that a test is watched to fail first), build and unit
  results, checkboxes, commit hashes and test names move to the code repository; `CNF` ids that
  were work items rather than scenarios are withdrawn, their `Fn` already tracking the work.
- **`08-hosts-and-deployment.md` keeps host behaviour and operator-facing contracts** — the
  daemon's subcommands, config keys, serve and shutdown sequence, logging redaction, the
  standalone mode, the data-directory layout, the sidecar as `ADR-0028` requires it — and loses
  the build, the devshell, CI, test counts, the absence or presence of manifests, and the
  deployment section. Where an operator artefact carries a contract (a readiness probe's exit
  codes, what a stranded move leaves for the operator), the contract stays and the artefact goes.
- **`11-open-questions.md` holds product decisions only.** Roadmap order ("which frontend is
  next") is the code repository's; a question stays here only if its answer changes what the
  wallet MUST do.
- **The boundary is gated, as a ratchet.** `tools/check_ids.py` counts, per document, the
  lines that name the codebase (`::`, `.rs`, crate paths, pull-request and issue ids, line
  cites) against `tools/codebase-refs-baseline.txt`, and fails on more or fewer than the
  baseline, so every chapter's rewrite lowers its number in the same change and the review
  ends at zero.
- The ADRs before this one were written about one implementation and say so; they are history
  and are not rewritten for this decision. Where a requirement cites one as its target, the
  review decides whether the ADR's decision is a behaviour of the wallet (it stays cited) or a
  choice of that implementation (the citation goes).

### Amendment, 2026-09-18: the review closed

The review ran as one pull request per chapter, in dependency order, and closed with every
gated document at zero in `tools/codebase-refs-baseline.txt`. Every consequence above happened
as written: the descriptive sense is gone from `README.md`; `HST-23`, `HST-24` and the
deployment question are withdrawn; `09` carries prohibitions without provenance; `10` is the
scenario suite; `08` kept the host contracts; `11-open-questions.md` holds two product
questions (numbered 1 and 2 today — the "question 1" this ADR names above was the deployment
question, since removed); the withdrawn ids are in `README.md`'s index. The ratchet **stays**:
at zero it is a plain prohibition, and CI's mutation step keeps proving the gate rejects a
reference. The code repository owns the hand-off lists each chapter's pull request produced,
one work item per chapter.

## The boundary: the refactor test

A sentence is a requirement only if a rewrite of the code that keeps every byte on disk, every
byte on the wire and every observable behaviour identical **cannot** violate it. If a pure
refactor cannot break it, it is a requirement. If a refactor would break it merely by renaming
or moving things, it describes the codebase and comes out.

What that keeps: on-disk shapes (the two stores, key tags and prefixes, persisted record fields,
the seed encoding), because upgrade-in-place is a contract; wire shapes (the route table, JSON
fields, exit codes, the stdout lines a script parses); protocol facts (seed derivation, the
gateway `routing_info` exchange); and the names of persisted and serialized types, which name
shapes rather than code. What it removes: internal function and method names, crate and file
paths, line numbers, the HTTP framework, the connector wiring, and any sentence whose only
content is where in the code something happens.

Two calls the test alone does not settle:

- **The dependency pin goes.** A pinned fork revision is a codebase fact — a rewrite could vendor
  the patches. Each behaviour the fork's patches provide becomes its own requirement; the code
  repository's conformance notes record that it is met by a patch, not by upstream.
- **The concurrency mechanism goes; its invariants stay.** One serialized admission point, one
  live key per allocator goal, agent work admitted nowhere else, generation-fenced writes — these
  are requirements. The actor, its one-shot commands and its leases are the reference design and
  are described in the code repository, not in a MUST.

## When the code and the requirement disagree

The requirement states what the wallet should do; the code repository's findings file records
that the implementation does not. Where "should" is settled by an ADR, the requirement follows
the ADR. Where it is not settled and is a product decision nobody has taken, it goes to
`11-open-questions.md` and the set is **silent** — a prescriptive set does not describe today's
code to fill the gap. Where it is not settled and is an engineering judgement, the review
proposes and the accepted answer lands under a named identifier.
