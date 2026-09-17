# 09 — Known defects

Every entry is a defect the wallet has had, written as a prohibition so that its fix cannot be
undone by a later change that looks like cleanup. Each states what a compliant wallet MUST NOT
do, cites the requirement that owns the positive rule, and says in a sentence or two what
failure the prohibition prevents. How one implementation came to each defect — the issue that
recorded it, the change that closed it, the tests involved — is the code repository's record,
not this set's.

Entries are grouped by theme; each is cited from the requirement it constrains.

## Money arithmetic

### DEF-1 — A funding move MUST NOT be bounded by a flat fee cap

The fee cap of an allocator-emitted funding move MUST be proportional to the amount moved
(`ALC-7`), and sizing MUST reserve the amount plus its proportional cap from the source, never a
flat cap (`ALC-8`). Under a flat cap alone, a move of a few sats could pass every check while
paying many times its own value in fees; and reserving the whole flat cap before sizing drove
the fundable amount to zero whenever the cap was large next to the surplus, refusing moves that
should have been made.

### DEF-2 — A refusal MUST NOT be recorded without the figures that produced it

Every refusal row MUST carry the amounts and bounds the allocator decided on (`STO-15`), and a
field added to that record later MUST decode from a row written before it existed (`STO-30`).
A refusal that recorded only the federation and a reason code could not be reproduced
afterwards, so fee policy was being designed on top of a failure nobody could explain.

### DEF-3 — An evacuation MUST NOT be bounded by the flat cap, nor sized against a cap it does not enforce

The evacuation cap is `ALC-20`'s, computed from the delivered net and never from the sized ask
(`ALC-21`), persisted with the receive so a replay cannot resurrect the planned cap (`OPS-25`),
and reached by the executor's sizing search (`OPS-44`). Route economics MUST NOT gate an
evacuation (`ALC-18`). Under the flat cap, at real gateway prices a full drain
was over the cap many times over: either the balance trickled out in dozens of chunks across as
many ticks, or no amount fit at all and the wallet retried forever — a silent livelock in the
one path whose purpose is to get money out of a dying federation.

### DEF-4 — A ledger row MUST NOT report a cap or an amount the wallet did not enforce

The ledger row's cap and amount MUST be the enforced cap and the executed amount, refreshed
together (`STO-17`). A row that kept the planned figures for its whole life let a fee audit
validate fees the enforced cap would have refused: an evacuation planned large and clamped small
recorded a cap it never applied.

### DEF-5 — Automated gateway selection MUST NOT stop at the first candidate that validates

Automated selection MUST choose the cheapest validated candidate (`FMI-12`), which means pricing
every candidate before choosing. Stopping at the first validating gateway paid a dearer route
whenever it happened to be listed first.

## Liveness and suppression

### DEF-6 — One federation's stuck work MUST NOT suppress decisions for another

Suppression MUST be scoped to the allocator goal that conflicts with live work, never to a
wallet-wide count (`ALC-30`): a stuck intent on federation A MUST NOT suppress an independent
decision for federation B. When any retryable pending work halted the whole tick, one
federation's stuck move stopped the allocator wallet-wide, including the tick that would have
decided an evacuation from a different, dying federation. The caution was sound — a tick against
unknown pending state risks re-issuing the same work under a fresh occurrence — and the blast
radius was the defect.

### DEF-7 — A structural evacuation refusal MUST NOT be beyond every operator action

A marked pre-artifact agent evacuation MUST be replaceable by a linked child under a qualifying
cap increase (`DOM-20`; `ALC-23` says what qualifies, `OPS-30` is the transaction). Before this,
a refusal whose fixed fee component exceeded the admitted cap base retried forever against the
cap it was admitted with; the operator raised the only knob the wallet exposed and nothing
changed. Terminalizing the retryable intent would not have fixed it: that strands the balance
evacuation exists to sweep.

### DEF-8 — The settlement-stall watchdog MUST NOT count an unexpired invoice

A receive counts toward a stall only once its invoice has been expired for longer than the
deadline (`ALC-40`). Counting every unpaid, unexpired invoice put a low-traffic wallet into a
restart loop until an invoice paid or expired — money-safe, but it polluted the one signal that
means "investigate".

### DEF-9 — A path that skips planning MUST NOT be silent

Every path that skips planning MUST set `automation_blocked` with a reason and a detail
(`ALC-45`); liveness is not readiness. A fail-closed fence that skipped planning while the
scheduler reported itself alive was correct to refuse and invisible while it did.

## Persistence and compatibility

### DEF-10 — A field added to a persisted type MUST NOT make older rows undecodable

A field added to a type on `STO-29`'s list — an already-shipped variant included — MUST decode
when absent, to the value `STO-30` names, and never to an unstated zero for a numeric; `CNF-18`
is the scenario that demonstrates it. A field added without a default left every row written
before it permanently undecodable: absent from history, re-warned on every read, and — under a
fence that treats an unreadable row as repair-only (`DEF-12`) — enough to stop automation over
rows a default would have read.

### DEF-11 — A type written to a live store MUST NOT reject a row carrying an unknown key

No type on `STO-29`'s list may refuse to decode a row for an unknown key (`STO-31`); strictness
belongs at the request surface, checked against the type's own field set (`API-20`). A stored
type that doubled as a validated request input rejected unknown keys, so the first row a newer
build wrote was unreadable to the previous build, and a rollback after that write could not
start.

### DEF-12 — An unreadable ledger row MUST NOT fence automation

An unreadable ledger row MUST NOT fence automation (`STO-22`). The agent-occurrence floor is
held by raising the checkpoint in the same transaction as any agent ledger append (`STO-21`) and
by seeding an absent checkpoint from the ledger (`STO-23`), never by refusing to run until every
row decodes. A migration that treated any unreadable row as repair-only would have ended ticks,
rebalancing and evacuation over a few audit rows (`DEF-10`) until an operator restored their
exact bytes — to repair a stale-checkpoint condition that did not exist.

### DEF-13 — A persisted type MUST NOT be exempt from the compatibility rules

The types `STO-30` and `STO-31` bind are the ones on `STO-29`'s list, transitively through every
type embedded in one; a type is on that list because the wallet writes it, not because someone
remembered to add it. A hand-maintained list that named the policy, the actions and the move
records but not the ledger rows is how `DEF-10` shipped.

### DEF-14 — A compare-and-swap write MUST NOT surface a write conflict to its caller

A write whose guard is read inside its own transaction MUST be retried until it commits or its
guard fails (`STO-8`); a plain write reports a conflict as `Retryable` and leaves the retry to
its caller (`STO-7`). The recovery commit once lacked the retry every other guarded write had,
so a transient conflict at the one moment a recovery becomes durable would have failed it.

## Federation clients and recovery

### DEF-15 — Recovery MUST NOT be a side effect of a join

Recovery is an explicit verb with complete-or-fail semantics (`FMI-30`), never automatic and
never a side effect of a join (`FMI-33`). When no recovery path existed, "wipe the journal and
rejoin" allocated a fresh empty partition, orphaned the funded one and reported a zero balance.

### DEF-16 — A single-guardian federation's one decryption share MUST NOT stop the client

In a single-guardian federation, aggregating the one threshold-decryption share MUST yield the
preimage and MUST NOT panic or stop the client's state machines (`FMI-39`); `CNF-32` is the
scenario that demonstrates it. A client whose single-share decryption panicked killed the
state-machine executor and froze every cross-federation operation on every federation the
wallet hosts.

### DEF-17 — Two client handles MUST NOT run on one partition

However opens and joins of one federation overlap, exactly one client MUST become live per
partition (`FMI-20`). An open racing a user's join could briefly run two client handles on one
database partition — the one state the client layer forbids.

### DEF-18 — The join serialization MUST NOT be held across an unbounded network fetch

The config preview under the join serialization MUST be bounded (`FMI-21`). Held across an
unbounded federation preview, one unreachable federation queued every later join and recovery
behind it.

## Recorded and reported state

### DEF-20 — The wallet MUST NOT attach a cause to a money state it did not observe

What the wallet records and emits states what a money state **is**, never why it arose or what
would recover it (`OPS-40`). A stranded move described as a gateway failure the preimage could
recover led to a proposal for recovery tooling that could have recovered nothing.
