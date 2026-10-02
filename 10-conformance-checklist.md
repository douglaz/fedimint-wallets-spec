# 10 — Conformance scenarios

The scenarios a conformant implementation MUST pass. Each `CNF-n` is one scenario — *given* a
state of the wallet's environment, *when* something happens at one of its boundaries, *then*
what the environment observes — and names the requirements it demonstrates. A scenario carries
no result: which scenarios an implementation has passed, at which revision, by which harness and
with which figures observed, are facts about that implementation and live beside it, in the code
repository's conformance results (`README.md`, *How compliance is measured*). A scenario the
implementation under review has not passed is a non-conformance of that implementation, recorded
in its `docs/open-findings.md`, never a reason to soften the scenario.

**A conformant implementation MUST pass every scenario in this chapter.**

A scenario is stated against the wallet's **environment** — federations, their guardians and
gateways, a Lightning payer, a store, a crash at a named point — never against a harness. Any
harness that produces the *given* state is admissible, and how the code repository realises each
scenario is its own business. Where a scenario needs a crash or a forced signal, it says what the
environment does; how an implementation injects it is `SEC-18`'s.

**The environment.** Unless a scenario says otherwise: two federations **A** and **B**, each
passing the structural floor of `ALC-14`, each with the `mint`, `wallet` and `lnv2` modules
(`FMI-3`), each with an lnv2 gateway on its vetted list (`FMI-10`), and one gateway **G** on
both lists that serves both (`FMI-13`); a Lightning node outside the wallet that G can pay and
be paid through; a wallet joined to A and B with spendable balance on A; a policy that pins A
as spending and B as standby, with `auto_join` off. Balances are read at the wallet's balance
boundary (`FMI-27`, `API-9`) before and after; "rises by the amount" and "falls by amount plus
fees" are exact, and every fee paid is within the cap the requirement names (`OPS-29`).

## Membership and recovery

**CNF-8** *Given* an invite for a federation the wallet has not joined, *when* the wallet joins
it, *then* the federation is registered and open, `list-feds` reports it, and its balance reads
zero with every joined federation open. *When* the same invite is joined again, *then* the
wallet reports it joined with no network call and no second registry row. Demonstrates `FMI-8`,
`API-22`, `API-9`.

**CNF-23** *Given* a wallet with spendable ecash on A, its twelve-word seed held outside it
(`SEC-24`) and A's invite, *when* the whole data directory is lost, a fresh wallet is
initialised, the seed restored through `restore-mnemonic` before the wallet first serves, and
A recovered through the recovery verb, *then* the recovered federation holds **exactly** the
ecash the lost wallet held on A — zero slack — is registered, `UserApproved`, and spendable: a
pay from it succeeds. *Given* that fresh wallet before its restore, *when* `restore-mnemonic` is
given the words as an argument rather than on stdin, eleven words, or twelve words that fail
the BIP-39 checksum, *then* each is refused and the seed slot stays empty; *given* the restored
wallet, *when* it is given twelve valid words again, *then* it is refused and the slot still
holds the first seed (`SEC-11`). *Given* the same wallet, *when* only the journal is lost — the client
store survives with its partitions, the registry does not — and A is recovered again, *then* the
recovery lands in a fresh partition, the orphaned partition is never opened and never reused, and
the recovered balance is again exact. Demonstrates `FMI-30`, `FMI-31`, `FMI-32`, `FMI-35`,
`SEC-11`, `SEC-24`, `STO-28`, `HST-5`.

**CNF-41** *Given* an invite for a federation whose module recovery cannot complete — a module
that reports its recovery failed, or a federation that becomes unreachable after the config
preview so that no module makes progress for longer than `FMI-30`'s bound — *when* the wallet recovers it,
*then* the recovery terminalizes `Failed` rather than parking: no registry row is written, no
client for that federation becomes live, the partition it used is left inert and is never
opened, and a later recovery of the same invite — once the federation is reachable — allocates
the next partition and completes with the seed's ecash. Demonstrates `FMI-30`, `FMI-31`,
`FMI-35`, `OPS-42`.

**CNF-32** *Given* a federation with exactly one guardian, joined by the user, *when* the wallet
receives over lnv2 on it — an incoming contract whose claim needs that guardian's single
decryption share — and then pays an external invoice from it, *then* the receive is claimed and
credited and the pay settles; the single share is enough for every lnv2 operation. Demonstrates
`FMI-39`, `DEF-16`.

## Money paths on one federation

**CNF-9** *Given* the environment, *when* the wallet issues a receive of an amount on A and
the invoice is paid from the Lightning node, *then* the receive is claimed, A rises by the amount
minus the gateway and federation receive fees, and the invoice carried the expiry and the
description `FMI-16` requires. *When* the wallet pays an invoice from the Lightning node out of A,
and a second pay of the same invoice is submitted while the first is still live, *then* the
second attaches to the first as already in flight and funds nothing, the send settles once, A
falls once by the invoice amount plus a fee within the cap, and a third submit after settlement
is answered with the existing outcome. Demonstrates `FMI-16`, `FMI-17`, `OPS-8`, `OPS-17`,
`OPS-18`, `OPS-29`.

**CNF-10** *Given* the environment, *when* the wallet issues a direct inflow of an amount into
A and the invoice is paid, *then* A is credited **never more** than the amount and at most
1 000 msat less — the gross-up's bounded shortfall plus the federation's mint output fee on the
claim — and the invoice amount is what the payer paid. Demonstrates `FMI-15`, `FMI-18`,
`OPS-22`, `OPS-23`.

## Moves

**CNF-11** *Given* the environment, *when* the wallet moves an amount from A to B through G,
*then* B rises by exactly the amount, A falls by the amount plus the receive and send fees, the
total fee is within the move's cap, and both legs' operation ids are on the move's ledger row.
Demonstrates `OPS-19`, `OPS-22`, `OPS-24`, `OPS-26`, `OPS-27`, `OPS-29`, `STO-33`.

**CNF-12** *Given* a fresh move from A to B for each of the four killpoints of `OPS-28` —
before the move record, after the receive commit, before the send, after the send commit —
*when* the wallet suffers an uncatchable abort at that move's killpoint and is restarted and
reconciled, *then* each move completes exactly once: B rises exactly once by the amount, A falls exactly once, no second
payable invoice was ever minted, and the route recorded with the committed leg is the one the
send went through. Demonstrates `OPS-28`, `OPS-20`, `OPS-24`, `OPS-25`, `FMI-17`, `OPS-35`,
`OVR-2`.

**CNF-55** *Given* the move environment, a stored `per_fed_cap` fixed except for the explicit
policy edits below, valid policies throughout, valid committed contracts and routes whose fees
fit the admitted cap, with no other live reservations except where stated, exercise the
following cases independently.
Balances and fees follow `CNF-11` for moves and `CNF-10` for direct inflows; gross-up, contract
verification and settlement remain those of `OPS-22`, `OPS-23` and `OPS-27`. Fixture balance
samples and damaged metadata below are supplied environmental faults, not additional wallet
verbs or permission to bypass admission. Their realization is the implementation's choice.

1. **Committed send, tight source.** *Given* an admitted `Move` from A to B for which A holds
   exactly `amount + fee_cap` before funding and B has ample cap room, *when* its send commits
   and debits A, and an uncatchable abort occurs at `OPS-28`'s fourth killpoint before the send
   id reaches the cached record, *then* on restart and reconcile the wallet recovers that send
   and completes the move exactly once, without terminalizing it for insufficient source
   balance. Keep the receive uncredited until after the resumed admission decision,
   so only the source's already-debited balance could cause the false refusal.
2. **Committed send, credited destination.** *Given* a separately admitted `Move` for which
   B initially holds `per_fed_cap - amount` and A is sufficiently funded that even after the
   send debit it still covers `amount + fee_cap`, *when* the same fourth-killpoint abort occurs
   and the existing receive credits B before the resumed admission decision, *then* restart
   and reconcile complete the move exactly once, without terminalizing it for destination cap
   room. The source check would still pass, so it cannot mask an erroneous destination check.

Run each of cases 1 and 2 with the `Invoiced` cache present, lacking the send operation id, and
again with that cache removed while the intent and both federation operation logs survive.
At the start of each resumed drive, supply those persisted records and balances. Every perform
that reaches pre-fund applicability must decide from reassembled evidence (`OPS-45`); any
pre-step backfill permitted by `OPS-35` may participate. No particular internal division of
reassembly work is required. In every run, the intent reaches `Done`, there is one source debit
and one destination credit across the crash, no second payable invoice and no second send,
and the committed route is retained under `OPS-20` and `STO-33`.

3. **Unfunded Move controls.** *Given* a user `Move` of 100 000 msat with a fee cap of
   10 000 msat, admitted under `per_fed_cap = 300 000` msat and aborted separately at each
   of killpoints 2 and 3, retain its invoice and receive operation id but no committed send.
   The live attempt reserves 110 000 outbound on A and 100 000 inbound on B; its own
   reservations are excluded at perform by `OPS-45`. Exercise two independent adverse states:
   (a) admit with A = 110 000 and B = 0, then supply a fresh spendable-balance sample of
   A = 105 000 on resume while B stays 0 and all reservations are unchanged. This is an
   explicit balance-boundary fault fixture, not a second wallet spend admitted through the
   existing reservation. Set the route's actual total fee to 1 000 msat, so the 101 000 msat
   debit could still be funded if the 110 000 msat pre-fund check were omitted.
   (b) admit with A = 250 000 and B = 100 000, then, before the resumed perform, lower the
   stored cap to 175 000 through the policy edit of `ALC-41`. This case explicitly changes
   the fixed-cap premise: balances and reservations stay unchanged, but B + amount = 200 000
   now exceeds 175 000 while the source still passes. No competing inflow evades reservation
   admission. *When* the wallet resumes and reconciles, *then* (a) terminalizes `Failed` for
   insufficient source balance under the amount-plus-cap check, and (b) terminalizes `Failed`
   for insufficient destination cap room, as `OPS-45` requires. Neither issues a send or pays
   the existing invoice; the invoice is not surfaced to an external payer. Its presence alone
   does not exempt either check. With the original balances and cap instead, each killpoint
   resumes through `OPS-28` and pays that invoice exactly once.
4. **Paid DirectInflow resume.** *Given* an admitted `DirectInflow` into B, initially at
   `per_fed_cap - amount`, with a receive artifact and its invoice already supplied to the
   external payer, *when* an uncatchable abort occurs before `Awaiting` is journaled, the payer
   pays that invoice, and its positive credit is reflected in B's balance before the resumed
   admission decision, *then* restart and reconcile recover the existing receive, without a
   cap-room refusal even though adding `amount` again would exceed the cap. Exercise this with
   the cache present and with it lost while the intent and destination operation log survive.
   The recovered contract is verified under `OPS-23`, the intent follows `OPS-27`'s `Awaiting`
   path and `OPS-16`'s settlement to `Done`, and there is one invoice and one credit across
   the crash, with the balance change required by `CNF-10`.
5. **New DirectInflow control.** *Given* B = 100 000 msat and a stored cap of 300 000 msat,
   admit a `DirectInflow` of 100 000 msat, but let no receive artifact commit yet. Then admit
   a separate user `Receive` of 50 000 msat into B, issue its invoice and leave it unpaid
   and `Awaiting`. Both admissions fit: 100 000 + 100 000 = 200 000, then
   100 000 + 100 000 + 50 000 = 250 000 ≤ 300 000. Before the DirectInflow perform,
   lower the stored cap to 225 000 through `ALC-41`, explicitly replacing the fixed-cap and
   no-other-reservations premises. Keep B's balance unchanged and the other receive live.
   *When* the DirectInflow performs, *then* `OPS-45` terminalizes it `Failed` for destination
   cap room before issuing an invoice or receive operation: excluding its own reservation,
   B + other inbound + amount = 250 000 > 225 000. Independently, `OPS-22` would allow
   B + rec.amount = 200 000 ≤ 225 000; its balance-only check cannot produce this required
   refusal. Keep fees and contracts otherwise valid so they cannot mask a missing `OPS-45`
   check. As a positive control, repeat with the cap lowered only to 250 000, leaving the
   other receive unpaid: the equality passes, one DirectInflow receive is issued and follows
   `CNF-10` when paid.

For cases 6–8, observe the intent's attempt and status, the reservation projection, the ledger
and the federation operation logs. Unknown is the `OPS-20` outcome: perform follows `OPS-4`
and `OPS-14`; an `Awaiting` DirectInflow follows `OPS-16`'s one-second retry cadence. Existing
protocol operations may progress independently during the fault; their progress is not new
funding by the wallet's resumed caller.

6. **Required operation-log read failure.** Exercise each row independently, once with the
   cache present as described and once with it lost. All listed federation operations survive;
   inject a read failure before the required log read can establish their presence or absence.

   | Caller | Surviving evidence and failing read |
   |---|---|
   | `Move` perform (`OPS-45`) | Case 1's fourth-killpoint state: `Invoiced` cache without a send id, valid receive and committed send in the logs, already-debited source; the required source log read fails. |
   | `DirectInflow` perform (`OPS-45`) | Case 4's `Executing` intent with an `Invoiced` cache and the paid receive in B's log; the required destination log read fails. |
   | `DirectInflow` awaiter (`OPS-16`) | An `Awaiting` intent with its receive id in the cache and its valid receive in B's log; the required destination log read fails. In the cache-lost variant the awaiter cannot obtain the receive id until that read succeeds. |
   | `Evacuate` perform (`OPS-19`) | A sized evacuation aborted after its send commits but before the send id is cached; the `Invoiced` cache and valid receive metadata preserve the committed amount, cap and route, and the source log holds the send; the required source log read fails. |

   *Then* each caller yields `Retryable` under `OPS-20`: the same attempt stays non-terminal,
   its reservations remain, no new invoice or send is issued, and neither the ledger nor the
   move record is terminalized because evidence could not be read. In particular the Move
   does not reach a no-send source-balance refusal, the Evacuate does not fund again, and the
   cache-lost awaiter does not fail for a missing receive id. *When* only the read failure is
   cleared, later reassembly resumes the original operations at the original attempt; let
   the existing receives be paid if still unpaid and let both legs settle where applicable.
   Each reaches `Done` with its original operation ids, one invoice and at most one source
   send in total, without a new attempt or replacement payment.
7. **Invoice finds a send behind undecodable metadata.** *Given* case 1's committed Move
   send, damage that send's metadata so `amount` has a nonnumeric value and its readable
   `move_id` is a different, unrelated key, not this attempt's correlation key. Keep the
   protocol send's invoice and id intact, and keep the receive's metadata valid for this
   attempt, including its invoice, amount, cap, quoted contract and route. Thus the malformed
   entry is warned about and skipped by metadata backfill, and does not meet `OPS-20`'s
   matching-corruption condition. *When* the Move resumes, once with the valid `Invoiced`
   cache lacking the send id and once with the cache lost, *then* reassembly finds the original
   source send from the invoice recovered from the cache or valid receive evidence. The
   original send id is recovered despite its undecodable metadata, pre-fund applicability
   follows `OPS-45`'s committed-send row, and the move settles once without a new invoice,
   send or source-balance refusal. The original route and enforced cap survive both variants.
8. **Undecodable metadata identifies this attempt.** Repeat each caller and surviving-evidence
   row of case 6 with all required reads successful. Instead, damage one of this attempt's
   log entries: retain a readable `move_id` exactly equal to its correlation key, but make
   `amount` nonnumeric so `MoveMeta` cannot decode. For Move and Evacuate, damage the send
   entry and keep the receive valid; for DirectInflow, damage the receive entry. Exercise both
   the cache-present and cache-lost variants. *Then* each reassembly is unknown under `OPS-20`,
   retains the same attempt and reservations, issues no new invoice or send and does not
   terminalize the intent, ledger or move record. In the Move variants, the invoice lookup
   can find the original send; that does not override matching-corruption uncertainty. In
   the cache-lost DirectInflow awaiter, failure to recover a receive id does not become
   `Permanent`. Repeating reassembly with the corruption still present preserves these
   observations; no corruption-repair facility is presumed.

   As an independent control, start a fresh Move with sufficient source funds and destination
   room, no artifacts of its own and an older undecodable entry in a scanned log whose readable
   `move_id` belongs to an unrelated operation. *Then* the wallet warns and skips that entry,
   finds no send for the fresh attempt, applies both `OPS-45` checks and completes one move.
   The old corruption does not stall it. A wholly unreadable `move_id` is not evidence of
   equality to the current attempt in either this control or the matching-corruption cases.

Demonstrates `OPS-7`, `OPS-16`, `OPS-19`, `OPS-20`, `OPS-22`, `OPS-23`, `OPS-24`, `OPS-27`,
`OPS-28`, `OPS-35`, `OPS-45`, `STO-33`, `FMI-17`, `OVR-2`.

**CNF-53** *Given* the environment except that B's vetted list is **empty** throughout and an
operator gateway **X** — on A's list, on no list of B's — answers `routing_info` for both A
and B, quotes viable fees and performs for both, *when* an automated move into B
is admitted with no override, *then* it stays `Pending`, retryable, with nothing minted; *when*
the operator awaits that move with the break-glass armed for its key naming X, *then* exactly
that move completes through X; *when* a move, a receive into B and a pay from B are each issued
with the override for their own key, *then* each routes through X; *when* the override is passed
to `tick`, `probe`, `status` or `reconcile`, *then* it is a usage error; and *when* a second
move into B is created without the override, *then* it is still `Pending` at the end.
Demonstrates `FMI-10`, `FMI-12`, `FMI-14`, `HST-10`, `ADR-0030`.

## Evacuation

**CNF-14** *Given* the environment with A holding a balance and B eligible as the destination
with cap room above that balance, *when* A begins to report a
corroborated shutdown — the `/status` signal corroborated as `FMI-26` requires, or a config
expiry within `ALC-19`'s trigger lead — and a tick runs, *then* the tick emits an
`Evacuate` from A into B keyed by the occurrence, B rises by what the evacuation delivered, and A
is drained — what remains on it is below `OPS-44`'s sizing floor, so a further tick's
`Evacuate` of A sizes nothing — without an operator naming the move. Demonstrates `FMI-26`,
`ALC-17`, `ALC-18`, `ALC-19`, `OPS-21`, `OPS-44`.

**CNF-36** *Given* the dying federation of `CNF-14` and a policy whose evacuation cap
components `(base, bps)` and whose flat `max_fee` disagree — `ALC-20`'s cap differs from
`max_fee` at every amount in play — *when* a tick plans, *then* the `Evacuate` it emits
carries `fee_cap` equal to `ALC-20`'s cap at the planned amount, never `max_fee` — the cap
readable on the intent and on its ledger row, the components on the intent; and the sizing that
follows enforces that cap at the delivered net (`CNF-43`), not `max_fee`. The funding move's
cap is `CNF-13`'s. Demonstrates `ALC-2`, `ALC-17`, `ALC-20`, `ALC-21`, `ALC-22`, `DEF-3`.

**CNF-43** *Given* a dying federation with a balance to evacuate, a route whose receive-side fee
makes the delivered net smaller than the sized ask, a policy whose evacuation cap `(base, bps)`
has `bps > 0` and whose flat `max_fee` exceeds every fee below, and a route fee at the sized
amount that lies strictly between `ALC-20`'s cap at the delivered net and the same cap at the
sized ask, *when* the evacuation is planned, sized and driven, *then* no fee above the cap at
the delivered net is paid, at the pre-mint gate or at the post-receive recompute — the leg is
refused or resized. *Given* a receive committed under that cap, *when* the wallet restarts with its cache
lost and replays the attempt, *then* the cap it enforces is the one persisted with the receive,
not a recomputed planning cap. Demonstrates `ALC-20`, `ALC-21`, `OPS-22`, `OPS-25`, `OVR-7`.

**CNF-24** *Given* a dying federation A and a policy whose evacuation cap is base-only (`bps =
0`) with a base below the summed bases of G's fees at both ends, *when* a tick plans and drives
the evacuation, *then* the sizing search refuses **structurally**: the `Evacuate` intent stays
`Pending` holding a marker with two freshly quoted samples, no invoice or operation id exists,
and both balances are unchanged. *When* the operator raises the cap component-wise so that it
qualifies, *then* the **scheduler** reacts without a manual tick: exactly one child evacuation
is created with reciprocal supersession links to the parent, the parent is `Failed` as
superseded with its marker cleared, and the child moves real value whose fee fits the new cap and
would not have fit the old. *When* the wallet is restarted and reconciled, *then* nothing
changes: no second child, no re-drive of the parent, balances as they were. Demonstrates
`ALC-23`, `ALC-24`, `ALC-41`, `OPS-30`, `OPS-31`, `OPS-32`, `OPS-35`, `STO-25`, `DEF-7`.

**CNF-42** *Given* the state `CNF-24` reaches once the child's receive is committed, *when* the
wallet suffers an uncatchable abort at the after-receive-commit killpoint of the **child** and is
restarted and reconciled, *then* the child proceeds to its pay step with the invoice it minted:
one send, B rises exactly once, A falls exactly once, the parent stays `Failed` as superseded,
and both sidecars are intact. Demonstrates `OPS-28`, `OPS-30`, `STO-25`, `OPS-35`.

**CNF-34** *Given* a marked `Pending` agent evacuation whose marker the current cap qualifies to
replace, *when* a claim of the parent — its `Pending → Executing` transition by a drive — commits
after the planner read the parent and before the exchange's compare-and-swap, *then* the
exchange writes nothing: no child intent, no sidecar, the parent is the only live intent for its
source, and the wallet holds exactly one executable evacuation for it. Demonstrates `OPS-30`,
`OPS-32`, `OPS-13`, `OPS-31`.

## The automated cycle

**CNF-13** *Given* the environment with B below its standby target by more than `ALC-10`'s
funding floor for the route, and A above its spending target by more than that shortfall plus
`move_fee_cap(shortfall, bps)`, *when* one tick runs, *then* it probes, scores, snapshots,
decides and commits a funding `Move` from A into B sized to the shortfall and not over, chosen
by the allocator and named by no one, carrying `ALC-7`'s proportional cap and not the flat
`max_fee` — the two differing at that amount — with the `Tick` row opened before sensing
and terminalized after, as `ALC-34` requires, and B rises by the move's amount. Demonstrates `ALC-4`,
`ALC-5`, `ALC-7`, `ALC-32`, `ALC-34`, `ALC-53`, `OPS-11`, `DEF-1`.

**CNF-20** *Given* the environment with `auto_join` on and a discovery source announcing a
third federation **C** that passes `ALC-14`'s floor under its announced id and lists G, which
serves it, on its vetted list, C's standby shortfall clearing `ALC-10`'s funding floor for the
route, and A holding, after the probes' fees, a surplus above its
spending target that covers that shortfall plus its cap, *when* the resident scheduler runs for as long as the policy's probe
span requires and the operator's only action is to pin C as standby in place of B once C is
joined, *then*, in order: C is auto-joined and probe-gated, and the pin does not bypass the
gate; scheduled probes run on C until its verdict is `Passed`; an
autonomous funding move fills C toward its standby target and **never over** it; and *when* C
then reports a corroborated shutdown and the wallet is restarted, *then* an autonomous
evacuation drains C back with no operator action. Demonstrates `ALC-28`, `ALC-29`, `ALC-37`,
`ALC-38`, `ALC-52`, `ALC-5`, `ALC-17`, `FMI-26`, `OVR-5`.

**CNF-16** *Given* a candidate federation the agent has joined, probe-gated, *when* the active
probe runs, *then* leg in mints `probe_amount` on the candidate paid from the spending
federation, leg out redeems the delta back, the combined loss across both federations is fees
only, every leg and the umbrella row are in `history`, and the attempt is recorded with the
session's start time; *when* enough probes pass over the policy's minimum span, *then* the
verdict is `Passed`; and *given* a candidate that is not joined, *when* a probe is attempted,
*then* it is a no-attempt that records nothing and never demotes the verdict. Demonstrates
`FMI-34`, `ALC-25`, `ALC-27`, `STO-26`.

**CNF-17** *Given* a discovery source announcing a federation the wallet has not joined —
one whose authenticated config carries the announced id and passes `ALC-14`'s structural
floor, and whose vetted list holds G, which serves it — and `auto_join` on, *when* a discovery pass runs, *then* the federation is discovered, previewed with
the Sybil check, auto-joined and marked `AutoJoined`, with the discover, auto-join and agent join
rows in `history`; *when* the operator pins it as standby in place of B and a tick runs, *then* it is refused
funding with a `NotProbed` refusal row: a pin does not bypass the gate — the shortfall clearing
`ALC-10`'s funding floor for the route, and A holding, after the probes' fees, a surplus above its
spending target that covers the shortfall plus its cap; *when*
`probe_min_successes` probes have passed over `probe_min_span_secs` and a later tick runs,
*then* that tick funds it. Demonstrates
`ALC-28`, `ALC-29`, `ALC-37`, `FMI-28`, `SEC-16`, `OVR-5`.

**CNF-38** *Given* a wallet whose stored occurrence is one below the largest representable
value, *when* the scheduler runs, *then* at most one cycle plans at the maximum, and every cycle
after it publishes `automation_blocked {cycle_failed}` and admits no agent work; *when* the
daemon is stopped and a standalone tick is invoked at the maximum, *then* it is refused for
the occurrence, before planning, and not for lock contention; and *when* the daemon is
restarted and `/v1/status` is read, *then* it answers 503. Demonstrates `ALC-33`, `ALC-36`, `ALC-45`,
`DOM-16`, `API-15`.

**CNF-35** *Given* a registered federation whose client partition fails to open at start,
*when* the cycle runs, *then* it returns blocked
`partial_federation_view` naming that federation, writes no tick, probe or watch row,
`/v1/health` reports `automation_ready` `false` with that reason, `/v1/status` answers 503, and
the wallet retries the open every cycle until it succeeds, after which the block clears.
Demonstrates `ALC-46`, `ALC-45`, `ALC-38`, `FMI-9`, `API-15`, `API-16`.

**CNF-51** *Given* a store whose federation registry holds a malformed value under a
well-formed key, in the partition the wallet reads, *when* the cycle runs, *then* it returns
blocked `corrupt_federation_registry` with the skipped-row count as its detail, writes no tick,
probe or watch row, and `/v1/health` reports it; *when* standalone `tick` or `status` is
invoked, *then* it refuses before opening; and *when* a user verb naming an intact federation
is invoked, *then* it still works. Demonstrates `ALC-46`, `ALC-45`, `ALC-38`, `HST-11`,
`STO-14`, `DEF-12`.

**CNF-50** *Given* a cycle whose planner reconcile pass cannot authorize planning — a membership
change or a raw terminal write in progress at that instant, or goal admissions poisoned — *when*
the cycle runs, *then* it runs as a non-money cycle: no tick row, no route pricing, no commit,
no fresh probe, while ledger repair, discovery and the deadlines still run, and before it sleeps
it publishes `automation_blocked {cycle_failed}` with a detail naming the reconcile, so
`/v1/health` reads not ready. Demonstrates `ALC-47`, `ALC-45`, `ALC-48`, `DEF-9`.

**CNF-37** *Given* a route whose two gateway schedules and two federation fees are such that a
proportional cap admits only moves above some break-even, *when* the wallet prices the pair and
`/v1/status` reports the deferred goal's `floor_msat`, *then* that floor is never below the true break-even: at the reported floor the modelled fee
of the route is within `move_fee_cap(floor, bps)` — a floor above the first viable amount is
conservative and conformant, one below it is not — and a funding shortfall below the reported
floor is deferred with that floor and its `floor_source`, not moved. Demonstrates `ALC-12`, `ALC-10`, `ALC-13`, `API-15`.

## Concurrency and responsiveness

**CNF-21** *Given* a gateway that accepts a connection and never answers, registered on the
candidate's vetted list, and a scheduled probe held in flight by it, *when* a pay is posted,
*then* its first outbound request reaches a federation or gateway while the probe's connection
is still open and unanswered — observed at those endpoints, not inside the wallet; *when* two pays are posted at once, *then* neither
waits for the other; *when* the external driver cap's worth of pays are held by hanging
gateways, *then* the cap-plus-one submit is refused `conflict` at once; *when* the daemon is
sent `SIGTERM` in that state, *then* it exits 0 promptly; and the move a stalled gateway holds
is not `Stranded` by the stall alone. Demonstrates `OVR-3`, `OPS-13`, `OPS-6`, `HST-7`, `FMI-23`,
`FMI-42`.

**CNF-22** *Given* the environment with the resident scheduler active, *when* the wallet is
driven for 24 hours by periodic receives, pays and moves, *then* every operation key appears
exactly once in `history`, no user operation fails, `/v1/health` reports `scheduler_alive`
`true` throughout, and a final `SIGTERM` exits 0. Demonstrates `STO-20`, `STO-16`, `OPS-14`,
`ALC-38`, `ALC-42`, `API-16`, `HST-7`, `OVR-4`.

## Durability and the ledger

**CNF-18** *Given*, for each of the eighteen fields `STO-30` lists — the four `MoveMeta`
fields in the operation log included — a stored row of the enclosing type with that field
alone stripped from its serialized form, never several at once, *when* the wallet reads each
row, *then* the field decodes to the value `STO-30` names for it,
and the wallet serves on that store. Demonstrates `STO-30`, `DEF-10`, `OVR-14`.

**CNF-33** *Given* a store in which a row of each type on `STO-29`'s list — the `Policy` row
and its nested values included — carries a key this wallet does not know, as a later build
would write it, *when* the wallet starts and reads them, *then* it starts and serves with every
field it knows at its stored value; *when* `PUT /v1/policy` is sent a body
with an unknown key, *then* it is refused 422 naming the unknown field. Demonstrates `STO-31`,
`STO-29`, `STO-13`, `API-20`, `DEF-11`.

**CNF-15** *Given* the environment, *when* one session performs two joins, a direct inflow, a
raw receive, a move, a pay whose fee cap is set below the route's fee, and a tick under a
policy whose per-federation cap induces `OverCap` refusals, *then* the whole session is
reconstructible from `history` and `show` alone: each row's kind, actor, reason, fees, error and
— for the move — both legs' operation ids, with timestamps non-decreasing by `seq`, the failed
pay's row carrying its error and each `OverCap` refusal its figures. Demonstrates `OVR-4`, `STO-15`, `STO-16`, `STO-19`,
`API-10`, `API-11`, `API-12`, `ALC-34`.

**CNF-47** *Given* a fresh copy of one store holding the plaintext seed for each of three
boundaries of the one-time re-encryption, and the key source available, *when* the wallet
starts on that copy and is killed at its boundary — before the slot commit; after the commit
while the plaintext still sits in a superseded store file; after the store is clean but
before the wallet serves — *then* on the restart that follows each: the slot holds
exactly one form of the same entropy (plaintext after the first, encrypted after the
other two), never neither; the wallet completes the migration before it serves; it
derives the same root secret as before; and once it serves, the plaintext entropy
appears in no file of the data directory. *Given* the key source unavailable, *when* the
wallet starts on the plaintext store, on the re-encrypted store or on an empty one,
*then* it refuses to start, the slot is unchanged and no seed is minted. *Given* the
re-encrypted store, *when* the build that predates `SEC-25` starts on it, *then* it fails
to start and mints nothing. *Given* the key source available, *when* the wallet first serves on
an empty store, and separately when `restore-mnemonic` stores twelve words on one, *then* each
slot is encrypted, the plaintext entropy appears in no file of the data directory, and
`walletd mnemonic` exports the same twelve words from it. Demonstrates `SEC-25`, `SEC-11`, `STO-4`.

## Frontends

**CNF-19** *Given* a running daemon and the CLI in client mode resolving it from the pointer
file, *when* the CLI issues a receive that the Lightning node pays and then a pay, each followed
by its await verb, *then* both settle, the balance moves as `CNF-9` requires, the money verbs
print `<word> <key>`, and the await verbs print `claimed` and `success`. Demonstrates `API-18`,
`API-21`, `API-25`, `API-29`, `API-38`, `OPS-5`, `HST-1`, `HST-13`.

**CNF-26** *Given* a daemon reachable by the CLI in client mode, *when* each verb of `API-26`
is invoked, *then*: the request each sends carries the fields and only the fields `API-18`–`API-24` name, and
`reclaim` posts an empty body to the route `API-42` names; two nonce-less `receive`
invocations each send a nonce of 32 lower-hex characters (`API-41`'s generated shape) and
create two distinct operations, while two nonce-less `direct-inflow` invocations of
one amount attach to one operation and re-yield its invoice, a nonce-less `move` sends
`occurrence` `0`, and an omitted `--fee-cap` or `--to`/`--fed` is absent from the request;
*given* a history whose newest rows do not match a filter and whose matching rows span more
than one page, `history --limit N` with that filter prints the N newest matching rows, and, over candidates
in mixed states, `candidates --state` prints only the selected state, newest first; every error envelope, usage error and journaled failure maps to the exit code `API-28`
gives it; the stdout of every
verb whose shape `API-29` or `API-39` fixes is that shape — `health` printing all five fields of
`API-16`, `status` rendering `deferred` and `suppressed`, `show` printing `fee_cap_msat`,
`history --json` and `show --json` carrying `fee_cap`; and `policy set` of each of the twenty-eight flags in turn PUTs every key the GET returned,
unchanged where no flag named it, refuses as a usage error a flag for a field the GET did
not return, a pin flag with its clear flag, a boolean flag without an explicit value, and a
bps flag outside its range before any PUT.

Incoming recovery and reclaim additionally demonstrate these cases. Fixtures may plant a
stored SDK final claim failure or accepted-claim issuance evidence, as `CNF-33` and `CNF-51`
plant store states. Contract disposition and issuance responses must be controlled consistently
with that evidence; no case requires an honest federation to reject a valid claim at consensus
to create the fixture. Run live-receive cases for raw `Receive` and `DirectInflow`, and the
settled-send cases for `Move` and `Evacuate`.

1. **Funded after expiry.** *Given* a live receive with a stored failed-claim observation,
   stored claim material, a funded unconsumed contract whose funding expiry has passed, and
   no accepted-claim issuance evidence, *when* reconcile runs, *then* it submits a claim
   automatically. With transient responses it remains non-terminal, keeping its inbound
   reservation and the same intent attempt; when the federation accepts and issues notes,
   it completes `Done` and credits exactly once. Its earlier `receive failed:` observation
   remains in the durable evidence. Repeat with a daemon restart before recovery, and with
   `reclaim <key>` triggering recovery instead of the next scheduled pass; both reach the
   same result without another invoice. Run ledger repair while the stored failure remains
   unresolved: it must not terminalize the receive or release its reservation.

   In the raw `Receive` fixture, leave the original SDK operation at final `Failure`
   throughout recovery and completion. While the claim is unresolved, exercise `OPS-46`
   preparation: it prepares no terminal failure, leaves the intent and ledger non-terminal,
   and retains the reservation. After recovery issues notes, preparation and finalization
   commit `Done` and ledger `Succeeded` for the original operation at the same intent
   attempt, with its definitive fee, despite that unchanged SDK `Failure`. Credit once,
   retain the earlier failure evidence, and release the reservation only on actual
   completion. Repeated `reclaim <key>` then answers `claimed`, exit 0, without another
   credit. Observe that any federation IO precedes the terminal hold and that the ledger
   and intent advance atomically.

2. **Own accepted claim, issuance pending.** *Given* the wallet's stored issuance evidence
   holds an accepted claim transaction, its notes have not issued, and the federation answers
   that the contract is consumed, *when* reconcile or reclaim runs, *then* it retrieves
   issuance from that evidence and sends no second claim. A manual call answers
   `issuance_pending`, exit 4. Repeated failed retrievals, timeouts and an SDK final issuance
   failure, each exercised separately and across restarts, leave the receive non-terminal
   with the same inbound reservation. With destination balance plus that reservation filling
   the per-federation cap, an otherwise-valid fresh inflow is refused `over_cap` (409, CLI
   exit 2), minting nothing. Ledger repair leaves the recovery non-terminal too. Once notes
   issue, the original receive completes once and manual reclaim answers `claimed`, exit 0;
   no retry or restart submitted another claim or created another invoice.
   Repeat the raw terminal-preparation fixture from case 1 with this accepted-claim
   evidence: the original SDK operation remains at final `Failure`, preparation cannot
   terminalize pending issuance, and eventual issuance permits `Done` and `Succeeded`,
   one credit, retained failure evidence and reservation release only on completion.

3. **Bounded attempts, no stalled-settlement exit.** *Given* three old live receives in claim
   retry, invoices expired beyond the settlement-stall deadline, no recent successful
   `Receive` ledger row, and repeated transient claim-submission failures, *when* scheduler
   cycles continue, *then* each is retried on the first pass after its chosen 1–60 second
   backoff, remains non-terminal and reserved, and does not make the daemon exit. Observe
   multiple attempts beyond funding expiry and across a restart. Between attempts, with no
   other drivers active and enough balance and cap room, all 32 otherwise-valid external
   drivers can be admitted; a 33rd meets the ordinary driver-cap refusal. Repeat with all
   three receives holding accepted-claim evidence and repeatedly failing issuance retrieval:
   the same slot and watchdog observations hold, and no new claim is submitted. A recovery
   attempt whose IO does not finish is abandoned at the perform timeout, emits no further IO
   from that abandoned drive, and resumes through a later eligible reconcile pass without
   changing its intent attempt or releasing its reservation.

   For both recovery classes, exercise ordinary same-key attaches with raw `Receive` and
   `DirectInflow` in `Awaiting`, and with send-required moves in `Pending` and `Executing`.
   Attach during backoff: it must neither reissue the original effect nor start an ordinary
   perform or re-await loop, shorten the backoff or defer the first due pass. The key remains
   recoverable at the same attempt, with its reservation and evidence intact; passes before
   the delay elapses do no recovery IO, and the first due reconcile pass resumes the bounded
   recovery step. Also attach while a recovery step owns the key, then let that step return
   unresolved: the requested re-drive is retained through ownership release and honored at
   the next eligible recovery opportunity, without immediate re-entry. Repeat across a
   restart. Separately, during backoff, explicit reclaim may trigger the one bounded attempt
   permitted by `FMI-41`'s manual exception. Race that manual call, an ordinary attach and a
   due reconcile pass on one key: they never overlap recovery work or duplicate a monetary
   effect; unresolved work continues under the same automatic cadence.
   As a control, three otherwise-qualifying old `Awaiting` receives that are in neither
   recovery class, with no recent success, still produce `ALC-40`'s non-zero daemon exit.

4. **Definitive evidence and send-first moves.** *Given* a funded contract consumed by another
   claimant, with the wallet's issuance evidence successfully read and showing no own
   accepted claim, *when* recovery classifies it, *then* it answers `not_claimable` and the
   live receive becomes `Failed` with `receive failed:` and the evidence retained. Separately,
   with a funded unconsumed contract whose claim federation fee equals its amount, and then
   one whose fee exceeds it, recovery answers `uneconomical`, records that reason with the
   receive failure anchor, and does not submit that claim. The same client remains running
   and can complete a different affordable receive afterwards.

   For each send-required move variant, observe the send first and persist its verifying
   preimage before receive handling. Rejected claims and own accepted claims with pending
   issuance leave the move non-terminal and its inbound reservation intact, even across
   restart; eventual issuance settles its receive leg and completes the move once. In the
   definitive `not_claimable` and `uneconomical` cases it instead becomes `Stranded`, with
   both operation ids, invoice, gateway, preimage, and the error anchor
   `send settled but receive was not credited` plus the `receive failed:` detail preserved.
   Later cycles and manual reclaim preserve those terminal records. A same-key request to
   retry the stranded move is refused `conflict` (409, CLI exit 2); none of these recovery
   paths sends again. A stored never-funded `Expired` receive retains its existing expiry
   result; a planted settled-send/expired-receive move takes the definitive-expiry branch
   of `OPS-27`, without requiring an honest payer to create that combination.

   For a probe `Move` leg, plant each recovery class separately: a settled send with a
   funded unconsumed receive in claim retry, and a settled send with this wallet's accepted
   claim whose issuance is pending. Remove the probe session, then run reconcile before
   and after the recovery backoff is due, restart, and reconcile again. Repeat with session
   loss caused by evacuation preemption; the umbrella records the preemption failure,
   while the recovering leg remains non-terminal. In each variant, due recovery continues
   at the same intent attempt, retaining the inbound reservation, preimage, operation ids
   and claim/issuance and failure evidence. No second send or invoice is issued; pending
   issuance submits no second claim. Eventual notes settle the receive leg and complete
   its move once, crediting once and releasing the reservation only then. Also restart
   after notes issue but before wallet completion: the next scan completes the leg rather
   than failing it as orphaned. The session is not recreated and no remaining probe leg or
   other new probe work is admitted by this
   exception. As a control, an orphaned probe leg with no recoverable funded receive still
   becomes `Failed` with `probe session is no longer active`.

5. **Manual surface, replay and audit.** For each eligible class in `API-42` — live receive
   or receive leg in claim retry, pending issuance, a stored receive `Failed` with
   `receive failed:`, a `Stranded` receive leg, and a receive already claimed by this wallet —
   submit the empty-body POST with the bearer token and check that `operation_key` is the
   target key. Exercise the following observations on fixtures where each is applicable;
   every response is HTTP 200, prints the wire outcome and has the indicated CLI exit:

   | Observation | Wire outcome | CLI exit |
   |---|---|---|
   | Notes issued, including already-issued notes | `claimed` | 0 |
   | Contract consumed by another claimant | `not_claimable` | 3 |
   | Claim fee at least the unconsumed contract amount | `uneconomical` | 3 |
   | Unreachable federation, claim rejection, or timeout without known accepted-claim evidence, each separately | `transient` | 4 |
   | Own accepted claim, notes not yet issued, including failed retrieval | `issuance_pending` | 4 |

   Each non-claimed CLI message carries the target key. Permit transient and pending
   observations to become claimed after the evidence changes. Repeat a successful reclaim,
   also after deliberately losing the first response and after spending the issued notes:
   it still answers `claimed`, exit 0, and leaves the balance unchanged. Each eligible
   call adds exactly one `Reclaim` audit row with its own nonce key and the target receive
   id; its status and error follow `STO-15`. Unresolved audit rows do not terminalize a live
   target; a later success does advance a live target normally. A planted already-terminal
   failed target recovered manually keeps its original terminal row and failure evidence.
   With only the best-effort audit write failing, the monetary outcome and response are
   unchanged and the row may be absent; absent that storage error, no eligible call may
   omit its audit row.

   A never-funded `Expired` receive is refused `422 refused`, message exactly
   `incoming contract was never funded`, no `refuse_reason`, CLI exit 2, with no monetary
   attempt and no reclaim row. Repeat for the planted `Stranded` move whose receive leg
   was never funded and ended `Expired`: the same refusal overrides the broad stranded-leg
   eligibility, with no attempt or audit row. An unknown key returns `404 not_found`, exit 1; other
   ineligible targets (a pay, or a receive still awaiting funding) return `422 refused`,
   exit 2. Each attempts and journals nothing. Without the bearer token, the route returns
   401 and CLI exit 5, attempting and journaling nothing.

Demonstrates `API-25`, `API-26`, `API-27`, `API-28`, `API-29`, `API-33`, `API-38`, `API-39`,
`API-40`, `API-41`, `API-42`, `API-36`, `FMI-37`, `FMI-41`, `FMI-23`, `DOM-8`, `DOM-10`,
`OPS-3`, `OPS-6`, `OPS-8`, `OPS-9`, `OPS-14`, `OPS-15`, `OPS-16`, `OPS-27`, `OPS-35`,
`OPS-36`, `OPS-40`, `OPS-43`, `OPS-46`, `STO-10`, `STO-15`, `STO-24`, `ALC-38`, `ALC-40`,
`HST-32`, `DEF-26`.

**CNF-54** *Given* a running daemon, *when* `wallet-web init` is run, *then* it takes the
password twice on the controlling terminal with echo disabled and refuses — writing nothing —
a mismatch, a password below or above `HST-26`'s bounds — each tried on its own — and a config path that already exists or
overlaps the token path; on success — a `--public-origin` given in a non-canonical but valid form among the inputs
— it writes the config `0600` with an Argon2id hash at or above `HST-26`'s minimums and the
origin in `HST-27`'s canonical form, which a browser's `Origin` header then matches; *when* the provisioned sidecar starts
with the standard proxy variables pointing at an observing endpoint, *then* it listens on
loopback only, has opened no store, reaches the daemon directly, and the proxy endpoint
receives nothing; *when*
`GET /healthz` is requested without a session, *then* it answers 200 with exactly the two keys
`HST-31` names and `daemon_reachable` `true`; *when* a page is requested without a session,
*then* it is `303` to `/login`, and a non-`GET` is `401`, neither carrying wallet data; *when*
`POST /login` is sent a wrong password, *then* it is `401` with no hint beyond that the login
failed, and after five consecutive failures every attempt is `429` for the lockout window;
*when* the right password is sent once that window has elapsed, *then* it is `303` to `/` with the `session` cookie carrying
the attributes `HST-31` fixes, and the balance page then shows what `GET /v1/balance` on the
daemon returns; *when* each daemon route other than `/v1/recover` is requested under the
sidecar's `/v1/` prefix with the session — a state-changing one also with the matching
`Origin` and the session's `X-CSRF-Token` — *then* its path, query, method, status and bodies
reach and return unchanged, with `Content-Type` and `Allow` forwarded and `Cache-Control:
no-store` added; *given* open operations on the daemon spanning more than one page of the open-history
filter and one unreadable ledger row, *when* the sidecar is restarted, a login succeeds, and its page is loaded,
*then* the page lists every open operation, having followed `next_before_seq` to `null`
under `status=open`, polls each through its operation route, and says the set is incomplete;
*when* a session goes without a non-polling request for the idle timeout,
or reaches the absolute timeout — requests marked `X-Polling: 1` extending neither — or the
sidecar restarts, *then* the session is gone and the next request is `303` or `401` as above; *when* an authenticated state-changing request other than `POST /login` arrives without
the session's CSRF token, or an authenticated one — or `POST /login` — arrives from another
`Origin`, *then* it is `403` with no change, while an unauthenticated one gets the `401` or
`303` above before its `Origin` is looked at; *when* `/v1/recover` is requested
through the sidecar, *then* it is not reachable by any route or page; *when* the daemon is stopped, its token rotated by `walletd init`, and the daemon restarted
while the sidecar keeps running, *then* the sidecar's next forwarded request uses the new
token; and *when* the sidecar is started on a config with no password hash, a non-loopback
`daemon_url`, a world-readable config file, or a config directory owned by or writable by
another user, *then* it refuses to start and serves nothing. The steps above are the shape
of the scenario, not its extent: every other refusal `HST-26` enumerates at provisioning and
at start — a hash of the wrong variant, version or sub-minimum parameters among them — and
every other response `HST-31` fixes at request time — the lockout under a concurrent burst,
`Cache-Control: no-store` on an authenticated page among them — is exercised on its own and
answered as its owner requires. Demonstrates `HST-26`, `HST-31`, `HST-27`, `SEC-22`, `SEC-5`.
