# 03 — Operation lifecycle

How a compliant wallet admits a money operation, executes it, resumes it after a crash and
terminalizes it. This is the part of the system the rest protects: a two-leg move killed at any
of four named points completes exactly once (`OVR-2`). Every requirement here states something
observable — what reaches a federation or gateway, what is journaled, what a frontend sees, what
survives a crash — and not how an implementation schedules or serializes the work. The
concurrency mechanism is the implementation's; its invariants are `OPS-13` (`ADR-0032`, "The
concurrency mechanism goes; its invariants stay"). A type or field named in backticks is a
persisted or serialized shape (`STO-9`, `STO-11`, `STO-33`) or a fedimint protocol type.

Vocabulary. A **perform** is one attempt to carry an intent forward by issuing, or re-issuing
under idempotency, its effect to a federation or gateway. A perform ends `Done`, `Awaiting`, or in
one of four **outcome classes** the whole set uses: `Retryable` — nothing terminal is known and
a later perform may succeed; `Permanent` — the intent fails; `StructuralEvacuationRefusal` — a
`Retryable` that carries refusal evidence (`DOM-19`); `Unsupported` — the action cannot be
performed at all. Error text quoted below is what the wallet records as the ledger row's `error`
(`STO-35`); where another requirement anchors on that text (`FMI-37`'s prefixes, `HST-32`'s
"send settled but receive was not credited"), the anchored part is normative and the rest of the
wording is informative.

## Intents and their states

**OPS-1** An executable operation is driven by an intent (`DOM-6`). Every lnv2 send or receive
an attempt issues MUST carry that attempt's correlation key in the operation's metadata
(`STO-33`, `STO-34`: the operation key on attempt 0, `retry:<len>:<key>:<n>` on attempt
`n > 0`), so that a resume finds the attempt's own operations and a retry can never adopt the
operations of the attempt that failed. A join or a recovery creates no such operation and carries
none.

**OPS-2** The status machine, which every durable writer MUST enforce (`STO-9`):

```
Pending   → Pending | Executing | Awaiting | Done | Failed
Executing → Pending | Executing | Awaiting | Done | Failed
Awaiting  → Awaiting | Done | Failed
Done      → Done
Failed    → Failed
```

`Failed → Pending` is not a transition. A retry is a separate write that mints a new attempt
(`OPS-10`).

**OPS-3** `Awaiting` is the state of an intent whose effect was issued and whose completion
depends on an external event: a direct inflow waiting for its payer, **and** a raw pay or receive
waiting for settlement. Reconcile MUST NOT re-perform an `Awaiting` intent; an awaiter owns it
(`OPS-16`). A raw pay that attaches to a send operation already settled goes `Executing → Done`
within the same perform and never enters `Awaiting` (`OPS-17`).

**OPS-4** How a perform's end is journaled: `Done` → `Done`; `Awaiting` → `Awaiting`;
`Retryable(msg)` → `Executing → Pending` with the refusal marker cleared; 
`StructuralEvacuationRefusal(evidence)` → `Pending` with `evacuation_refusal = evidence`
(`OPS-31`); `Permanent(msg)` → `Failed` with `msg` as the ledger row's `error`; `Unsupported` →
`Failed`, reachable only when a refusal reaches perform. A retryable outcome MUST NOT bump the
attempt counter. These dispositions apply to the perform's own outcome only. A journal write that
fails during a drive — the claim, the re-read, the status write after success, the retryable
reset — terminalizes nothing: the intent keeps the status of the last committed write and the
next reconcile pass picks it up (`OPS-43`). A journal failure MUST NOT produce a `Failed` intent.

## Admission

**OPS-5** Every user verb — whichever host and frontend it arrives through (`ADR-0031`) — MUST be
admitted as one user decision (`reason: UserInitiated`, `actor: User`) through the wallet's single
admission point (`OPS-13`), with the spendable balance of every **open** federation the verb names
sampled before admission and handed to it: `pay`: `from`; `move`: `from` and `to`; `receive` and
`direct-inflow`: `to`; `join` and `recover`: none. A federation that is joined but not open
(`DOM-2`) samples no balance and is treated as zero spendable on the source side (`API-18`); a
**fresh** request, or a retry (`OPS-10`), whose destination — `move`, `receive`,
`direct-inflow` — is joined but not open MUST be refused as destination-unavailable with nothing
journaled (`OPS-6`; `API-6`: 503). An
active probe's legs are agent work: they MUST be admitted through the same point, validated
against the probe's in-flight session (`ALC-27`, `OPS-6`), and each awaited to terminal
(`OPS-16`) under the host's perform timeout (`FMI-22`; `HST-2` names the daemon's setting), or
24 hours when none is configured. A verb of any host MUST NOT admit a money intent anywhere else
(`OPS-12`).

**OPS-6** Admission of a **fresh** key — one with no intent — runs these checks in this order,
and the first that fails is the outcome (`OPS-39` names each refusal reason, `OPS-38` the
destination-unavailable outcome, `API-6` the status of each):

1. a journal read fault → `storage_error`;
2. a goal-bearing agent decision (`DOM-17`) re-scans the live intents, and a conflicting holder
   → `conflict` (`ALC-30`);
3. a destination that is joined but not open → destination-unavailable (`OPS-5`, `OPS-38`);
4. a probe leg whose session is not its source federation's in-flight session → `conflict`;
5. the external driver cap — **32** at once, counting every user-originated intent being driven
   other than a probe leg or an evacuation, and every awaiter whatever its actor (`OPS-8`) — is
   full → `conflict` (`ADR-0024`: "a generous admission cap bounds externally-submitted
   totals");
6. a source federation held by an in-flight probe session → `fed_held_by_probe`, unless the
   request is that session's own leg or an evacuation, which preempts the probe (`OPS-35`);
7. the arithmetic of `OPS-7` against the sampled balances, the strict reservation projection
   (`OPS-9`) and the stored `Policy.per_fed_cap`.

On success the goal is recorded as held, the balance generation of every federation the action
touches and the membership generation MUST be advanced so that no allocator plan computed over
the world before this admission can commit (`OPS-13`, `ALC-32`), any probe preemption is applied,
and the intent is driven (`OPS-14`).

**OPS-7** The arithmetic admission MUST run with sampled balances on every fresh admission, every
retry (`OPS-10`) and every agent decision (`OPS-11`), and again at perform time before any new
funding (`OPS-45`): for `Move` and `Pay`, `amount + fee_cap ≤ balance[from] −
reservations.outbound(from)`, else `insufficient_after_reservations`; for `Move`, `Evacuate`,
`DirectInflow` and `Receive`, `balance[to] + reservations.inbound(to) + amount ≤ per_fed_cap`,
else `over_cap`. **`Evacuate` has no source-balance check at admission and no pre-fund admission
at perform time** (`OPS-45`); its money safety rests on perform-time sizing (`OPS-21`). `Join`
and `Recover` are admitted without arithmetic. An admission that skips the arithmetic because no
balance was sampled is not an admission.

The **hard cap** is one value: the stored `Policy.per_fed_cap` (`DOM-15`, `STO-13`), and every
entry point — a resident host's verbs, every standalone verb, an active probe's legs, an
evacuation's sizing — MUST enforce that value. A standalone `tick` or `status` MAY run under a
flag override, which MUST be validated and MUST NOT be persisted. A verb or a configuration
MUST NOT disable the cap (`ADR-0018`: "the `--allow-over-cap` flag no longer exists on any verb; the
refusal is `OPS-7`").

**OPS-8** Idempotency. A request whose key already exists **attaches** to the existing intent —
except that a user request whose key resolves to an intent an active probe admitted, or a probe
leg whose key resolves to a user's intent, MUST be refused `conflict` with nothing journaled
(`DOM-21`). By the existing status: `Done` → deduplicated with the existing outcome; `Pending` →
driven; `Executing` → re-performed without a claim (`OPS-43`); `Awaiting` → re-awaited
(`OPS-16`), counted against the driver cap (`OPS-6`) whatever its actor; a key a live driver
already owns → a re-drive is requested of that driver (`OPS-14`); `Failed` → the retry path
(`OPS-10`) for a `User` request. An `Agent` decision never attaches to a terminal key: in a batch
it is dropped as `conflict` (`ALC-53`); a probe leg or any other agent request that meets one
drives nothing and answers with the existing outcome (`OPS-10`).

What attach validates depends on the state. For a **terminal** key only the idempotency
**anchor** is checked — `Pay`: `payment_hash`; `Receive`: `to, amount, nonce`; `DirectInflow`:
`to, amount` (the action carries no nonce; the key does); `Join`: federation and invite; every
other action: full equality — and a change is refused `conflict` (`API-6`: 409), "same-key
request changed the completed operation's idempotency anchor"; a completed pay re-submitted with
a different `fee_cap` is therefore a deduplication, not a refusal. For a **live** key the sizing
fields are checked — `Pay`: `from, amount, fee_cap, payment_hash`; `Receive`: `to, amount,
fee_cap, nonce`; `Move`/`Evacuate`: `from, to, amount, fee_cap`, the gateway hint ignored;
`DirectInflow`: `to, amount, fee_cap`; `Join`/`Recover`: federation and invite — and a mismatch
is refused `sizing_conflict {field: "request sizing"}` (`API-6`: 422). An attach MUST NOT change
the stored `action, actor, reason, created_at_ms, max_fee, operation_id` or `invoice` (`STO-9`).
The accepted response does not say whether the admission was fresh or attached (`API-18`).

**OPS-9** Reservations are projected from every non-terminal intent (`Pending`, `Executing`,
`Awaiting`); a corrupt row fails the projection closed, so admission stops rather than
under-reserve (`STO-10`). The **strict** projection reserves every non-terminal intent's full
action: `Move`/`Evacuate` outbound `amount + fee_cap` on the source, inbound and target-credit
`amount` on the destination; `DirectInflow`/`Receive` inbound; `Pay` outbound. The **allocator**
projection weakens by move-record phase when the record is trusted (`Invoiced` keeps all three;
`Sending` drops the outbound; a terminal phase drops all; a `Pay` with an operation id reserves
nothing) and is what agent planning and commit use (`ALC-35`). User admission MUST use the strict
view.

**OPS-10** Retry. Only a `Failed` intent, only by a `User` request, only preserving the anchor
fields of `OPS-8`, never a `Failed` pay that recorded an operation id — refused `conflict`,
"this invoice already consumed its single payment attempt" (`FMI-17`) — and never a `Failed`
move whose move record's phase is `Stranded` — refused `conflict`, "this move's send already
settled" (`HST-32`: a retry would send again) — a refusal checked before every admission check
below, `API-19`'s destination check included. Before the write the retry
is admitted like a fresh key: an unopened destination (`OPS-5`), the driver cap and the probe
hold (`OPS-6`), and the arithmetic (`OPS-7`) on the refreshed intent against the strict
projection, the request's sampled balances and the stored cap. The retry write then, in one transaction (`STO-9`): writes `Pending` at
`attempt + 1`, deletes the cached move record, appends a fresh ledger row and repoints the key
index (`STO-20`), so the failed attempt and the retry are two truthful rows and the failed row's
error is kept verbatim (`STO-35`); the new attempt's effects carry its own correlation key
(`OPS-1`). Every durable writer is attempt-fenced: a write by a stale attempt writes nothing, and
a drive treats that as `Retryable`. An agent decision whose key is `Done`, `Awaiting` or `Failed`
is skipped, never retried; a new occurrence mints a new key.

**OPS-11** Agent decisions are admitted as one batch by the tick commit (`ALC-32`, `ALC-53`). The
batch MUST be refused whole on a stale policy generation (`ALC-41`), a changed world generation,
an invalid plan or balance-facts authority, or more than one occurrence; each decision is then
checked — a fresh destination balance, unchanged balance facts, terminal replay, goal conflict,
the admission watermark and, for a funding move, that the amount does not exceed the fresh target
shortfall — before the checks of `OPS-6`.

**OPS-12** Agent work — an allocator decision, an active probe's legs, an evacuation exchange —
MUST be admitted through the wallet's single admission point (`OPS-13`) and nowhere else
(`CONTEXT.md` **Engine**: "Admitting agent work anywhere else is reaching around the engine").
The one exception is `wallet-cli --standalone tick` (`ADR-0031`): a one-shot process that holds
the wallet's exclusive store lock, plans, re-scans the live intents for goal blockers itself
immediately before applying, and applies one batch under the same admission arithmetic
(`ALC-36`). It is not a resident engine and not the model for another host.

**OPS-13** The admission point. A compliant wallet MUST have exactly one serialized admission
point per store — a resident host's while one is resident (`ADR-0031`), or the one-shot
standalone process's while it holds the exclusive store lock (`HST-9`) — and:

- every admission (`OPS-5`–`OPS-12`), every intent status transition, every artifact write (an
  operation id, an invoice, a move record), every reservation-releasing write and every
  generation advance MUST pass through it or be serialized with it, so that two admissions never
  read the same reservation state and both succeed;
- it MUST hold at most one live key per allocator goal: a goal-bearing admission MUST refuse a
  candidate that conflicts with a held goal (`DOM-17`, `ALC-30` own the goal and the conflict
  rule);
- every write that changes a reservation MUST advance the balance generation of each federation
  it touches before any later allocator decision reads it, so that a plan computed over the
  earlier world cannot commit (`OPS-6`, `OPS-11`);
- it MUST perform no network IO: nothing that talks to a federation or gateway — a perform, an
  await, tick planning, route pricing — runs on it, so no operation's IO can delay another's
  admission (`OVR-3`, `ADR-0024`);
- every artifact write is **attempt-fenced**: it requires the intent at the expected key and
  attempt, else writes nothing, and the drive treats that as `Retryable`; a fenced write that
  applies wakes every waiter parked on the key (`OPS-16`); a write that errors advances the same
  generations a success would and is reported as a storage fault;
- a status write whose attempt mismatches, or whose transition `OPS-2` forbids, MUST write
  nothing.

Which task or thread does this is the implementation's (`ADR-0032`).

## Driving an intent

**OPS-14** Driving, as invariants; what task or thread does it is the implementation's
(`OPS-13`). At most one perform of a given key is in progress in a process at any time
(`OPS-43`), and at most one await (`OPS-16`). Ownership does not survive a restart and need not:
cross-restart exactly-once rests on the deterministic operation ids, the protocol's send dedup
and the operation-log backfill (`ADR-0024`), never on who owned the key. A re-drive requested
while a key is being driven (`OPS-8`) MUST NOT be lost: when that drive ends with the same
attempt, or a newer one, `Pending`, the intent MUST be re-performed without waiting for the next
reconcile pass; when it ends `Awaiting`, an awaiter MUST take the key over at once. Absent such
a request, a drive that ends `Retryable` leaves its `Pending` key unowned until the next
reconcile pass: there is no in-driver retry loop, so the retry cadence is the reconcile cadence
(`ALC-38`). Nothing on this path re-drives a planner-owned marker (`OPS-35`). A read fault while
ownership is released MUST cause a reconcile pass in preserve mode (`OPS-35`), retried with
bounded backoff until a scan completes.

**OPS-15** The per-intent perform timeout (`FMI-22`; `HST-2` names the daemon's setting) bounds
one perform. On expiry the wallet MUST abandon the drive — no further IO is issued from the
abandoned drive — MUST NOT terminalize the intent, and MUST leave it re-performable by a later
reconcile pass, at the same attempt (`OPS-4`), under
the executor's idempotency (`OPS-43`); whether it rests `Executing` until reconcile normalizes it
(`OPS-35`) or is reset to `Pending` at once is the implementation's. Join and recover MUST NOT
be timed out (`FMI-21` and `FMI-30` bound them). The transport bound `FMI-38` is the inner bound
and is not replaced by this one.

**OPS-43** The drive step is the only path by which a journaled intent is **performed** — issued
or re-issued to a federation or gateway — on every host. The one other route to network IO is
the awaiter of an `Awaiting` raw pay, receive or direct inflow, which awaits and never re-performs
(`OPS-16`). In order:

1. `Pending` → **claim**: one atomic `Pending → Executing` transition conditioned on the key and
   attempt, which blanks `evacuation_refusal` in the same transaction (`STO-9`). A claim that
   does not apply — another claimant won, a different attempt, an absent key, a forbidden
   transition — ends the step with no IO. A claim that errors ends the step with the error.
2. `Executing` → **no claim**: a crash-recovery resume or a concurrent scan re-performs under the
   executor's idempotency (`OPS-17`–`OPS-27`).
3. A key already being driven in this process ends the step with no IO (`OPS-14`); the key is
   drivable again once that drive completes or is abandoned (`OPS-15`).
4. Re-read the intent: it MUST be `Executing` at the same key and attempt, else the step ends (a
   stale scan); a read error ends it with the error.
5. Perform on the re-read intent, then journal the outcome as `OPS-4` states; an already-in-flight
   outcome journals as `Awaiting`, and `Unsupported` records `error = "executor does not support
   this action"`.

The status write after a successful perform is not conditional on the status: if it fails the
intent stays `Executing` with its side effect done, the next reconcile pass normalizes it to
`Pending` (`OPS-35`) and re-performs, and reassembly reaches the terminal it already has — a
`Settled` record completes with no new IO, a raw operation attaches by payment hash (`OPS-17`) or
correlation key (`OPS-18`). A failing retryable reset likewise leaves `Executing`; the reset
requires the current `Executing` attempt, else `Permanent`.

**OPS-45** Pre-fund admission runs inside every perform before any new funding is issued: for a
raw `Pay` after the hash lookup and invoice validation, for a raw `Receive` after the correlation
lookup, for `Move` and `DirectInflow` before reassembly (`OPS-20`). Endpoints: `Move` → source and
destination; `DirectInflow`, `Receive` → destination only; `Pay` → source only; `Evacuate`,
`Join`, `Recover` → none. It is skipped when the cached move record is trusted (`OPS-9`) and its
phase is `Sending | Settled | Refunded | Failed | Stranded`. Reservations are every other
non-terminal intent's; a scan failure → `Retryable("reservation scan failed before funding;
leaving the intent pending: …")`. An intent carrying an allocator goal (`DOM-17`: an agent `Move`
with a funding reason, or an agent `Evacuate`) uses the allocator projection, built from the move
records of the other live `Move`/`Evacuate`/`DirectInflow` intents (a record that fails to decode
keeps that intent strict, with a warning; any other read error → the same `Retryable`); every
other intent uses the strict projection. The source balance, and the destination's for an action
with a destination endpoint, are sampled fresh. Then the arithmetic of `OPS-7` under the stored
cap; its refusal is `Permanent` and terminalizes the intent.

**OPS-16** An **awaiter** owns an `Awaiting` intent. For a raw `Pay` or `Receive` it MUST:
require the intent's recorded operation id (absent → `Permanent`); wait for the protocol's final
state of that operation (`FMI-38` bounds each wait); map it to a ledger status — a send's
`Success → Succeeded`, `Refunded → Failed "send refunded"`, `Failed → Failed` with the detail; a
receive's `Claimed → Succeeded`, `Expired → Failed "receive expired"`, `Failed → Failed` with the
detail — under the error prefixes `FMI-37` requires; prepare the terminal (`OPS-46`) **before**
taking any exclusive hold, since preparation may read the federation; then, under the terminal
hold (`OPS-41`), finalize — the ledger advance and `Awaiting → Done | Failed` in one transaction,
adopting the observed operation id — and release the hold. A `DirectInflow` awaiter MUST: re-read
the intent (`Done | Failed` → finished; any status other than `Awaiting` → `Permanent`); backfill
the move record from the operation log (`OPS-20`); require the receive operation id (absent →
`Permanent`); wait for the receive's final state; then under the hold settle the record — phase
`Settled`, or `Failed` with the outcome "receive invoice expired before payment" or the
protocol's detail; a fenced write that does not apply → `Retryable` — and finalize (`Awaiting →
Done | Failed` conditioned on the attempt; a conditional write that does not apply is success,
the intent being already terminal).

Failure classification: an error raised **before** a final state is observed is `Retryable` when
transient and `Permanent` when the operation is missing, is not a Lightning operation, is of the
wrong kind for the role, or the federation lacks lnv2; **any** local error after the final state
was observed — preparation, finalization, taking or releasing the hold — is
`Retryable("post-terminal-observation local fault: …")` even when the underlying error is
`Permanent`, so an observed terminal is never lost to a local fault. A `Retryable` outcome waits
1 s, off the admission point, and retries ownership: a new awaiter runs only while the same
attempt is still `Awaiting`. A `Permanent` outcome writes `Failed` with `error = "service
awaiter permanent failure: …"`; if that write errors, the awaiter waits 1 s and retries ownership
instead.

A caller awaits an operation by key, target and deadline: an unknown key is not found
(`API-11`); target **invoice** resolves as soon as the intent's `invoice` or the move record's
`invoice` exists (`API-21`); target **terminal** resolves on `Done | Failed`; otherwise the caller
is parked and every transition on the key re-evaluates it; the deadline is a timeout (`API-6`:
504).

**OPS-41** While a raw operation's terminal write (`OPS-16`, `OPS-46`) or a membership change (a
join, an open, a recovery commit) is in progress, the wallet MUST NOT issue or validate a tick
plan or balance facts (`ALC-32`), so one raw terminal's database write fences all tick planning
for its duration. `ADR-0024` calls the raw terminal write "the narrow money-intent exception":
it is the one write a driver serializes with admission after its network IO has completed, and
nothing is ever serialized with admission across network IO.

**OPS-46** Raw terminal preparation and finalization. Preparation runs with no hold taken and
yields a **not-recording** preparation — one that will advance no ledger row — when: the key has
no ledger row; the row's repair fence (`STO-24`: seq, federation, role, operation id, status)
cannot be captured; the fence's attempt is not this attempt; the row does not match the role,
federation and operation; or the row records no operation id and the operation log's entry for
the attempt's correlation key (`STO-34`) is not exactly this operation. Otherwise it observes the
operation without blocking: no final state → `Retryable("raw operation {op} for --key {key} is
still in flight")`; a final state gives the observed status (`Succeeded`/`Failed`) and the
definitive fee. Finalization: a not-recording preparation takes the stale check below; a status
that conflicts with the observed one → `Permanent("raw terminal status … conflicts with observed
…")`; else one transaction that requires the intent at the fence's attempt, the action/role pair
`Pay`/send or `Receive`/receive, a non-terminal status whose transition to the target `OPS-2`
allows, and the action's federation equal to the fence's; adopts the observed operation id (a
**different** recorded id → no-op); advances the ledger row only if it is still at the fence's
seq, federation, role and operation id **and** at the fence's expected status — or is already an
unrepaired terminal equal to the target, in which case only the intent is written; then writes
the intent `Done`/`Failed` with the error. A no-op leaves the intent as it is: if the same
attempt is still non-terminal → `Retryable("raw terminal {preparation|fence} no-op left attempt
{n} for --key {key} non-terminal; retrying ownership")`, else success. `OPS-16` maps every error
here to `Retryable`.

## Perform, per action

**OPS-17** `Pay`. First look for the newest lnv2 send operation on `from` whose invoice carries
the payment hash, and observe it without blocking:

| found | disposition |
|---|---|
| none | issue a payment (below) |
| not final, `attempt > 0` | `Retryable("payment hash is still in flight for an earlier attempt")` |
| not final, `attempt == 0` | record the operation id (fenced; stale → `Retryable`), return already in flight |
| final, succeeded | record the operation id, then the ledger `Succeeded` with definitive fees (fenced; stale → `Retryable`), return **`Done`** — no awaiter ever runs |
| final, refunded or failed | ignored; issue a payment (below) — the protocol's per-invoice dedup returns the same dead operation as already in flight (`FMI-17`) and the awaiter terminalizes it |

Issue: parse the invoice (`Permanent("parsing raw pay invoice: …")`) and reject an expired one
(`Permanent("raw pay invoice has expired")`); pre-fund admission (`OPS-45`). Candidates: the
break-glass gateway armed for this key alone, else the source's vetted list (`FMI-12`); the
action's `gateway` field is never consulted and there is no pin (`ADR-0030`). Per candidate,
`gw_quote` = the gateway's send fee on the amount (`FMI-18`) and `fed_quote` = the federation's
send quote on `amount + gw_quote`; either quote failing skips the candidate; keep the cheapest
`gw_quote + fed_quote ≤ fee_cap`. None kept: some candidate quoted → `Permanent("raw pay fee
quote {lowest} msat exceeds fee cap {cap} msat")`; nothing quoted from the vetted list →
`Permanent("no lnv2 gateway produced a send fee quote for federation {hex}")`; nothing quoted
from a break-glass → `Retryable("break-glass gateway {url} produced no send fee quote for
federation {hex}")`. Issue the lnv2 send through the chosen gateway with the raw metadata
(`STO-34`); the protocol's refusals classify per `FMI-17`. Persist the operation id (fenced;
stale → `Retryable`) and return `Awaiting` for a started send, already in flight for a
deduplicated one (both journal as `Awaiting`). A crash between the send and the artifact write is
recovered by the hash lookup above. Terminalization is the awaiter's (`OPS-16`).

**OPS-18** `Receive`. If the intent records an operation id: require the intent's `invoice`
(`Permanent`), run the committed-fee check below and return `Awaiting`. Else look in the
destination's operation log for a receive carrying this attempt's correlation key (`STO-34`,
`FMI-16`): found → committed-fee check, record the operation id and invoice (fenced; stale →
`Retryable`), return already in flight. Else pre-fund admission (`OPS-45`, destination only) and
candidates as for pay (the break-glass for this key, else the destination's vetted list); per
candidate `gw_quote` = the gateway's receive fee on `amount`, the contract `= amount − gw_quote`,
which MUST be `≥ 5 000` msat (`FMI-16`), then `fed_quote` = the federation's receive quote on the
contract; a failed gateway or federation quote marks "quote unavailable" and skips the
candidate; keep the cheapest `gw_quote + fed_quote ≤ fee_cap`. None kept:

| observed | disposition |
|---|---|
| some total quoted, **every** candidate quoted | `Permanent("raw receive fee quote {lowest} msat exceeds fee cap {cap} msat")` |
| some total quoted, a quote was unavailable | `Retryable` with the same text |
| no total, a minimum-contract refusal, every candidate quoted | `Permanent("raw receive amount too small: net {amount} msat produces a {contract} msat incoming contract; lnv2 requires at least 5000 msat")` |
| otherwise | `Retryable("no lnv2 gateway produced a receive fee quote for federation {hex}")`, or `"break-glass gateway {url} produced no receive fee quote for federation {hex}"` |

Issue the lnv2 receive for `amount` — **not grossed up** — through the chosen gateway with the
raw metadata (`STO-34`) and invoice expiry 3 600 s (`FMI-16`); an error → `Retryable`. The
committed-fee check: read the committed contract; `actual = amount − committed + the
federation's receive quote on committed`; `actual > fee_cap` → persist the operation id and
invoice **first**, so the orphan is recorded, then `Permanent("raw receive committed fee {actual}
msat exceeds fee cap {cap} msat")`. Persist the operation id and invoice (fenced; stale →
`Retryable`), return `Awaiting`.

**OPS-19** `DirectInflow`, `Move` and `Evacuate` share one plan and one step loop: `Move` and
`Evacuate` are send-required with a source; `DirectInflow` is receive-only; only `Evacuate`
carries `fee_cap_components`. The gateway hint is not on the plan. Where pre-fund admission runs
in the loop, and when it is skipped, is `OPS-45`.

**OPS-20** Reassembly reconstructs the working move record from the cached record (`STO-11`)
plus the operation log of the destination (and of the source, when distinct), filtered by
`move_id == this attempt's correlation key` (`STO-33`). The backfill reads the operation log
newest-first to exhaustion; per leg the **first** (newest) matching artifact wins; a receive
artifact without an invoice is dropped entirely (never a receive operation id without its
invoice); `amount` is the first matching artifact's, either leg; `fee_cap` the first artifact
carrying one. Precedence: amount — artifact > cached > planned; cap — artifact > cached > the
action's cap rule at the reassembled `amount` (`OPS-21`: the components, or `{base: the
intent's fee_cap, bps: 0}` for an intent without them), where the cached cap counts only when
the cache holds a receive or send operation id. So a committed leg whose metadata carries no `fee_cap` (an
operation an older build wrote, `STO-33`) reconstructs the cap enforced at the net it was
committed at (`STO-17`, `DEF-4`; `ADR-0029`: "the cap enforced at that net"; `CONTEXT.md`
**Delivered net**), never the planning cap at the planned amount; a pre-artifact record is
re-sized by `OPS-21` before anything commits. A leg the
artifacts do not supply keeps the cached operation id and invoice; `outcome`, `preimage` and both
quoted fees come only from the cache. Phase: a cached terminal phase (`Settled | Refunded |
Failed | Stranded`) is preserved; otherwise a send operation id → `Sending`, else an invoice →
`Invoiced`, else `Created`. Gateway (`FMI-14`; `ADR-0030` rule 4, "Committed routes replay;
drafts never do"): a move is **committed** when the cache holds an invoice, a receive or a send
operation id, **or** the operation log recovered an artifact for this attempt. Not committed →
the break-glass for this key, else resolve afresh: a draft's cached gateway is **never**
replayed, send-required or not. Committed → the route MUST replay as recorded, from the cache
and, after cache loss, from the `gateway` — and, for a hop, the `send_gateway` — the committed
leg's metadata carries (`STO-33`) —
`CONTEXT.md` **Committed route**: "a restart cannot pay through a different gateway than the one
the invoice was sized for" — and MUST NOT be re-resolved. The one exception is an operation
committed before the route was persisted with the leg: a committed send-required move whose
recovered metadata carries no `gateway` has no committed route to replay and is re-resolved as
a draft is, under the same fee cap, which the pay step re-checks (`OPS-26`); `CONTEXT.md`
**Committed route** names this exception. A committed receive-only move recovered without a cache takes the
`gateway` its metadata carries; when the metadata carries none it carries the local sentinel
gateway string `recovered-receive-only-gateway-not-used`, since no send leg will use it.

**OPS-21** `Evacuate` only, and only while no artifact exists (no invoice, receive or send
operation id): size the fresh evacuation. The ask is the **action's** `amount`, not the cached
one — a pre-artifact record is re-sized from the intent every pass. Clamp the ask to the
destination's cap room: `room = per_fed_cap − balance(to)` saturating; `room == 0` →
`Permanent("no cap room at destination: federation {hex} holds {dest} msat at/above the per-fed
cap {cap} msat, so an evacuation cannot drain into it")`; else `desired = min(amount, room)`.
Read the source's spendable balance; take the cap rule from the action's components (an intent
without components uses `{base: the intent's fee_cap, bps: 0}`); snapshot one gateway fee per leg
for the whole search — the receive-leg gateway's receive fee at the destination and the
send-leg gateway's pre-invoice send fee as `FMI-18` assumes it (the swap fee `send_fee_minimum`
on a shared route, `send_fee_default` on a hop) — warning, never refusing, on a schedule outside
`FMI-19`'s limits (the protocol refuses at the send); run the search of `OPS-44` (`ALC-22`).
`Sized(n)` sets `rec.amount = n, rec.fee_cap = cap.at(n)`; `Refused(r)` is `Retryable("no
evacuable amount fits: desired {d} msat, source balance {s} msat, evacuation fee cap {base} msat
+ {bps} bps (retrying — a later tick may succeed once in-flight funds settle or the quote moves);
{r}")`; `StructuralRefused(evidence)` is the marker (`OPS-31`). A quote transport fault anywhere
in the search is `Retryable` and aborts it.

**OPS-44** The evacuation sizing search, given `desired`, `spendable`, `cap` and a quote `q(n)`.

*Quote*: `n = 0` → `Unquotable{shortfall: None}`; gross `n` up at the snapshotted receive
gateway fee (`FMI-18`, `OPS-22`'s fixed point); contract `< 5 000` msat → `Unquotable{None}`;
`send_gw` = the snapshotted send fee on the invoice; `send_tx` = the federation's send quote on
`invoice + send_gw`; the ecash module's insufficient-balance refusal → `Unquotable{shortfall:
requested − available}`; any other error → `Retryable` (aborts the search); else `Priced{invoice,
receive_quote, send_quote = send_gw + send_tx}` with `delivered = invoice − receive_quote`,
`total_fee = receive_quote + send_quote`, `source_debit = invoice + send_quote` (all saturating).

*Verdicts*: **affordable** iff `source_debit ≤ spendable`, shortfall `source_debit −
spendable`; an `Unquotable` candidate is never affordable, shortfall = the ecash module's gap or
the largest representable value when none; **fits cap** iff `total_fee ≤ cap.at(delivered)`
(exact-cap admitted); **combined** fits iff both, shortfall = `max(affordability shortfall,
total_fee − cap.at(delivered))` (0 for the cap term of an `Unquotable`).

*Constants*: floor `F = 5 000` msat; at most 8 boundary probes per boundary set; oscillation
bound `A = 6 + 2·(300·tiers + 100) + 2 100 + 2·ceil(spendable × 1 000 / 1 000 000)` with `tiers
= 64 − leading_zeros(max(spendable, 1))` (the ecash module's 100 msat base and 1 000 ppm
ceiling), saturating at the largest representable value — the bound on how far a quote may
oscillate around a candidate before the search gives up on it.

*Boundaries* (the ecash module's denominations are powers of two): `above(a, hi)` = for `k` from 63 down
to 0, `((a >> k) + 1) << k` when `≤ hi`, deduplicated, at most 8, largest first; `below(a, F)` =
for `k` from 0 up, `floor(a / 2^k) × 2^k − 1` while `≥ F`, deduplicated, at most 8, nearest
first.

*Bisection* `largest_fitting(F, hi, A, probe)`: `hi < F` → none; `lo = F − 1`; while `lo <
hi`: `mid = lo + ceil((hi − lo) / 2)`; `probe(mid)` fits → `lo = mid`; else if its shortfall
`≤ A` and some candidate of `above(mid, hi)`, probed in order, fits → `lo = that candidate`;
else `hi = mid − 1`. Result `lo` if `lo ≥ F`, else none.

*Search*: (1) fast path `q(desired)`: if `Priced`, affordable and fits cap → sized at `desired`;
if affordable, `hint = desired`. (2) `desired < F` → not sized. (3) pass 1: `p1 = desired` if
the fast path was affordable, else `p1 = largest_fitting(F, desired, A, affordability of q(·))`;
none → not sized. (4) re-quote `q(p1)`: not `Priced` → not sized; `hint = p1` iff affordable,
else `hint` cleared; combined fits → sized at `p1`. (5) pass 2: `p2 = largest_fitting(F, p1, A,
combined of q(·))`; if some `p2`, re-quote it and accept only if the fresh combined verdict fits.

*Viability post-check* on a sized `(n, cost)`: `total_fee ≤ delivered` → `Sized(n)`; else probe
`below(n, F)` in order and return `Sized` at the first candidate whose fresh quote is `Priced`
with `total_fee ≤ cap.at(delivered)`, `source_debit ≤ spendable` and `total_fee ≤ delivered`;
none → `Refused("the largest chunk this route can carry costs more than it delivers …")`, never
a marker.

*Diagnosis* (only when nothing was sized) — every branch is `Refused` (plain `Retryable`) except
the last: no `hint`; `q(hint)` not `Priced`; `q(hint).source_debit > spendable`; `q(hint)` fits
cap ("the cap no longer refuses …"); `q(F)` not `Priced`; `q(F).source_debit > spendable`;
otherwise `low = {delivered, total_fee, cap.at(delivered)}` from `q(F)`, `high` likewise from
`q(hint)`, and `ALC-24`'s `is_structural` → `StructuralRefused(EvacuationRefusalEvidence
{cap_components: cap, requested_net: desired, source_spendable: spendable, low, high, diagnostic,
measured_at_ms})` (`DOM-19`), else `Refused`. Only this branch produces the marker of `OPS-31`. A
probe's out leg runs the same search with `cap = {base: leg cap, bps: 0}` and no viability
post-check (`ALC-27`).

**OPS-22** Minting the invoice. Validate the source end of the gateway if send-required
(`FMI-13`; a failure → `Retryable`); enforce the destination cap unless `Evacuate` — `balance(to)
+ rec.amount > per_fed_cap` → `Permanent("destination would exceed the per-fed cap
({dest}+{amount} > {cap} msat) for federation {hex}")`; gross up at `rec.amount` (`FMI-18`; no
solution or a contract under the minimum → `Permanent("direct inflow amount too small: …")` for
every shape); record the receive quote on the record; **receive-leg cap check** `receive_quote ≤
cap_rule.at(requoted_delivered)` where `requoted_delivered = invoice − receive_quote` and
`cap_rule` is the action's components or `{base: rec.fee_cap, bps: 0}` — over is persisted
first, then `Retryable` for `Evacuate`, `Permanent` otherwise, message "fee over cap (receive
side {q} msat exceeds the {cap} msat cap at the {d} msat this would deliver)"; and for
`Evacuate` a viability pre-check `receive_quote > requoted_delivered` → persist, then
`Retryable`. Then `net` = the delivered net when it is under the ask, else the ask, and
`delivered_cap = cap_rule.at(net)`; nothing on the record is lowered before the receive commits.

**OPS-24** The persistence order at minting is load-bearing and MUST be: the draft record (phase
`Created`, gateway, receive quote, no invoice, no receive operation id) written **before** the
lnv2 receive is issued; the receive committed carrying `MoveMeta {move_id, role, amount: net,
fee_cap: delivered_cap, from, to, gateway, send_gateway?}` plus the quoted contract (`STO-33`);
the committed contract
read back and verified (`OPS-23`); **only then** — after `rec.amount := net` and `rec.fee_cap :=
delivered_cap` when `net < rec.amount` (a no-op cap for a non-evacuation rule) — the `invoice`,
the receive operation id and phase `Invoiced` written to the record. The order matters because
the artifact test of `OPS-21` is what stops a later pass from re-sizing a committed evacuation
against fresh prices; an implementation MUST NOT write the invoice before the contract is
verified. A move-shaped receive that commits and is then refused (`OPS-23`) leaves an orphaned
contract that expires unpaid (a raw receive's orphan is `OPS-18`'s: operation id and invoice
persisted first). The refusal MUST be written together
with what it orphans: the move record takes `amount := net`, `fee_cap := delivered_cap`, the
orphaned receive operation id and phase `Failed` with the refusal as its outcome — and MUST NOT
take the invoice, which is never surfaced (`OPS-23`) — so that the ledger row, refreshed to the
executed pair once a receive operation id exists (`STO-17`, `STO-15`'s `recv_op`), records the
amount and cap the contract was committed at and names the orphan, while the planned pair stays
on the intent (`STO-9`).

**OPS-23** The never-over check: the committed incoming contract MUST equal the quoted one, else
`Permanent` "gateway receive fee changed between quote and mint; re-run". The protocol re-reads
`routing_info` at mint time, so a fee drop would otherwise over-credit. The invoice is unpaid and
never surfaced; the orphan expires. The same check re-runs on every replay that skips minting; a
receive operation whose metadata carries no quoted contract is `Permanent("receive op is missing
the quoted contract amount; re-run under a fresh occurrence")`.

**OPS-25** The enforced cap survives replay because it is **in the receive operation's
`MoveMeta`** (`fee_cap`, absent meaning none and not zero, `STO-33`) and reassembly prefers that
over the planned cap once a leg is committed (`DEF-3`) — and, where a committed leg's metadata
carries none, recomputes the cap at the committed net instead of reading the planned one
(`OPS-20`). A crash plus cache loss cannot resurrect the planned-amount cap.

**OPS-26** The pay step: verify the recovered receive contract (`OPS-23`; the destination
federation not open → `Retryable`; missing or corrupt with it open → `Permanent`); parse the fixed
invoice; expired → `Permanent` "move invoice expired before the send leg could pay it"; re-quote
the send leg through the **send-leg gateway** — the recorded gateway on a shared route, the
recorded `send_gateway` on a hop (`STO-33`, `OVR-13`): `receive_quote = invoice_msat −
rec.amount`, `send_gw` = that gateway's send fee on the invoice (`FMI-18`), `send_quote =
send_gw` + the federation's send quote on `invoice_msat + send_gw` (a quote error →
`Retryable`); persist both quotes (this also restores
the receive quote after a cache loss); **both-leg cap check** on `rec.fee_cap`: the fixed receive
quote alone over the cap → `Permanent`, the total over → `Retryable`; for `Evacuate` the
viability check (`receive > net` → `Permanent`, `total > net` → `Retryable`); issue the lnv2
send through that same send-leg gateway, accepting a started or an already-in-flight outcome
(`FMI-17`); persist the send operation id, phase `Sending`.

**OPS-27** Awaiting settlement: await the **send first**. Any await error → `Retryable`,
reservations retained. `Success(preimage)` → persist the preimage **before** awaiting the receive;
any receive await error → `Retryable`; `Claimed → Settled`; `Expired | Failed → Stranded` with the
anchor string "send settled but receive was not credited". `Refunded → Refunded`; `Failed(msg) →
Failed` — what each `Failed` proves is `FMI-37`, and a forfeited send can still arrive as
`Success` (`FMI-23`). `Settled → Done`; every other terminal phase → `Permanent(outcome)`.
**Stranded is therefore exactly: a settled send with a preimage and an op-terminal non-claim on
the receive.** It is terminal; the allocator view releases both reservations for it. A move
perform is synchronous to `Done`; a direct inflow returns `Awaiting` after minting and is
finalized by its awaiter. A direct inflow that resumes with its invoice and receive operation id
recovered re-verifies the committed contract (`OPS-23`), re-persists the reassembled record and
returns `Awaiting` with no further IO.

**OPS-28** Four killpoints. A move MUST survive an uncatchable abort at each of these points and
complete exactly once on resume (`CNF-12` demonstrates all four):

| Killpoint | State on disk | Required resume |
|---|---|---|
| before the move record | receive committed; the record has no invoice or receive operation id | backfill by `move_id` (`OPS-20`); no second mint |
| after the receive commit | the record has the invoice, no send | proceed to the pay step (`OPS-26`) |
| before the send | invoice exists, no send | pay exactly once, by the protocol's dedup (`FMI-17`) |
| after the send commit | send committed; the record lacks the send operation id | backfill, or a re-pay deduplicates to already in flight |

At the first killpoint the gateway replays from the pre-receive draft `OPS-24` wrote; if that
cache is also lost, the committed route is recovered with the leg (`OPS-20`). How an
implementation injects the aborts to prove this is its own (`SEC-18`).

**OPS-29** Where fee caps bind, and on what base:

| Action | Pre-mint / pre-fund | Both legs | Base |
|---|---|---|---|
| Pay | cheapest `gw + fed ≤ fee_cap`, else `Permanent` | — | absolute `fee_cap` (default `max_fee`) |
| Receive | cheapest fitting, then committed-contract re-check | — | absolute |
| DirectInflow | receive leg ≤ `fee_cap` (`Permanent`) | — | absolute; gross-up bounded by it |
| Move | receive leg ≤ `fee_cap` (`Permanent`); fallback route priced at the amount | fixed receive + re-quoted send ≤ `fee_cap` | `floor(amount × max_fee_bps_of_move / 10 000)` stamped by the allocator (`ALC-7`) |
| Evacuate | sizing at delivered net; receive leg ≤ `cap.at(delivered)` (`Retryable`) | same, on `cap.at(delivered net)` + viability | `base + floor(net × bps / 10 000)` (`ALC-20`) |

**OPS-42** `Join`: parse the invite (`Permanent`); join (`FMI-8`; an error → `Retryable`); the
join is **new** iff `!membership_preexisting && (the protocol reported a new join || the
registry row's invite equals the intent's)`, the registry row read only when neither of the
first two terms holds, and a join that is not new records the ledger note `STO-35` names
("already joined (concurrent/prior); no-op re-open"), which is what keeps a re-open out of the
auto-join counts (`ALC-29`); if the actor is `User`, mark the candidate `UserApproved` — **but only
from a state that is neither `AutoJoined` nor already `UserApproved`** (`DOM-12`), so a user
`join` of an already-auto-joined federation leaves the row
agent-owned and only the audited `approve` verb (`API-23`) releases its probe gate and unproven
slot (`ALC-37`, `ALC-29`); seed recovery promotes any candidate state (`STO-26`) but refuses a
federation that still has a registry row (`FMI-31`), which auto-join always writes, so it is not a
release path either; record the join's outcome in the ledger (a stale attempt → `Retryable`);
return `Done`. `Recover`: parse, recover (`FMI-31`), **any** error → `Permanent`, `Done`. Neither
has a fee cap or a reservation, and neither is timed out (`OPS-15`).

## Evacuation supersession

**OPS-31** The **marker** is `Intent.evacuation_refusal` (`STO-9`). It is written only by the
retryable reset that carries `StructuralEvacuationRefusal` evidence (`OPS-43`), and cleared by
the `Pending → Executing` claim, any ordinary retryable reset, the deliberate clear below, or the
exchange (the retired parent keeps it). The deliberate clear is one transaction against the
planner's parent: the stored row MUST equal the planner's copy byte-for-byte, be `Pending`,
agent, `Evacuate`, marked, with no `operation_id` or `invoice`, no supersession sidecar
(`STO-25`), no other live agent evacuation for the source, and any move record pristine (else
`Permanent`); it blanks the marker only — no driver, no wake — and is invoked by the tick commit
for a no-child disposition and by the planner's reconcile pass for a parked handoff (`OPS-35`,
`ALC-38`). `show` projects `evacuation_refusal_active` as `true` for an exact readable `Pending`
agent `Evacuate` with a marker, `false` for an exact readable intent without one, and omits it
when no intent is readable; `history` omits it (`API-11`, `API-33`).

**OPS-30** The exchange is one transaction: a full-row compare-and-swap on the parent; the
evidence validated; the parent `Pending`, agent, same source, no artifacts; the child's
occurrence strictly greater and its key distinct; no other live agent evacuation for the source;
the child's namespace empty; any parent move record pristine (phase `Created`, trusted, no
invoice, operation ids, preimage or outcome) — else `Permanent`. Then: the parent → `Failed` with
"superseded after measured structural evacuation refusal; successor <key>" and its ledger row
advanced; the child intent `Pending` at attempt 0 with its own `Started` row; the two sidecars
(`STO-25`). A replay with a coherent sidecar pair validates and returns success without writing.
`DEF-7` is why this exists.

**OPS-32** The tick commit's replacement branch (`ALC-32`) additionally requires the child's
`fee_cap_components` to equal the **current** policy cap and `cap.at(amount)` to equal its
`fee_cap` (else `policy_superseded`); fresh balances for both ends; the re-read parent equal to
the planned one byte-for-byte (else no child, marker retained); qualification re-checked
(`ALC-23`); balance facts unchanged; fresh blockers excluding the parent; the allocator
projection excluding the parent; the arithmetic of `OPS-7` on the child. On a `Permanent` error
the marker is retained as definitely uncommitted; on any other error the wallet re-reads the
sidecar and the parent to classify the exchange committed, uncommitted or ambiguous, and an
ambiguous outcome MUST poison goal admissions and balance facts until restart. Success advances
both endpoints' generations, resolves waiters on the old key, and drives the child.

**OPS-33** The standalone path requires `--occurrence` strictly greater than the parent's agent
occurrence and refuses the largest representable value up front (`DOM-16`); every
replacement-path error retains the marker; a confirmed-uncommitted outcome bails; a committed one
applies just the child with reservations excluding the parent. Standalone `status` is dry: a
stale occurrence warns and returns the diagnostics with no would-run decisions (`ALC-44`).

## Reconcile

**OPS-35** A reconcile pass — run by a resident host at the start of every cycle (`ALC-38`), by
`POST /v1/reconcile` and the `reconcile` verb (`API-24`; both in preserve mode), and by the
ownership recovery of `OPS-14` — MUST, in order: scan the `Pending | Executing` intents (a scan fault fails the pass,
and the scheduler treats eligibility as unknown); compute goal blockers before any filtering
(`ALC-31`); preempt any in-flight probe whose source federation has a pending evacuation,
recording the probe `Failed` "probe preempted by evacuation; no attempt recorded"; then, per
intent, apply the pass's **marker mode** to a planner-owned marker — a `Pending` agent `Evacuate`
whose occurrence is below the largest representable value and whose marker the current policy
cap qualifies to replace (`ALC-23`): **preserve** (the cycle's opening pass, and ownership
recovery) skips it; **capture** (the planner's own pass, `ALC-38` step 5) skips it and parks it
for the planner, but only while it is `Pending` with no `operation_id` or `invoice` and goal
admissions are not poisoned (`OPS-32`); **re-drive without planner** (a recovery-only cycle)
drives it, still skipping while poisoned, and suppresses the wake of its next renewed marker once
— then fail an orphaned probe leg whose session is gone (`Failed` "probe session is no longer
active"), skip registry-owned keys, normalize `Executing → Pending` (a plain status write, the
marker untouched), and drive (`OPS-14`); then scan the `Awaiting` intents and spawn an awaiter for
every unowned key. A pass performs at most **one** drive step (`OPS-43`) per intent; a step that
ends `Retryable` or with a structural refusal leaves the intent `Pending` for a later pass.
Before stepping, a pass MAY backfill the move record of every pending and awaiting move-shaped
intent from the operation log (`OPS-20`; a failure is logged and that intent skipped). What
`POST /v1/reconcile` runs after the pass is `API-24`.

**OPS-36** Reconcile never re-performs: `Awaiting` intents (re-attached only), `Done`, `Failed`,
keys a live driver owns, and planner-owned markers under the preserve or capture modes.

**OPS-37** Repair. Ledger repair (`STO-24`) — its scan and its ledger-row repair — runs off the
admission point, while the one reservation-releasing write it makes, the raw terminal repair of
a `Pay | Receive` intent, MUST be serialized with admission (`OPS-13`) and fenced on the row's
seq, operation id, role and status and on the intent's attempt (`ADR-0031`: "Ledger repair is
the deliberate off-actor exception"). The move-record backfill from the operation log (`OPS-20`)
is the other repair path. Neither admits a fresh intent.

## Errors

**OPS-38** What an admission or await outcome means to a caller (`API-6` owns the status codes;
`API-7` the rule that a caller branches on the key's presence):

| Outcome | Meaning | HTTP |
|---|---|---|
| refused, with a reason (`OPS-39`) | admission or commit refused; nothing journaled for a fresh key | 422 / 409 |
| storage fault | a durable read or write failed or an internal invariant broke; a fresh agent admission may or may not have committed | 500 |
| not found | an await on an unknown key | 404 |
| destination unavailable | a fresh admission, or a retry (`OPS-5`), whose destination is joined but not open; nothing journaled | 503 |
| timeout | the await deadline elapsed; the operation is still live | 504 |
| shutting down | the wallet is draining or its engine is gone | 503 |

**OPS-39** The refusal **reason** is the contract; the message is informative. A refusal carries
exactly one of the nine reasons below (`API-5` gives their wire spelling, `API-6` their status;
the tenth reason, `amount_required`, is minted by the HTTP handler alone, `API-18`). The
mapping from refusing condition to reason below is the requirement: each condition MUST yield
its reason whatever the message text says, and a change to any message MUST NOT change the
reason a condition yields; how an implementation derives the reason is its own:

| Reason | Assigned when |
|---|---|
| `insufficient_after_reservations` | the source check of `OPS-7` fails at admission or retry |
| `over_cap` | the destination check of `OPS-7` fails at admission or retry |
| `sizing_conflict {field: "request sizing"}` | a live-key attach changes a sizing field (`OPS-8`) |
| `fed_held_by_probe` | item 6 of `OPS-6` |
| `storage_error` | a journal fault on the admission path — the key read, the goal-blocker scan, a probe-record read — surfaced as a refusal (`API-6`: 409) rather than as the storage fault of `OPS-38` |
| `policy_superseded` | a batch planned under a stale policy generation (`OPS-11`, `ALC-41`), or a replacement whose child cap is not the current policy's (`OPS-32`) |
| `policy_invalid` | a stored or submitted policy that fails validation (`DOM-15`, `API-20`) |
| `budget_exhausted` | a probe the probe budget refuses (`ALC-26`) |
| `conflict` | every other refusal: a goal conflict (`ALC-30`), the driver cap, a probe/user key collision (`DOM-21`), the anchor refusals of `OPS-8` and `OPS-10`, an agent decision meeting a terminal key (`ALC-53`), a replacement occurrence or exchange conflict (`OPS-30`, `OPS-33`), an admission racing a membership change in progress (`OPS-41`), a batch refused whole for any reason but the policy generation (`OPS-11`), a candidate approval race (`API-23`) |

**OPS-40** The wallet MUST NOT attach a cause to a money state it did not observe in what it
records or emits: the ledger `error` (`STO-35`) and the operation views (`API-12`) state what the
state **is** — `Stranded` is "a settled send with a preimage and an op-terminal non-claim on the
receive" (`OPS-27`) — and never why it arose or what would recover it (`DEF-20`). The operator's
account of causes and responses is the code repository's runbook (`HST-32`).
