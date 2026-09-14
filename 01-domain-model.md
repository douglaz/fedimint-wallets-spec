# 01 — Domain model

The entities a compliant wallet has, and their states. Vocabulary is `CONTEXT.md`'s. A type
named here in backticks is a persisted or serialized shape, or a fedimint protocol type; the
name is part of the shape, not of any implementation (`ADR-0032`).

## Federation

**DOM-1** A **federation** is identified by its 32-byte `FederationId`. The wallet knows a
federation through up to three durable records: a **registry row** (`STO-14`: invite, database
prefix, joined-at seconds), whose presence means the wallet has joined it; a **client
partition** in the fedimint client's store (`STO-3`) holding that client's state and ecash; and
optionally a **candidate row** (`DOM-12`) from discovery.

**DOM-2** A joined federation is in one of two runtime states: **open** — the wallet holds a
live client for it and can transact — or **registered-but-unopened** — a registry row exists
and no live client does, because opening the partition failed at startup or because a recovery
has committed the registry row and not yet made the client available. The distinction is held
in memory only; no durable record marks a federation as unopened (`STO-27`). The wallet MUST NOT plan from a world that contains an unopened federation:
every whole-world planning surface refuses to plan while any federation is in it (`ALC-46`).

**DOM-3** A federation is **eligible to fund** when the light probe's verdict holds — the
structural floor passes, the quorum is live and a gateway is available (`ALC-15`) — or the
operator has pinned it as spending or standby; and, in either case, only when it is not
probe-gated, or it is probe-gated and its active-probe verdict is `Passed` (`DOM-12`,
`ALC-37`). A pin overrides the scorer; nothing overrides the probe gate.

**DOM-4** The **spending federation** and the **standby federation** are each either pinned in
`Policy` or auto-designated every cycle from the eligible set, ordered by rank descending, then
spendable balance descending, then id ascending (`ALC-16`). A probe-gated federation whose
verdict is `Passed` MAY be auto-designated standby and MUST NOT be auto-designated spending; a
pinned federation is not in the auto-designated set.

## Operation and intent

**DOM-5** An **operation** is the user-facing unit of activity, identified by its **operation
key** (a correlation key, `STO-6`) and listed by `history` (`API-10`). Every operation has
exactly one current ledger row (`STO-20`). Operation kinds: `join, recover, receive, pay,
direct-inflow, move, evacuation, refusal, probe, tick, discover, autojoin, approve` (`STO-15`).

**DOM-6** An **intent** is the durable record that drives an *executable* operation: the money
verbs, `join` and `recover`. It carries an `Action` (`DOM-7`), an attempt counter, a status
(`DOM-8`), the actor (`DOM-9`) and, on an agent evacuation, optional refusal evidence
(`DOM-19`); the persisted shape is `STO-9`. Intents never appear in a frontend's type names or
copy (`CONTEXT.md` **Intent**).

**DOM-7** `Action` has eight variants; seven are executable:

| Variant | Who builds it | Note |
|---|---|---|
| `DirectInflow {to, amount, fee_cap}` | user | invoice grossed up so `to` nets `amount`: never over, possibly under by a bounded receive-fee step (`FMI-15`) |
| `Move {from, to, amount, fee_cap, gateway?}` | allocator (funding), user, probe legs | `gateway` is a route hint (`CONTEXT.md` **Route hint**) |
| `Evacuate {from, to, amount, fee_cap, gateway?, fee_cap_components?}` | allocator only | `fee_cap` is the planning cap; the components recompute the enforced cap from the delivered net (`OVR-7`) |
| `Pay {from, invoice, amount, fee_cap, payment_hash, gateway?}` | user | |
| `Receive {to, amount, fee_cap, nonce, gateway?}` | user | fees deducted from `amount` |
| `Join {federation, invite, membership_preexisting}` | user only | auto-join builds no intent: it leaves only its nonce-keyed ledger row (`STO-6`, `FMI-8`, `ALC-4`) |
| `Recover {federation, invite}` | user only | the allocator MUST NOT emit it |
| `RefuseInflow {fed, reason, diagnostics}` | allocator | **not executable**; becomes a refusal row, never an intent |

**DOM-8** `IntentStatus` ∈ `Pending, Executing, Awaiting, Done, Failed`. `Pending`: journaled,
owned by no driver, re-drivable. `Executing`: claimed from `Pending` by one driver — the
transition is exclusive, and a losing claimant performs no IO (`OPS-43`); how an intent found
`Executing` after a restart is resumed is the lifecycle's (`OPS-35`, `OPS-43`), and it never
pays twice (`OVR-2`). `Awaiting`: the effect was issued and completion depends on an external
event — a direct-inflow payer, or a raw pay's or receive's settlement — so it is never
re-performed. `Done`: terminal success, held in no status index, so finished work is never
scanned (`STO-10`). `Failed`: terminal and indexed; retryable only by an explicit user action
that mints a new attempt (`OPS-2`, `OPS-10`).

**DOM-9** `Actor` is `User` or `Agent {occurrence}`. The actor is the audit discriminator
`ADR-0014` needs; it also decides which admission checks apply (`OPS-6`) and which intents hold
allocator goals (`DOM-17`).

**DOM-10** A **move record** is the derived cache of a two-leg operation: both legs' operation
ids, the invoice, the gateway, the enforced fee cap, the quoted fees, the preimage, and a
`MovePhase ∈ Created, Invoiced, Sending, Settled, Refunded, Failed, Stranded`. `STO-11` owns
the field list and which fields the wallet rebuilds from the fedimint operation log; `STO-33`
owns the operation metadata they are rebuilt from.
**Stranded** means exactly what `OPS-27` states — "a settled send with a preimage and an
op-terminal non-claim on the receive". It is not a gateway failure and the preimage does not
recover it (`DEF-20`).

## The ledger row

**DOM-11** An `OperationRecord` is one row per operation: `seq` (the ordering authority),
`correlation_key`, `kind`, `actor`, `reason`, `status ∈ Started, Awaiting, Succeeded, Failed`,
created and updated timestamps (which carry no ordering authority), `fees {fee_cap?,
receive_fee?, send_fee_quoted?}`, `error?`, and `repaired` (a terminal conclusion reached by
repair from absence of evidence, supersedable exactly once by an authoritative write).
`ReasonCode` ∈ `SpendingBelowTarget, StandbyBelowTarget, ShutdownNotice, Unhealthy, OverCap,
NotProbed, LowReputation, UneconomicRoute, UserInitiated, ActiveProbe, StandingInstruction`
(`STO-15`, `STO-16`).

## Candidates, probes, discovery

**DOM-12** A **candidate** is a federation discovery has seen: `id`, `invite`, `source ∈
Observer, Nostr, Manual` (the persisted variant set; no requirement in this set produces
`Nostr`), `structural ∈ Passed | Rejected(reason)`, and `state ∈ Rejected, Discovered,
AutoJoined, UserApproved`. `UserApproved` is conferred by `approve` from `AutoJoined`
(`API-23`), by a user `join` from any state that is not already `AutoJoined` (`OPS-42`), and by
seed recovery from any state (`STO-26`); once written it MUST NOT be demoted by any later write
(`STO-26`). A joined federation with no `UserApproved` row is **probe-gated** (`DOM-3`).

**DOM-13** A **probe record** per federation holds up to 256 `ProbeAttempt`s — `{at_ms: u64,
ok: bool, from: FederationId, amount_msat: u64, leg_fee_cap_msat: u64, error: String?}`, the
persisted field names verbatim — and at most one in-flight `ProbeSession` (`STO-26` owns both
shapes and the pruning rule). An **active-probe verdict** ∈ `Passed, NeverProbed, Insufficient,
Expired, Failed, FailedSinceLastPass` is computed, never stored, from the attempts, the source
federation and the policy's window (`ALC-25`).

**DOM-14** Two different things are called a probe. The **light probe** runs every cycle on
every open federation and spends nothing: structural facts, one threshold read for liveness,
gateway validation, balances, shutdown signals (`ALC-15`). The **active probe** spends real
sats — a leg of the policy's probe amount into the candidate, then a smaller leg back — to
prove that ecash minted there can be redeemed (`ALC-27`).

## Policy, occurrence, watch state

**DOM-15** `Policy` is the standing instruction's twenty-eight parameters, stored as one row
(`STO-13`) and never in a host config file (`OVR-8`). The wallet MUST validate the stored row
before running the engine under it, MUST refuse to run under an invalid one, and MUST reject an
edit that would store an invalid one (`API-20`). Balance knobs (`per_fed_cap`, `spending_target`,
`standby_target`, the two pins); three fee caps of three shapes (`max_fee` absolute, for user
verbs and probe legs; `max_fee_bps_of_move` proportional, for funding moves;
`evac_fee_base_msat` + `evac_fee_bps`, for evacuations); probe window and budget; scheduler
cadence; discovery caps; `auto_join`; `require_mainnet`.

**DOM-16** An **occurrence** is the allocation epoch stamped into every agent decision's key
(`STO-6`). It has three sources. A resident host's cycle allocates one by a checked increment
of the stored `WatchState.occurrence` (`STO-12`, `ALC-33`). A one-shot standalone tick takes
it from the operator (`--occurrence`) and records it as the floor. An active probe's legs
derive theirs from the session nonce — the first sixteen hex characters of the 32-character
nonce read as a `u64` — so a probe occurrence is a 64-bit random head that is reconstructible
from the stored `ProbeSession` alone (`STO-26`); the three sources share one `u64` space and
the key shape does not namespace them. The floor never decreases, is raised in the same
transaction as any agent ledger append (`STO-21`), and is fail-closed at the largest
representable value: a cycle MAY run at it exactly once, the wallet MUST fail every cycle after
it, and MUST refuse an operator-supplied occurrence equal to it (`ALC-33`, `STO-12`).

**DOM-17** An **allocator goal** is the identity a live intent holds against re-issue: a
**funding goal** into one destination for an agent funding move, an **evacuation goal** out of
one source for an agent evacuation. Goals exclude occurrence, amount, gateway and the other
endpoint. User intents and probe legs hold no
goal. A held goal suppresses only the candidate decisions that conflict with it (`ALC-30`,
`ALC-31`).

**DOM-21** An intent belongs to the actor that admitted it. A user request whose key resolves
to an intent an active probe admitted — a user move whose endpoints, amount and cap equal a
probe leg's and whose occurrence equals the leg's nonce head — MUST be refused as a `conflict`
(`API-6`: status 409, nothing journaled), whatever the leg's status; it is never attached to,
deduplicated against or retried. The rule is symmetric: a probe leg whose key resolves to a
user's intent is refused the same way, and the probe records no attempt, as for a preflight
failure (`ALC-27`). The key shape does not change (`STO-6`).

## Route economics

**DOM-18** **Route economics** for an ordered federation pair: an optional resolved gateway, a
minimum viable amount, and a status ∈ `Routable, Unroutable, UneconomicAtAnySize`, priced
afresh for each cycle from the gateways' fee quotes and supplied to the allocator's snapshot.
An absent entry means **unpriced**, which is permissive (`ALC-11`). `Unroutable` means no
candidate validated at both ends; `UneconomicAtAnySize` means a validated route whose fees
outrun the cap at every amount (`ALC-12`); `Routable` carries the economic floor (`ALC-10`).

## Evacuation refusal evidence and supersession

**DOM-19** `EvacFeeCap {base_msat: Msat, bps: u16}` with `at(net) = base_msat + floor(net ×
bps / 10 000)`. The sum MUST saturate at the largest representable value rather than wrap, so
no `(base, bps)` pair can produce a small cap. `EvacuationRefusalEvidence {cap_components:
EvacFeeCap, requested_net: Msat, source_spendable: Msat, low: EvacuationQuoteSample, high:
EvacuationQuoteSample, diagnostic: String, measured_at_ms: u64}` is two freshly quoted
delivered-net samples (`low`, `high`, each `EvacuationQuoteSample {delivered_net: Msat,
total_fee: Msat, fee_cap: Msat}`) plus the cap components admitted with, the requested net, the
source's spendable balance, a diagnostic string, and a unix-millisecond timestamp. It is
**evidence** that a refusal looks structural, never proof a route is unavailable (`ALC-24`). It
is persisted on the intent (`STO-9`) and in the supersession sidecar (`STO-25`).

**DOM-20** An **evacuation supersession** retires a marked pre-artifact agent evacuation as
`Failed` and admits a linked `Pending` child at a fresh occurrence and distinct key under a
qualifying cap increase, writing the forward and reverse audit links — the two sidecars
`STO-25` owns — in the same transaction (`OPS-30`). The parent's evidence and identity are preserved; a superseded parent
MUST never be retried.
