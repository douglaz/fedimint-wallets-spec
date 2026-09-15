# 00 — Overview

## Problem

Fedimint federations issue blind-signed ecash backed by a guardian multisig, which gives a
spending wallet the privacy a custodial Lightning wallet cannot: no KYC, a provider blind to
balance and history, fully private receives. They are also **ephemeral** in practice — a
federation can degrade, lose its gateway, or announce it is shutting down — so a wallet that
holds its whole balance in one federation is one outage away from a user who cannot pay.

The wallet specified here spreads a small spending balance across federations and moves it
automatically on the user's standing instruction, so that one federation degrading never leaves
the user with nothing to spend. It does this as an **on-device agent** with no operator, no
curated list and no service in the fund path (`ADR-0014`, `ADR-0015`), and it records every
action it takes and every operation it refuses durably enough that the user can reconstruct
what happened, why, and what it cost.

## What the wallet is

**OVR-1** The wallet is one **engine** — the decision-and-admission core — embedded in a
**host**, which decides when the engine runs and never what it decides, and used through
**frontends**, which talk to the engine and never schedule, supervise or admit work
(`CONTEXT.md` **Engine**, **Host**, **Frontend**; `ADR-0031`). Every resident host MUST embed the
same engine, so that the frontends "behave identically" (`ADR-0031`) by construction. The hosts
and frontends a compliant wallet provides, and the contract of each, are
`08-hosts-and-deployment.md`.

**OVR-2** Every money operation MUST be a durable, idempotency-keyed intent, recorded before any
network call, and MUST be resumable after a crash at any point without paying twice
(`03-operation-lifecycle.md`, `CNF-12`). This is the property the rest of the design protects.

**OVR-3** A money operation's network IO MUST NOT block another's start: admission is
millisecond bookkeeping, and the waiting happens inside the operation, never at the point that
admits it (`ADR-0024`, `CNF-21`).

**OVR-4** Every operation the wallet performs, fails, or refuses to perform — a funding
shortfall it defers below the route floor and a duplicate it drops included — MUST be written
to the append-only ledger as a row. An intent-backed row MUST be written in the same
transaction as the intent transition it describes (`STO-16`), so it is never missing. A row
that describes no intent is written best-effort — `ALC-34`: "Every ledger write around a tick
is best-effort (warn on error) except the money path" — so a failed write of one MUST NOT fail
the work it records, and such a row MAY be absent after a storage error and for no other
reason; `approve` is the exception, whose row shares the candidate promotion's transaction
(`STO-26`). History without failures is not history.

**OVR-5** The allocator MUST fund only what a probe has proven. A discovered federation
becomes fundable after a sustained window of real sats-spending round trips passes, never on
discovery alone (`ALC-37`, `ADR-0017`).

**OVR-6** An allocator decision MUST depend only on its inputs — a snapshot gathered before
the decision is made (the policy's targets and caps, balances, probes, reservations, route
prices), the occurrence it plans for, and the goal blockers in force — and on nothing observed after the snapshot was taken: two
decisions over the same inputs are identical (`ALC-1`).

**OVR-7** An **evacuation's** enforced fee cap MUST be computed from what the destination is
actually credited, never from the amount asked for (`ALC-21`); a cap computed on an amount nobody
received bounds nothing. A funding `Move` keeps the proportional cap the allocator stamped on the
planned amount even when delivery settles a hair under: the amount is revised and the cap is not,
which errs conservatively by a few msat (`OPS-22`, `OPS-24`).

**OVR-8** The user's standing instruction's parameters are one stored `Policy`, edited at
runtime through the wallet's own surfaces and never through a host config file (`STO-13`,
`API-20`).

## System context

```
   frontends  ──────────►  host  (embeds the engine; owns cadence, restart, config)
   (CLI, web UI,             │
    Android UI)              │   engine: admission, intents, ledger, allocator, reconcile
                             │        │
                             │        ▼
                             │   the wallet's two stores: the fedimint client's, and
                             │   the journal (intents, ledger, registry, candidates,
                             │   probes, watch state, policy)   `05-persistence.md`
                             ▼
       federations (guardian APIs) ◄──► lnv2 gateways ◄──► Lightning
       Fedimint Observer (discovery only, untrusted; `ADR-0020`)
```

**OVR-9** Exactly one process owns the wallet's stores at a time: a second opener MUST block or
be refused, and MUST never open them alongside the first (`STO-2`, `HST-1`). A one-shot
standalone host takes the same exclusive ownership and drives the same engine, and every intent
it admits — the agent's probe legs included — MUST pass through the engine's one admission
point, with the single exception `ADR-0031` documents: the standalone tick, "a deliberately
isolated compatibility exception, not a resident host or a model for a future frontend".

**OVR-10** A host drives; the engine decides. A host MAY drive the engine from a resident loop
or from platform wakes, and a cycle so driven MUST be safe to run at any time, overlapping
another or not, without duplicating work — `ADR-0031`: "an arbitrary, possibly-overlapping 'run
a cycle now' cannot duplicate work unless the goal model itself fails" — because the engine, not
the host, owns admission (`CONTEXT.md` **Host**).

## Non-goals, decided

**OVR-11** No on-chain evacuation (`ADR-0004`, `ADR-0018`), no Cashu, no iOS, no multi-device,
and no LNURL or Lightning Address in this version — the last per `ADR-0004` as amended, which
defers Lightning Address and LNURL-pay to v2+ together with their provider, recurringd
(`ADR-0013`).

**OVR-12** No Tor. Reliability over network anonymity; "private" means no KYC, a blind provider,
and private receives, not network-level anonymity (`ADR-0002`, `CONTEXT.md` **Private**).

**OVR-13** A two-gateway Lightning route is a non-goal for ordinary movement. Every ordinary move
resolves one gateway that validates at both federations. Evacuation is the decided exception: when
no gateway serves both federations, an evacuation MUST fall through to a hop over two gateways on
different Lightning nodes, each leg chosen from its own federation's vetted list — `ADR-0029`,
"a second route when no gateway is shared", where "the hop is tried in the same tick".

**OVR-14** No compatibility shims. A persisted type changes only by gaining fields — a field so
added MUST decode when absent from a stored row, and a row written by a newer build MUST stay
readable by the build before it (`STO-29`–`STO-31`, which own the reference encoding) — with one
exception: `OperationKind` MAY gain a variant for a new kind of operation (`STO-15`), and a row
of a kind a build does not know MUST be skipped by that build as an unreadable row and MUST
fence nothing in it (`STO-22`), so a rollback past the variant's introduction still starts and
runs.

## What this document does not decide

Whether the engine ships on by default is open at the product level (`11-open-questions.md`).
