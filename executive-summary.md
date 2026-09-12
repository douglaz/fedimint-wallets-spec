# fedimint-wallets — Executive summary

*A single-file orientation to the specification, for a reader who has never seen the code.*

---

## 1. What this is

A **spending** wallet for Fedimint ecash, built for someone who would otherwise use a custodial
Lightning wallet and wants to not be custodied. It holds small balances across two or more
federations, pays and receives over Lightning through the federations' gateways, and — this is
the part that is novel — runs an on-device **allocator** that moves the balance between
federations on the user's standing instruction: topping up the one used for spending, keeping a
warm standby in another, and evacuating a federation that announces it is shutting down. A
federation is treated as **ephemeral**: it may degrade or vanish, and the wallet's job is to make
sure that never leaves the user unable to spend (`ADR-0001`, `ADR-0006`).

The wallet is a **headless engine** embedded in hosts: a 24/7 daemon (`walletd`) that serves it
behind a loopback HTTP API, a CLI that is a thin client of that API and can also drive the engine
one-shot, a browser sidecar (`ADR-0028`), and an Android app (`ADR-0003`, `ADR-0011`). Every host
embeds the same engine and every frontend sees the same behaviour (`ADR-0031`,
`08-hosts-and-deployment.md`).

This set is **prescriptive** (`ADR-0032`): it says what a compliant wallet must do, not what any
implementation does. Where the implementation in
[`douglaz/fedimint-wallets`](https://github.com/douglaz/fedimint-wallets) falls short, that
repository's `docs/open-findings.md` says so, one item per tracked issue.

## 2. The four ideas everything else follows from

**A money operation is a durable intent, not a function call.** Every pay, receive, move, join
and recovery is written to a journal under an idempotency key *before* any network call, then
driven by a task that can be killed at any point and resumed by a reconcile pass. The
cross-federation move — two Lightning legs, through one gateway that serves both federations or
two when none does — survives a crash at four named
points without paying twice or minting a second payable invoice, because the fedimint client's
deterministic operation ids and the journal's compare-and-swap writers together make the second
attempt attach to the first (`03-operation-lifecycle.md`, `CNF-12`).

**Nothing blocks anything else.** A Lightning payment can be held for hours. So no operation's
network IO ever runs on the serialized admission point; admission is millisecond bookkeeping and
per-operation driver tasks do the waiting. A pay issued while a probe is stuck reaches its first
external call in under 250 ms (`ADR-0024`, `CNF-21`).

**The ledger is the user's record, and it is append-only.** Every operation — including every
failure and every refusal — is one row in a sequence-numbered ledger; an intent-backed row is
written in the same transaction as the intent transition it describes (`OVR-4`). Nothing deletes
a row. A terminal row is immutable. A retry is a new row. The history verb reconstructs a whole
session (`05-persistence.md`, `CNF-15`).

**The allocator only ever spends what a probe has proven.** A federation the wallet discovered
on its own is fundable only after a sustained window of real, sats-spending round-trip probes
has passed; reputation feeds and metadata can demote a candidate but never promote one. A
federation the user joined by hand is trusted as the user's own decision — unless the agent had
already auto-joined it, in which case only the audited `approve` verb releases the gate (`ADR-0017`,
`06-allocator-and-automation.md`).

## 3. What the wallet does, in one paragraph each

**Money.** Join a federation; receive (fee deducted from the invoice) and direct-inflow (invoice
grossed up so the destination is credited the requested amount, never over and at most one
receive-fee step under); pay a BOLT11 invoice choosing the cheapest gateway that fits a fee cap;
move between federations as an internal swap through a gateway both ends validate, or over a
Lightning hop between two gateways when no gateway serves both (`ADR-0029`); recover ecash from
the twelve-word seed plus the federation's invite, into a fresh partition, never wiping anything
(`ADR-0025`).

**Decision.** Once per cycle the engine probes every open federation (no sats spent), scores them
structurally (guardian count, threshold, modules, mainnet), builds a snapshot with balances and
in-flight reservations, prices the funding routes (a per-pair economic floor below which a move
costs more than it is worth), and asks a pure function what to do. It emits at most a top-up
move, a standby move, and an evacuation per dying federation, each with a fee cap: proportional
for funding moves, base-plus-proportional for evacuations, computed on what the destination is
actually credited (`ADR-0029`).

**Safety.** Per-federation balance cap enforced at plan time and again before minting. A route
that is uneconomic at any size blocks funding and says so in the ledger. One federation's stuck
operation never suppresses decisions for the others. An evacuation that cannot fit its cap at any
amount is marked with durable evidence, and a qualifying cap increase atomically retires it and
admits a linked successor. An unopened federation fences all planning and reports why on
`/v1/health`; so does a corrupt registry row.

**Host.** The daemon owns both stores exclusively — a second process that opens them is refused —
serves the HTTP API behind a bearer token,
runs the scheduler with adaptive sleep, wakes early for a federation's announced expiry, restarts
itself on a settlement stall, and refuses to start on an invalid stored policy. The CLI's
`--standalone` mode drives the same engine one-shot under the same exclusive ownership.

## 4. How to use this set

Read `00`, `01` and `03` first. Every requirement carries a stable identifier and is written to
be checked at one of the wallet's boundaries; `10-conformance-checklist.md` holds the scenarios a
conformant implementation must pass. Decisions and the alternatives they rejected are in
`docs/adr/`; the vocabulary is `CONTEXT.md`; the one product decision still open is in
`11-open-questions.md`. What the existing implementation has demonstrated, and where it falls
short, is the code repository's to say.
