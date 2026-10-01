---
status: accepted
---
# The standing instruction is acknowledged when the wallet is created or restored; a store's existence is the proof

`ADR-0014` requires an explicit, plain-language, gating acknowledgement "BEFORE any funds are
received", and the set had no requirement that records it or gates on it (`spec-dn8`): no
acceptance route, no row on disk, no admission check. The review offered runtime gates —
refuse receives, or every money operation, or only the agent, until a stored acceptance
exists. Decided on 2026-09-25: none of those.

**Decided.** The acknowledgement gates the wallet's **creation and restoration**, not its
operations. `walletd init`, the standalone mode's first run and `restore-mnemonic` require the
user or operator to accept the standing instruction explicitly — a flag naming it, or a TTY
prompt that shows the `ADR-0014` text — and refuse to create or restore a store without it,
leaving nothing behind (`HST-29`). The store records the acceptance in its creation write, so
**a store that exists was acknowledged**: no requirement checks a runtime acknowledgement
state, no route accepts one, and no operation is refused for lacking one. The seeded policy
row is still not the acknowledgement; the explicit acceptance at creation is, and `init`
cannot supply it silently.

**A backup that carries the acceptance restores without asking** (decided 2026-09-29). The
acceptance record — that the standing instruction was accepted, which text, and when — travels
in any backup that can carry it, and a restore from such a backup creates the store with that
record and no prompt. Android's silent Block Store restore (`ADR-0003`) is the case this serves.
A restore from a source that carries no acceptance record — a twelve-word mnemonic, whether
through `walletd restore-mnemonic` or Android's manual seed export — still requires the explicit
acceptance above. Either way the rule holds: every store was created with an acceptance, either
given on that device or carried from the one that gave it.

**Stores older than this decision.** The set is greenfield (`ADR-0033`, `ADR-0038`): it
specifies no compatibility rule for a store created before the acceptance record existed. Such a
store cannot be served anyway — it holds no encrypted seed slot, so `ADR-0033` refuses to start
it — and its only path forward is restoring its mnemonic into a new store, which requires the
acceptance like any other restore. No store therefore runs the agent without one.

**Why.** "Before any funds are received" is satisfied at the earliest possible point — before
the wallet that could receive them exists — with one gate instead of a per-operation one, and
without a second consent state that recovery, migration and hosts would each have to carry.
A restored store spends and receives as soon as it exists because restoring it required the
same acceptance.

**Rejected.** A runtime gate on inbound receipt, on every money operation, or on the agent
only: each adds a stored consent state, an acceptance surface, a refusal reason and an
environment change to chapter 10, for a distinction the creation gate already makes. Treating
the seeded policy row as the acknowledgement: `init` writes it without the user.

**Consequences.** `spec-dn8` narrows to: an owning requirement (a new domain rule under the next free `DOM` identifier)
stating the acknowledgement's content, that creation and restoration require it, that the
store records it, and that its existence is the proof; `HST-4` (`init`), `HST-10` (the
standalone flag), the `restore-mnemonic` contract and `FMI-31`/`SEC-11` cite it; the CLI
grammar (`spec-ee9`) gains the flag; chapter 10's environment says its stores were created
with the acceptance. The backup unit gains the acceptance record wherever the backup can carry
it: `ADR-0003`'s Block Store payload, `ADR-0025`'s backup unit, `SEC-24` and `FMI-32` change with
it. Chapter 11's question 1 — whether onboarding presents automated
management as the default posture or as an opt-in — was answered by `ADR-0039`: every wallet
is auto-managed.
