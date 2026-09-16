# 06 — Allocator and automation

What a compliant wallet decides on the user's standing instruction, and how it carries the
decision out: the pure decision core, the route economics it reads, the scoring and
eligibility that feed it, evacuation, the active probe and discovery, the goal-scoped conflict
rule, the tick that turns decisions into admitted intents, the scheduler cycle a resident host
drives, and the readiness signal that says whether any of it ran. Every requirement states a
behaviour observable at a boundary — what reaches a federation or gateway, what is decided over
which inputs, what is journaled, what a frontend sees — and not how an implementation
structures the code that produces it (`ADR-0032`). A name in backticks is a persisted or
serialized shape (`STO-6`, `STO-9`, `STO-13`, `STO-15`, `STO-26`), a wire field (`API-15`,
`API-16`) or a protocol fact; the variants of `Action` (`DOM-7`), `ReasonCode` (`DOM-11`), the
route status (`DOM-18`) and the active-probe verdict (`DOM-13`) are the domain model's.

Vocabulary. A **decision** is one element of a plan: an executable `Move` or `Evacuate`, or an
advisory `RefuseInflow`, which becomes a `Refusal` row and never an intent (`DOM-7`). A
**plan** (or **round**) is the decisions for one occurrence (`DOM-16`). A **cycle** is one run
of the scheduler (`ALC-38`); a **tick** is the planning and commit inside a cycle, or the
one-shot standalone verb that does the same (`ALC-36`). The **light probe** and the **active
probe** are `DOM-14`'s.

## The decision core

**ALC-1** The allocator's decision is a pure function of a **snapshot**, the **occurrence** it
plans for and the **goal blockers** in force (`ALC-31`): it performs no IO, and two decisions
over equal inputs MUST be identical (`OVR-6`). It yields the **decisions**, the **suppressed**
candidates a blocker withheld (`ALC-30`) and the **deferred** funding goals (`ALC-10`); a
committing tick writes every one of the three (`ALC-34`), a dry run reports them (`ALC-44`), and
producing the last two MUST NOT change the first. The snapshot carries: the joined, open federations whose light probe
succeeded (`FMI-25`) in **ascending `FederationId`** order, byte-lexicographic over the 32
bytes, each with its `spendable` balance (`FMI-27`), whether it is probed, its `shutdown_notice`
(`FMI-26`), its `healthy` flag — `FMI-25`'s `quorum_live`, the threshold read that succeeded —
and its `eligible_to_fund` (`ALC-15`); the designated
spending and standby federations (`ALC-16`); from the stored `Policy` (`STO-13`) `per_fed_cap`,
`spending_target`, `standby_target`, `max_fee_bps_of_move`, the evacuation cap components
(`ALC-20`) and the two pins; `min_move`, the lnv2 minimum incoming contract of 5 000 msat
(`FMI-16`); the route economics by ordered pair (`ALC-13`); and the projected reservations
(`ALC-35`). Snapshot order is emission order, and decides which of two same-tick evacuations
into one destination gets the cap room (`ALC-9`).

**ALC-2** The decision reads no other input. It does **not** read the flat `max_fee` — the flat
cap bounds no allocator-emitted action (`DEF-1`) — and it does not read the clock: the
occurrence, not the time, is a decision's epoch.

**ALC-3** One policy governs every path. Every planning and probing path — a resident host's
tick, `GET /v1/status`, and the standalone `tick`, `status` and `probe` verbs — MUST run under
the stored `Policy` (`STO-13`, `OVR-8`): its targets and caps, its probe amount and leg fee cap
(`max_fee`, `DOM-15`), its probe budget and its cadences. A one-shot standalone verb MAY apply
flag overrides to those values for that invocation under `OPS-7`'s rule — an override "MUST be
validated and MUST NOT be persisted" (`HST-10` lists the flags). The active-probe verdict
(`ALC-25`) MUST be computed under the stored `probe_amount` and `max_fee`, so an attempt made
through any entry point qualifies on the same terms.

**ALC-4** The procedure, in order:

1. For each federation in snapshot order: if it has an evacuation reason (`ALC-17`), plan an
   evacuation or the refusal `ALC-17` names and admit it against the blockers (`ALC-30`);
   independently, if `spendable > per_fed_cap` (strict), emit an advisory `OverCap` refusal
   with empty diagnostics.
2. Top up spending: `want = funding_shortfall(spending_target, …)` (`ALC-6`), and only when
   `want > 0` **and** the spending federation has no evacuation reason (otherwise this step
   emits nothing). The source is the standby federation unless it has an evacuation reason (a
   source is not gated on probes or eligibility); `available = max_fundable(standby spendable −
   its outbound reservations − what this plan already debited from it)` (`ALC-8`); then fund
   into spending per `ALC-5`.
3. Fund standby under the same two guards, with the source's budget additionally floored at the
   spending target — `spendable − spending_target − outbound − debited` — so spending is never
   drained below its target.

The allocator MUST NOT emit `DirectInflow`, `Join`, `Recover`, `Pay` or `Receive` (`DOM-7`).

Admission into the plan: a candidate a blocker withholds goes to **suppressed** and reserves
nothing (`ALC-30`); an admitted `Move` or `Evacuate` credits `amount` to its destination and
debits `amount + fee_cap` from its source for the rest of the plan, both saturating; the plan
holds at most **one decision per key** (`STO-6`) — an executable decision whose key is already
held is not emitted a second time, and when two refusals share a key the one carrying figures
replaces one whose diagnostics are empty, keeping the first one's position (an `OverCap`
refusal with figures therefore replaces the advisory one for the same federation).

The emission order is therefore: for each federation in snapshot order, its `Evacuate` or
evacuation refusal, then the suppression twin if the evacuation was withheld (`ALC-30`), then
its advisory `OverCap`; then the spending step's decisions; then the standby step's. Within one
funding step the order is: the receive-blocker refusal (which ends the step) | the `Move` |
`OverCap` | `UneconomicRoute` (which ends the step) | the shortfall refusal — so one destination
with a move, a cap refusal and a shortfall refusal yields `[Move, OverCap, SpendingBelowTarget]`
and exactly those rows. The ledger `seq` order of one tick's rows follows this order (`ALC-34`).

**ALC-5** Funding into one destination (`ALC-4` steps 2 and 3), evaluated in this order. A row
whose outcome says "the step ends" is an early exit; every other row falls through to the next:

| Condition | Outcome | What is visible |
|---|---|---|
| the destination is not eligible to fund, or not probed (`ALC-15`) | `RefuseInflow NotProbed` with source-side diagnostics; the step ends | refusal row |
| the source is the destination | nothing; the step ends | nothing — this is not a decision |
| `want < floor` (`ALC-10`) and the route is not `UneconomicAtAnySize` | a **deferred** funding goal `{dest, source, reason, want, floor, floor_source}`; the step ends | a `Refusal` row (`ALC-34`) and `status` `deferred` (`ALC-44`) |
| `cap_room` (`ALC-9`); `amount = min(want, cap_room, available)`; if the route is `Unroutable` or `UneconomicAtAnySize`, **or `amount < floor`**, then `amount = 0` | the crumb rule: an amount that would not clear the floor is never moved, and the shortfall refusal below records why | see below |
| a source exists and `amount > 0` | the `Move` — admitted, conflict-suppressed (`emitted_amount = 0`, `ALC-30`), or not emitted again under a held key | move / refusal / nothing |
| route `UneconomicAtAnySize` | `OverCap` first when `want > cap_room`, then `UneconomicRoute`; the step ends with **no** shortfall refusal, even when `want < floor` | one or two refusal rows |
| `want > cap_room` | `OverCap` with figures | refusal row |
| suppressed, or `amount < min(want, cap_room)` | `SpendingBelowTarget` / `StandbyBelowTarget` | refusal row |

An `Unroutable` pair gets no dedicated refusal: the amount is forced to zero and the shortfall
refusal records it. When the candidate move was conflict-suppressed, **every** refusal this step
emits — the `OverCap` one included — is keyed `conflict-suppressed:<candidate key>:<tag>`
(`ALC-30`, `STO-6`).

The `RefusalDiagnostics` each refusal carries (persisted on the row, `STO-15`; refusal identity
is `fed + reason`, and the figures never distinguish two refusals). "src?" is `Some` iff a
usable source existed, else `None`:

| Refusal | `source` | `want` | `available` | `source_spendable` | `max_fee` | `max_fee_bps` | `cap_room` | `amount` | `conflict_suppressed` | `min_move` |
|---|---|---|---|---|---|---|---|---|---|---|
| receive-blocker (`NotProbed`) | src? | `Some(want)` | src? (the `max_fundable` result) | src? | `None` | `Some(bps)` | `None` | `None` | `false` | `Some(min_move)` |
| deferred funding goal (its row, `ALC-34`) | src? | `Some(want)` | src? | src? | `None` | `Some(bps)` | `None` | `Some(0)` | `false` | `Some(min_move)` |
| funding `OverCap` / `UneconomicRoute` / shortfall | src? | `Some(want)` | src? | src? | `None` | `Some(bps)` | `Some(cap_room)` | `Some(emitted)` — `0` if suppressed, else `amount` | as suppressed | `Some(min_move)` |
| advisory `OverCap`; evacuation with no destination | all `None` / `false` |
| evacuation, source drained (`amount == 0`) | `Some(from)` | `None` | `Some(src_available)` | `Some(spendable)` | `None` | `None` | `Some(cap_room)` | `Some(0)` | `false` | `None` |
| evacuation suppression twin (`ALC-30`) | `Some(from)` | `None` | `Some(src_available)` | `Some(spendable)` | `None` | `None` | `Some(cap_room)` | `Some(0)` | `true` | `None` |

**ALC-6** `funding_shortfall(target, spendable, target_credit, credited_this_plan) = target −
spendable − target_credit − credited`, saturating. `target_credit` counts only pending `Move`
and `Evacuate` deliveries into the target (`OPS-9`); an external `Receive` or `DirectInflow` in
flight does not reduce the shortfall.

**ALC-7** A funding move's fee cap is **proportional**: `move_fee_cap(amount, bps) = floor(amount
× max_fee_bps_of_move / 10 000)` in 128-bit arithmetic, stamped on the `Move` (`DEF-1`). A
`max_fee_bps_of_move` of `0` or above 10 000 is an invalid policy (`DOM-15`); this rule owns
that range.

**ALC-8** Sizing reserves `amount + cap(amount)` from the source, never a flat cap:
`max_fundable(budget, bps) = ((budget + 1) × 10 000 − 1) / (10 000 + bps)` in 128-bit
arithmetic, the exact integer maximum with `amount + floor(amount × bps / 10 000) ≤ budget`
(`DEF-1`).

**ALC-9** The per-federation cap is enforced by the allocator four ways: `cap_room = per_fed_cap
− spendable − inbound reservations − credited this plan` (saturating) clamps every funding and
evacuation amount; an evacuation destination needs `cap_room > 0`; a federation already over the
cap gets the advisory refusal of `ALC-4`; `want > cap_room` gets an `OverCap` refusal with
figures. The cap is re-checked with fresh balances at commit (`ALC-53`, `OPS-7`) and again
before minting (`OPS-22`). The allocator moves balance between federations and never raises the
wallet's total; whether that total is capped is open (`11-open-questions.md`, question 2).

## Route economics

**ALC-10** The funding floor is `max(route.min_viable_amount, min_move)` when the pair is
`Routable`, else `min_move`. `Unroutable` and `UneconomicAtAnySize` force the amount to zero. A
shortfall below the floor is **deferred**, not refused, with `floor_source = route_min_viable`
iff `floor > min_move`, else `protocol_min_move` (`API-15`); a shortfall at or above the floor whose clamped
amount falls below it is zeroed and **refused** (the crumb rule, `ALC-5`). Over-blocking
self-heals as the shortfall grows, while under-blocking churns forever, so the floor is an
explicit upper bound on what may be withheld and MUST be recomputed every tick, never cached. A
deferred shortfall MUST leave a ledger row (`OVR-4`, `ALC-34`) and MUST be reported by `status`
(`ALC-44`).

**ALC-11** Unpriced is permissive. A pair is left **unpriced** (absent from the map, floor
`min_move`) when: the quote budget or deadline is exhausted; the fundable maximum (`ALC-13`) is
zero; more than four gateways are listed; any gateway fee request fails (`FMI-11`:
unavailable); the federation receive quote errors; both send quotes error; the vetted list is
empty; every candidate's slope is indeterminate; or the pair is conflict-blocked (`ALC-31`). It
is `Unroutable` only when at least one gateway is listed and every listed one fails validation
at one end or the other (a `null` answer, `FMI-11`), and `UneconomicAtAnySize` only when the
proof in `ALC-12` holds. The budget is one per tick: a 10 000 ms deadline from the tick's start
and **24 calls**, where one call is each of: the destination's gateway list, each candidate's
receive-fee request, each candidate's send-fee request, the federation receive quote, the
federation send quote, and the send-quote fallback. The concrete preflight (`ALC-32`) runs
under the same deadline but consumes no call. The budget and the priced map are shared across
every route revision and across the replacement and ordinary rounds of one plan (`ALC-32`), so a
pair priced once is never re-quoted in that tick.

**ALC-12** `min_viable_amount(quotes, bps)` for one candidate, with `PPM = 10⁶`, `BPS = 10⁴`,
every product in 128-bit saturating arithmetic, `recv`/`send` the gateway `{base_msat, ppm}` at
each end, `recv_fed`/`send_fed` the federation fees sampled per `ALC-13`:

1. `recv.ppm ≥ PPM` → `UneconomicAtAnySize`.
2. **All six** of `recv.base, recv.ppm, send.base, send.ppm, recv_fed, send_fed` zero →
   `Routable(0)`.
3. `p = PPM − recv.ppm`, `q = PPM + send.ppm`, `k = recv_fed + recv.base`, `c = send_fed +
   send.base`.
4. Lower-bound proof from the gateway terms alone, at the 5 000 msat minimum contract:
   `gw_slope = (recv.ppm + send.ppm) × BPS`, `cap_gw_slope = bps × PPM`, `D = PPM × BPS`,
   `margin = (recv.base + send.base) × D + 5 000 × (gw_slope −̇ cap_gw_slope)` (saturating
   subtraction). If `gw_slope ≥ cap_gw_slope && margin ≥ 2 × D` → `UneconomicAtAnySize`.
5. `cap_slope = p × (BPS + bps)`, `fee_slope = BPS × q`. `cap_slope ≤ fee_slope` →
   `Indeterminate` (never a permanent status: integer flooring can still admit a finite window).
6. Else `floor = ceil(BPS × (q × k + p × (c + 1 + ceil(q / PPM))) / (cap_slope − fee_slope))`,
   saturated to the largest representable `u64`; `Routable(floor)`.

Every rounding is upward: the floor MUST never under-estimate the true break-even (`CNF-37`).

**ALC-13** Pricing, once per tick:

- Pairs: exactly `(standby, spending)` and `(spending, standby)` when both are designated and
  distinct, minus the pairs `ALC-31` blocks; a pair already priced in this tick is skipped.
- Fundable maximum: for `(standby → spending)`, `want = funding_shortfall(spending_target,
  spending.spendable, target_credit(spending), 0)` and `protected = 0`; for `(spending →
  standby)`, `want = funding_shortfall(standby_target, standby.spendable,
  target_credit(standby), 0)` and `protected = spending_target`; `budget = source.spendable −
  protected − outbound(source)`; `maximum = min(want, max_fundable(budget, bps), per_fed_cap −
  dest.spendable − inbound(dest))`, all saturating. Same-plan credits and debits are not
  consulted here. `maximum == 0` → unpriced.
- Candidates: the destination's vetted list (`FMI-10`), in list order. Per candidate, the
  receive fee at the destination and then the send fee at the source, each read from its
  `routing_info` (`FMI-11`): a `null` at either end skips the candidate; an unavailable gateway
  at either end unprices the pair. No serving candidate among `n > 0` listed → `Unroutable
  {resolved_gateway: None, min_viable_amount: 0}`.
- Federation fees are sampled once at `sample = maximum + move_fee_cap(maximum, bps)`: the
  receive quote at `sample`; the send quote at `sample`, falling back to `maximum` when that
  quote errors (a source-constrained pair), and unpriced if both error.
- Selection: for each serving candidate compute `floor = min_viable_amount` (`ALC-12`) and
  `cost = modelled_fee(maximum)` where, in 128-bit arithmetic, `k = recv_fed + recv.base`,
  `invoice = ceil((maximum + k) × PPM / (PPM − recv.ppm))`, `send_gw = ceil(invoice × send.ppm /
  PPM) + send.base`, `cost = (invoice − maximum) + send_gw + send_fed` (the largest
  representable value when `recv.ppm ≥ PPM`). If any candidate is `Routable`, the result is the
  `Routable` candidate with the smallest `cost`, ties broken by **first in list order**
  (`FMI-12`), as `{resolved_gateway: Some(gw), min_viable_amount: floor, Routable}`. Else if any
  candidate is `Indeterminate` → unpriced. Else the `UneconomicAtAnySize` candidate with the
  smallest `cost` (same tie-break) as `{resolved_gateway: Some(gw), min_viable_amount: 0,
  UneconomicAtAnySize}`.

Fee inputs enter from **both** legs: gateway base and ppm each way plus both federation fees.
The `resolved_gateway` is stamped on the emitted `Move` (and on an `Evacuate` of the same pair,
`ALC-17`) as the route hint (`CONTEXT.md` **Route hint**), so which gateway wins here is
wire-visible.

## Scoring and eligibility

**ALC-14** The structural floor collects failing reasons in this order: `guardian_count < 2` →
`NoFaultTolerance`, **else** `guardian_count < 4 || threshold < 3` → `TooFewGuardians` (a
1-of-1 therefore carries `NoFaultTolerance` alone, never both); `threshold == 0 || threshold >
guardian_count || threshold < n − (n−1)/3` (saturating) → `InvalidThreshold` (`FMI-24`); not
mainnet when `require_mainnet` → `WrongNetwork` (`FMI-5`); a required module missing (`Mint`,
`Wallet`) → `MissingModule`; shutdown scheduled → `ShutdownScheduled`; no lnv2 → `NoLnv2` (not
policy-tunable). Discovery applies the same floor (`ALC-28`).

**ALC-15** `eligible_to_fund = floor_ok && quorum_live && gateway_available`, all three from the
light probe, which spends nothing (`DOM-14`): the floor is `ALC-14`, `quorum_live` is `FMI-25`'s
threshold read, and `gateway_available` is true when some gateway on the federation's vetted
list serves it (`FMI-14`; an empty list is a valid list, `FMI-10`). No reputation, rating or
third-party prior is an input to eligibility or rank: `ADR-0017` and `ADR-0020` permit such an
input only to demote ("may rank or demote among already-probe-passed federations; it may NEVER
fund or block"), and no requirement in this set produces one (`FMI-28`: "nothing the Observer
says is load-bearing"; `FMI-43`), so the `LowReputation` reason (`DOM-11`, `ALC-51`) is
persisted vocabulary that no requirement in this set emits. The
snapshot's final eligibility is `(eligible_to_fund || pinned) && probe_gate_ok` (`ALC-37`,
`DOM-3`): a pin overrides the scorer; nothing overrides the probe gate.

**ALC-16** Rank, `u32` saturating, only for an eligible federation (else 0): `min(threshold,
guardian_count) × 100`, `+ 50` if a peg-out fee is quotable, `− latency_ms / 10` (`FMI-25`).

Auto-designation: the designatable set is every federation with `eligible_to_fund &&
probe_gate_ok` — a pin does **not** enter it — sorted by rank **descending**, then `spendable`
**descending**, then id **ascending** (`DOM-4`). The spending federation is the policy pin, else
the first designatable federation that is not a probe-gated member (`ALC-37`) and not the
pinned standby. The standby federation is the policy pin, else the first designatable
federation that is not the spending federation (a probe-gated member whose verdict is `Passed`
MAY be standby, never auto-spending). Either MAY be `None`.

## Evacuation

**ALC-17** The **evacuation reason** is `ShutdownNotice` when the snapshot's `shutdown_notice`
holds, else `Unhealthy` when it is not `healthy`; shutdown wins. The destination is the pinned
standby when it is eligible for evacuation, else the eligible federation with the **smallest
id** (byte-lexicographic); eligible means not the source, no evacuation reason of its own, no
receive blocker (`ALC-5`'s first row) and cap room (`ALC-9`: `cap_room > 0`). No destination →
a refusal with empty diagnostics. `amount = min(source spendable − outbound − debited,
cap_room)`; zero → a refusal with figures (`ALC-5`); else `Evacuate {fee_cap:
components.at(amount), gateway: route hint, fee_cap_components}` keyed
`evac:<from>:<to>:<occurrence>` (`STO-6`). The hint is the pair's `resolved_gateway` when the
pair happens to be priced (an `UneconomicAtAnySize` entry's gateway included), else `None`. The
stamped cap is the **planning cap at the planned amount**; the executor recomputes at the
delivered net (`OPS-21`). `CNF-14` and `CNF-20` demonstrate the drain.

**ALC-18** Route economics MUST NOT gate an evacuation: no `min_move`, no route status, no fee
pre-reservation on the source (`DEF-3`), and no requirement that a gateway serve both ends. A
dying federation is drained even when the route prices badly; the cap, not the floor, is the
backstop. `OVR-13` owns the fall-through — "when no gateway serves both federations, an
evacuation MUST fall through to a hop over two gateways on different Lightning nodes, each leg
chosen from its own federation's vetted list" — and `FMI-14` and `OPS-21` place it at fresh
sizing inside the same attempt; what this rule adds is the allocator's half: the evacuation is
emitted whenever a destination exists (`ALC-17`), and the route-revision loop's preference for
a destination with a shared gateway (`ALC-32`) MUST never suppress it.

**ALC-19** Two leads, distinct by name. The **trigger lead** is 24 hours — this rule owns the
number; `FMI-26` owns the corroboration rule and the combination of signals that schedules an
evacuation within it. It is a constant of the wallet, not a policy parameter. The **wake
lead** is the runtime-mutable `Policy.evacuation_lead_secs` (`STO-13`): the
scheduler sleeps until `expiry − wake lead` and, once inside that window, re-wakes every
`min(min_interval, expiry − now)` — at the minimum interval, but never past the expiry itself
(`ALC-39`). The wake lead never triggers an evacuation, and the trigger lead never governs
the sleep.

**ALC-20** The evacuation cap is `EvacFeeCap {base_msat, bps}.at(net) = base + floor(net × bps /
10 000)`, computed in 128-bit arithmetic and saturated to `u64` (`DOM-19`); the defaults are
`STO-13`'s. A `bps` above 10 000, or the pair `(0, 0)`, is an invalid policy (`DOM-15`; this
rule owns the range); `bps = 0` alone (a base-only cap) is legal (`DEF-3`).

**ALC-21** Every enforced evacuation cap is computed from the **delivered net** — `invoice −
receive_quote`, what the destination is actually credited — never from the sized ask
(`CONTEXT.md` **Delivered net**, `OVR-7`). The planning cap is the one deliberate exception and
is superseded by the recomputed cap as soon as sizing runs.

**ALC-22** The allocator stamps the planning cap and the components (`ALC-17`) and nothing
else; the sizing search that turns the planned amount into a delivered net — two passes over
delivered net with a viability post-check — is the executor's and is `OPS-44` (`OPS-21`). What
the allocator side owns is the marker that search leaves behind: a refusal whose evidence is
structural (`ALC-24`) is the marker (`OPS-31`), carrying two freshly re-quoted samples (the
5 000 msat floor and the largest probed affordable amount); every other refusal is `Retryable`.

**ALC-23** A cap edit **qualifies** to replace a marked evacuation iff `new.base ≥ old.base &&
new.bps ≥ old.bps && (new.at(low.net) > old.at(low.net) || new.at(high.net) >
old.at(high.net))`. Component-wise monotone and strictly larger at a recorded sample; a crossed
edit (base up, bps down) or one whose bump truncates away does not qualify, and `status` warns
for each marker the current cap cannot replace (`ALC-44`, `DEF-7`). `CNF-24` demonstrates the
replacement.

**ALC-24** Structural evidence, given the cap and the two samples `low` and `high` (`DOM-19`),
in signed 128-bit arithmetic: with `span = high.net − low.net`, there is no evidence unless
`span > 0`; `rise = high.fee − low.fee` (may be negative), `cap_rise = bps × span`, `fee_rise =
rise × 10 000`, and `fixed = low.fee − rise × low.net / span` with `/` truncating toward zero:
`fee_rises_no_faster_than_cap = cap_rise ≥ fee_rise`; `fixed_component_exceeds_cap_base =
fee_rise ≥ cap_rise && fixed > base && low.fee > cap.at(low.net)`; `is_structural` is the **OR**
of the two. The caller MUST separately establish that both samples are over their caps. It is
two-point evidence on a non-monotone curve, not a proof, and nothing requires a proof: the
evidence feeds the supersession audit record (`STO-25`) and the qualification rule (`ALC-23`)
and never turns into route-unavailability (`CONTEXT.md` **Structural evacuation refusal
evidence**).

## Probes and discovery

**ALC-25** The active-probe **verdict** (`DOM-13`) over a candidate's `attempts` (`STO-26`), a
source federation, `now` and the stored policy (`ALC-3`; the defaults are `STO-13`'s): no
attempts → `NeverProbed`; sort by `at_ms` (stable); the window is the attempts with `now −
at_ms ≤ ttl` (`probe_ttl_secs`; the boundary is in-window); an empty window → `Expired` if any attempt ever qualified,
else `NeverProbed`; the suffix is the successes strictly after the most recent in-window
failure; an empty suffix → `FailedSinceLastPass` if any contiguous success run before that
failure qualifies (count and span), else `Failed`; **qualifying** = `ok && same source &&
amount_msat ≥ probe_amount && leg_fee_cap_msat ≤ max_fee`; `Passed` iff the qualifying suffix
holds `≥ probe_min_successes` and `newest.at_ms − oldest.at_ms ≥ probe_min_span_secs`, else
`Insufficient`. Failures count regardless of source; successes only from the same source. The
verdict is computed, never stored (`DOM-13`), over the retained history, which `STO-26` prunes
on every outcome write.

**ALC-26** Two budget checks guard a probe, both over the rolling 7-day window measured from a
row's `max(created_at_ms, updated_at_ms)`:

- The scheduler's **pre-filter**: `attempts < max_probe_attempts_per_week && spend <
  max_probe_spend_per_week`, counting agent `Probe` rows with a recorded `cost_msat`; its reset
  time is the earliest such row's effective time + 7 d. A fresh probe that fails it is skipped
  with a `watch-probe-skip:<candidate>:<spending>:<amount>:<bucket>` row (`STO-6` owns the
  shape and the `bucket` encoding) written `Started` then `Failed` under `StandingInstruction`
  with the reason as its `error`, and the deadline wakes at the reset (`ALC-52`).
- The **admission check**, which is what refuses (`OPS-39`: `budget_exhausted`): with
  `reservation(a, c) = max(a + c, 2 × c)` for an amount `a` and leg cap `c`, entries retained
  while `active || age < 7 d`, `attempts` = costed entries, `active` = uncosted non-terminal
  umbrella rows (each reserving its session's `reservation`, or the policy's when the session
  is gone), it refuses iff `attempts + active + 1 > max_probe_attempts_per_week || spend + Σ
  reserved + reservation(probe_amount, max_fee) > max_probe_spend_per_week`. A wallet at `spend
  = max − 1` therefore passes the pre-filter and is refused here. While the budget cannot be
  read, every fresh probe MUST be refused, and the refusal leaves the skip row (`ALC-48`).

**ALC-27** The active probe (`FMI-34`, `CNF-16`): resume an in-flight session first (its `from`,
amount and leg cap win over the caller's); else sample the candidate's baseline balance (`0`
when not open) and begin a session (`STO-26`); write the umbrella `probe:<fed>:<nonce>` row
(`STO-6`); for a fresh probe or a resume before leg IN is journaled, **preflight** — both
federations open, `source.spendable ≥ amount + leg_cap`, `candidate.spendable + amount ≤
per_fed_cap`, `source.spendable ≤ per_fed_cap`, and a gateway serving the route both ways
(`FMI-13`) — where a failure is a no-attempt that changes no verdict; re-sample the baseline;
leg IN as a `Move` keyed by the user-move shape `move:<from>:<to>:<amount>:<fee_cap>:<occurrence>`
(`STO-6`) with the occurrence derived from the nonce (`DOM-16`), admitted through the
admission point (`OPS-5`) and awaited to terminal (a non-terminal outcome is transient and the
session is retained); size leg OUT from `delivered_in − 1 000` msat and persist it on the
session; `out_fee_cap = min(leg_cap, delivered_in − out_net)`; the no-sweep check
`candidate.spendable == baseline + delivered_in` (exact equality) and a source-cap re-check
`source.spendable ≤ per_fed_cap`, both only while leg OUT is not yet journaled; leg OUT, sized
by the search of `OPS-44` with `cap = {base: leg cap, bps: 0}` and no viability post-check; one
atomic outcome write (the attempt appended, the session cleared, the umbrella row `Succeeded`,
`cost_msat = in.amount + in.receive_fee_quoted + in.send_fee_quoted − out.amount`, counting the
in-leg only when `Settled`/`Stranded` and the out-leg only when `Settled`). Every attempt's
`at_ms` is the session's `started_at_ms`, not the completion time. A leg failure demotes (an
`ok: false` attempt) only when it is attributable to the candidate: a `Failed` phase on leg
OUT; or no terminal phase and the failing step is candidate-hosted — the mint for leg IN, the
pay for leg OUT, judged from the record's invoice and send artifacts — and the error is neither
a source-side fault nor one of the protocol's deterministic invoice- or route-defect
rejections (`FMI-17`). `Stranded`, `Refunded`, a `Failed` leg IN, and an ambiguous record are
umbrella-only failures that record no attempt.

**ALC-37** The **probe gate**: a joined federation with no `UserApproved` candidate row is
auto-joined and fundable only when its active-probe verdict is `Passed` (`OVR-5`, `ADR-0017`);
a missing or unreadable candidate row gates fail-closed (`ALC-48`). `approve` (`API-23`) writes
`UserApproved` and exempts it; a user `join` writes it only when no `AutoJoined` row already
exists (`OPS-42`), so re-joining an auto-joined federation does **not** release this gate. A
pin does not bypass the gate (`CNF-17`).

**ALC-28** A discovery pass:

1. Collect from each source under a fair share of the pass deadline (`Observer`, `Manual`;
   `FMI-28`, `FMI-22`; a slow or failed source is recorded, never fatal); group announcements
   by claimed id.
2. Recover agent-joined candidates: a joined federation whose row is `Discovered`/`Rejected`
   and whose registry entry is agent-created becomes `AutoJoined`/`Passed`; a joined
   federation with no row gets one from its joined invite (`source: Manual`, `AutoJoined`,
   `Passed`).
3. The candidate universe is the announced ids ∪ (when `auto_join`) every stored non-joined
   `Discovered` id, sorted; take a rotation window of `max_candidates_per_pass` from the stored
   cursor and rotation (`STO-12`).
4. Per candidate in the window, stopping at the pass deadline: a **joined** candidate is
   refreshed only if it has no row, or its row is `AutoJoined`/`UserApproved` and some
   announced invite differs from the stored one (the stored invite is replaced); a
   `Discovered`/`Rejected` row of a joined federation is left untouched without a fetch. An
   unjoined candidate is fetched iff it has no row, or (announcements exist and) **the stored
   invite is no longer announced** or `now − structural_checked_at > 7 d`; a differing invite
   that merely coexists with the still-announced stored one does not force a fetch. A fetch
   previews the first invite that authenticates within the per-candidate timeout (`FMI-22`),
   requires `claimed_id == invite id == config id` (the Sybil check, `FMI-28`), and applies the
   structural floor (`ALC-14`) with the stored `require_mainnet`: `Passed` keeps an existing
   `AutoJoined`/`UserApproved` state and otherwise writes `Discovered`; rejected writes
   `Rejected(<first reason>)`. The row keeps the existing `source` and `discovered_at_ms`, and
   sets `structural_checked_at_ms = updated_at_ms = now` (`STO-26`).
5. One `Discover` ledger row per source (`STO-15`); then auto-join if enabled (`ALC-29`); one
   `AutoJoin` row (`autojoin:<nonce>`) always; advance the cursor over attempted ids only;
   `wrapped` iff the window completed, auto-join completed (or stopped for budget) and the plan
   wrapped; `backlog = !wrapped && universe non-empty`.

**ALC-29** Auto-join considers only non-joined `Discovered` rows in the window, in window order,
with the budget checked before each in this order: `lifetime ≥ auto_join_lifetime_cap` →
blocked (stops the pass); `weekly ≥ max_auto_joins_per_week` → blocked (stops);
`concurrent_unproven ≥ 3` → skip this candidate. The first two are policy fields (defaults 20
and 5, `STO-13`); the concurrent-unproven limit of **3** is a constant of the wallet, not
runtime-mutable. A candidate not floored this pass is re-previewed first: an id mismatch writes
`Rejected("IdMismatch")`, a structural failure `Rejected(<reason>)`, a preview error leaves it
`Discovered`. A newly joined candidate is `AutoJoined` and probe-gated (`ALC-37`), and the three
counts are incremented locally for the rest of the pass; a join that merely reopened an existing
membership leaves the row `Discovered`. Auto-join builds no intent and leaves the nonce-keyed
`join:<fed>:<nonce>` row (`DOM-7`, `FMI-8`). `auto_join` defaults to `false`.

## Conflicts

**ALC-30** Suppression is scoped to the **allocator goal** (`DOM-17`), never a global count
(`DEF-6`). A live intent (`Pending`, `Executing`, `Awaiting`) holding a goal blocks a candidate
decision iff the goals are equal, or the holder is `Evacuate(s)` and the candidate is a `Move`
touching `s`; the candidate's own key never blocks it. `FundInto(A)` pending does not block
`Evacuate(A)`; `Evacuate(A)` live blocks any funding move from or into `A` but not another
federation's evacuation into `A`. A suppressed funding decision co-emits its refusals with
`amount: Some(0)` and `conflict_suppressed: true`, each keyed
`conflict-suppressed:<candidate key>:<tag>` (`ALC-5`, `ALC-51`); a suppressed non-zero
evacuation emits its twin `conflict-suppressed:<evac key>:<tag>` (a zero-amount suppressed
evacuation emits nothing). Every such row's `error` MUST name the operation key of the intent
whose goal suppressed it, so the ledger alone explains the suppression (`OVR-4`); `status`
reports the same pairs (`ALC-44`). While an evacuation of either designated federation is
live, no allocator top-up is emitted at all.

**ALC-31** Blockers are computed from the live intents at plan time, folded forward as each
decision in a batch is admitted, and re-scanned at commit (`OPS-11`, `OPS-35`). The pair
pre-filter that skips pricing (`ALC-13`) is conservative: it cannot exclude the candidate's own
key; a held `FundInto(d)` blocks every pair into `d`, a held `Evacuate(s)` blocks every pair
with `s` at either end. The pre-filter saves network IO and MAY be wrong; the admission-time
re-scan is what is load-bearing (`OPS-13`, `ADR-0031`).

## The tick

**ALC-32** A resident host's tick has two halves: **planning**, which performs network IO and
writes nothing but the tick row (`ALC-34`), and **commit**, which admits the planned batch
through the admission point (`OPS-11`, `OPS-13`) and performs no network IO. Planning, in
order: build the snapshot, with every probe-gated member's verdict (`ALC-25`) evaluated against
the spending federation the same facts designate before any verdict is applied (the spending
federation itself is not verdict-gated); project reservations (`ALC-35`); price routes
(`ALC-13`), then drop from the snapshot any pair this plan has invalidated (below); decide
(`ALC-1`); then the **route-revision loop**:

1. In a non-money cycle (`ALC-47`), or with no route budget, the round is returned as planned.
2. Preflight, in emission order, each `Move`/`Evacuate` whose key has **no** existing intent (an
   unreadable journal counts as existing) against the destination's vetted list in list order
   (`FMI-10`): a gateway serving the destination and then the source (`FMI-13`) ends the scan as
   routable; the first problem wins. An empty or unreadable list, or no gateway serving the
   destination, is a **destination** problem; a gateway serving the destination but none of
   those serving the source is a **source-route** problem. Either marks the destination
   **unavailable for the rest of this plan** — the mark MUST NOT outlive the plan (`ALC-48`).
   Deadline expiry before the preflight answers returns the current round with a warning.
3. No problem: if a designated pair is **route-blocked** — its status is
   `Unroutable`/`UneconomicAtAnySize`, some refusal names its destination with a reason other
   than `OverCap` and `diagnostics.want ≥ min_move`, and no `Move` into that destination was
   emitted — mark that destination unavailable, keep the **first** such round as the
   route-blocked fallback, and re-plan; otherwise return the round, except that when a
   route-blocked fallback exists and the final round emits no `Move`, the fallback is returned so
   its refusal stays visible.
4. A problem: if it is a source-route problem on an emitted `Evacuate`, remember this round as
   the evacuation fallback; add the pair to the invalidated set; mark the destination
   unavailable and re-plan, so a destination with a shared gateway is preferred. If the mark
   changed nothing, or a later round no longer evacuates the remembered source, stop and return
   the evacuation fallback: the evacuation is emitted, and the hop is the executor's (`ALC-18`).
5. Every re-plan counts as a route revision; when the count exceeds the number of probed
   federations the current round (or the route-blocked fallback) is returned.

Markers: which reconcile mode preserves, captures or re-drives a structural marker is
`OPS-35`'s (its **preserve**, **capture** and **re-drive without planner** modes); the planner
consumes only a marker its own capture pass parked. The **replacement round** runs first, with
replacements enabled: the qualifying parent is the parked one when the capture pass offered it,
else the **first** live agent `Evacuate` in key order whose occurrence is below the largest
representable value and whose marker qualifies under the current cap (`ALC-23`); its key is
excluded from the blockers and its reservations from the projection. The first same-source
`Evacuate` of the replacement round is the one-child replacement (`OPS-30`, `OPS-32`); every
other planned decision is set aside as **replacement-deferred** and never committed; with no
such child the plan records a marker-clear disposition instead (`OPS-31`), and the ordinary
round is then planned, sharing the route state, and returned with that disposition. Finally the
pinned inputs are validated: a pin naming a federation the snapshot does not hold is a planning
fault — the round fails, its tick row terminalizes `Failed` (`ALC-34`) and nothing is
committed. Commit: `OPS-11`'s whole-batch guards, then the replacement branch (`OPS-32`) or the
per-decision loop (`ALC-53`). The tick row is opened before sensing and terminalized when every
accepted driver finishes.

**ALC-33** A resident host allocates the occurrence (`DOM-16`) once per cycle before the tick
row opens, by a checked increment of `WatchState.occurrence` (`STO-12`); an overflow at the
largest representable value is `Permanent` and fails the cycle. The wallet MAY run exactly one
cycle at that value and MUST fail every later one with `cycle_failed` (`ALC-45`, `CNF-38`);
the standalone tick MUST refuse it up front (`ALC-36`).

**ALC-34** Ledger rows per tick (shapes `STO-6`, kinds `STO-15`): one `Tick` row keyed
`tick:<occurrence>:<nonce>` — `Started` before sensing, terminalized with the decision,
performed and failed counts, `Succeeded` iff `failed == 0` and the batch carries no error (a
zero-decision batch refused for a stale policy generation or a reservation-projection fault
carries the error and terminalizes `Failed`); the standalone tick additionally requires no
decision skipped for a terminal key; one `Refusal` row per advisory decision **and per deferred
funding goal** (`ALC-5`, `ALC-10`; keyed `refuse:<tag>:<dest>:<occurrence>`, the tag that of
the shortfall it defers, `error` naming the floor and its `floor_source`), status `Succeeded`,
`error` = the batch note when one applies, **append-once** (an existing key is never rewritten,
so the figures are those at first observation); one `tick-drop:<occurrence>:<key>` row per
executable decision dropped at commit (`ALC-53`) or newly suppressed by the standalone re-scan
(`ALC-36`) — a `Refusal` row, status `Succeeded`, `error` = the drop message, diagnostics all
default except `conflict_suppressed = true` and `amount = Some(0)` when the drop was a conflict
on a non-zero move. A whole-batch refusal (`PolicySuperseded`, world-generation drift, an
invalid plan or balance authority, or a live-intent scan fault) terminalizes the tick row
`Failed` and writes no per-decision rows; the one exception is a reservation-projection
storage fault, which writes the advisory refusal rows before terminalizing `Failed`. The
commit-time missing-destination-balance drop inside the fresh-target check (`ALC-53` item 6)
writes no `tick-drop` row; the earlier missing-balance check (item 1) does. Every ledger write
around a tick is best-effort (warn on error) except the money path (`OVR-4`), and a tick whose
row could not be opened MUST NOT plan (`ALC-48`).

**ALC-35** Planning and commit use the **allocator** reservation projection (`OPS-9`), which
weakens each in-flight move's reservation by its recorded phase, and a plan so projected is
valid only with the balance generation that authorized it (`OPS-11`, `OPS-13`). A corrupt move
record falls back to the strict projection for that intent; a retryable read error aborts the
plan.

**ALC-36** The standalone tick (`OPS-12`, `HST-9`), in order: refuse an occurrence equal to the
largest representable value (`DOM-16`); record the occurrence as the floor (`STO-12`); open the
tick row; plan as `ALC-32` plans; refuse a plan carrying both a replacement and
a marker disposition (`Failed` row); re-scan the live intents for blockers and write
`tick-drop` rows for newly suppressed decisions (`ALC-34`); validate the pins (bail with a
`Failed` tick row); **bail** with a `Failed` row if any executable decision's key already maps
to a `Done`/`Awaiting`/`Failed` intent, telling the operator to pass a fresh `--occurrence` (a
resident host instead drops such decisions one by one, `ALC-53`); report the
replacement-deferred decisions; clear the marker disposition; apply the replacement (`OPS-33`)
or the decisions under the admission arithmetic (`OPS-7`); write the refusal rows; terminalize.
It is not a resident engine and not the model for another host (`ADR-0031`): a host MUST
schedule agent work through the cycle of `ALC-38` and nothing else — a resident host runs that
cycle in a loop, a wake-driven host runs it once per wake (`OVR-10`).

## The scheduler cycle

**ALC-38** One cycle, in order:

1. A reconcile pass in **preserve** mode (`OPS-35`). This is the retry cadence of a `Retryable`
   intent (`OPS-14`): once per cycle, with one exception — a re-drive requested while a driver
   owns the key is honoured by that driver when it leaves the intent `Pending` at the same
   attempt, without waiting for the cycle (`OPS-14`). The cycle interval is the sleep `ALC-39`
   computes — at most `base_interval_secs`, at least `min_interval_secs` (`STO-13`), earlier
   on an expiry or probe deadline, a policy change, or an expiry wake.
2. Ledger repair (`OPS-37`).
3. List the federation registry (`STO-14`) — **fence A**: any skipped row → a recovery-only
   reconcile pass (**re-drive without planner**, `OPS-35`), and the cycle returns blocked
   `corrupt_federation_registry` (`ALC-45`, `ALC-46`, `CNF-51`).
4. Open every registered federation that is not yet open (`FMI-20`) — **fence B**: any still
   unopened → a recovery-only pass, and the cycle returns blocked `partial_federation_view`
   (`CNF-35`).
5. The planner's reconcile pass in **capture** mode (`OPS-35`): release the previous parked
   marker, capture a qualifying one, and authorize planning (refused while a membership change
   or a raw terminal write is in progress, `OPS-41`, or while goal admissions are poisoned,
   `OPS-32`) — when planning is not authorized the cycle continues as a **non-money** cycle
   (`ALC-47`).
6. Allocate the occurrence (`ALC-33`) — **fence C**: failure → `cycle_failed`.
7. If planning may commit, open the tick row (`ALC-34`).
8. The light probe of every open federation, once (`ALC-49`), then balances (`FMI-27`) and the
   facts; route pricing is allowed iff planning may commit; the blockers are the reconcile's.
9. Plan (`ALC-32`), then — only when planning may commit — re-read balances, authorize the
   batch against them and commit (`ALC-53`); a balance authority that cannot be issued
   terminalizes the tick row `Failed`.
10. If commit was never invoked, release the parked marker.
11. Recompute the designation (`ALC-16`) from the cycle's facts and the post-commit balances
    under a fresh policy read; a fresh probe is admitted only when planning may commit and the
    designation succeeded.
12. The due probes (`ALC-52`), each admitted as one probe decision.
13. Discovery if due (`ALC-28`; due = `backlog || now ≥ last_discover + discover_every_secs`;
    a failed pass records `now` and clears the backlog).
14. The deadlines (`ALC-52`, `ALC-39`).

A storage fault in the reconcile's scan (step 1 or 5; `OPS-35`: "a scan fault fails the pass"),
the occurrence (step 6), the watch state, the policy, discovery or the deadlines fails the cycle
(`cycle_failed`, `ALC-45`); so does a read fault in the watchdog or the sleep computation
(`ALC-39`, `ALC-40`). A ledger-repair fault (step 2) and a federation or gateway fault from step
8 onward are warned and the cycle continues: a federation whose light probe errors is dropped
for the cycle (`FMI-25`, `ALC-48`), a discovery source that fails is recorded (`ALC-28`). The
cycle is a **noop** iff nothing failed, the reconcile was idle, zero
decisions were planned, the commit accepted and refused nothing, no probe was attempted and the
discovery watch state is unchanged (`ALC-39`). `CNF-20` demonstrates the cycle end to end;
`CNF-21` that a probe held in flight never delays a user verb (`OVR-3`).

**ALC-39** The sleep after a cycle, all in ms: `discover_delay = min_interval` when the discovery
backlog is set, else `last_discover + discover_every − now` (saturating); `routine =
clamp(min(base, discover_delay), min_interval, base)` (`base_interval_secs`,
`min_interval_secs`, `discover_every_secs`; `STO-13`). Each expiry
deadline yields `evac_point = expiry − wake lead` (`ALC-19`): `evac_point − now` when that is
positive, else `min(min_interval, expiry − now)`. Each probe deadline yields `max(due − now,
1 000)` (the busy-spin floor). The sleep is `routine` capped by the minimum of every expiry and
probe delay. The expiry deadlines are, per probed federation, only the corroborated
`config_expiry_secs` and `meta_module_expiry_secs` (`FMI-26`; never the override meta or the
`/status` flag) and only those still in the future. The wait ends on shutdown, a policy change
(`ALC-41`), the timer, or a per-federation expiry wake from the meta field
`federation_expiry_timestamp` (`FMI-26`); a wake re-adds the hinted expiry, recomputes the
sleep, and is **coalesced**: if the last wake-triggered cycle was a noop (`ALC-38`) less than
`min_interval` ago, the wake waits the remaining cooldown, unless the recomputed sleep is
shorter, in which case the timer runs instead. A fault reading the policy or the deadlines while
computing the sleep is a cycle fault (`ALC-45`), and the wait MUST still be at least
`min_interval`: nothing re-cycles without sleeping.

**ALC-40** The settlement-stall watchdog runs after every cycle: count the `Awaiting` `Receive`
or `DirectInflow` intents older than the deadline (300 s; `HST-2` names the daemon's setting)
**whose invoice has been expired for longer than the deadline** (`DEF-8`) — the invoice read from
the intent, or for a `DirectInflow` from its move record; with no parseable invoice the intent
counts once `now − created_at > 3 600 s + deadline`. At least three such, and no `Receive`
ledger row (a `DirectInflow` success does not count) `Succeeded` with `updated_at` inside the
deadline window among the newest 4 096 rows → the scheduler MUST stop, and the host MUST treat
that as fatal and exit non-zero for its supervisor to restart it (`ALC-42`, `HST-7`). The exit
is its artifact; it writes no ledger row. A journal or record read fault disarms the watchdog
for that cycle only and is reported as a cycle fault (`ALC-48`).

**ALC-41** `PUT /v1/policy` (`API-20`) validates, stores, applies the new caps to every later
sizing, bumps the policy generation (`STO-27`) and wakes the scheduler at once (`ALC-39`). A
round planned under the old generation MUST be refused whole at
commit (`OPS-11`: `policy_superseded`) and its tick row terminalized `Failed`; a fresh probe
planned under the old snapshot MUST be refused the same way.

**ALC-42** Once shutdown begins the cycle issues no further request to any federation or
gateway and admits no further agent work (`HST-7` owns the sequence); a scheduler that stops
for any other reason MUST be fatal to the host, and the host's liveness flag `scheduler_alive`
(`API-16`) MUST read `false` from then on.

**ALC-43** The occurrence floor is `DOM-16`'s ("never decreases, is raised in the same
transaction as any agent ledger append (`STO-21`), and is fail-closed at the largest
representable value"), seeded from the ledger when absent (`STO-23`). What this chapter adds:
no admission path this chapter describes — the tick commit, the standalone tick, a probe leg
— MAY leave it below the highest agent occurrence the ledger holds.

**ALC-44** `GET /v1/status` (`API-15`) and the standalone `status` verb run the planner dry
against the stored policy at `occurrence + 1`: routes are priced and the concrete preflight runs
(network IO, no writes); it warns per pinned-input problem, per structural marker the current
cap cannot replace (`ALC-23`), per decision whose key already maps to a terminal intent, and per
deferred funding goal; it returns the would-run `decisions`, `scored` with `gated_eligible`
read from the planned snapshot, `deferred` (`ALC-10`) and `suppressed` — each conflict-withheld
candidate with the key of the intent whose goal holds it (`ALC-30`). A replacement child whose
occurrence is not strictly newer than its parent's is a stale plan: the resident host's status
MUST fail with that error, the standalone one MUST warn and return the scored view with **no**
would-run decisions (`OPS-33`). `status` and the ledger row of `ALC-34` are the two surfaces
for a floor-deferred shortfall.

**ALC-45** Every path that skips planning MUST set `automation_blocked {reason, detail}` before
the cycle sleeps (`DEF-9`), and `automation_ready` on `/v1/health` is its negation (`API-16`).
The reasons: `corrupt_federation_registry` (fence A, with the skipped-row count as the detail),
`partial_federation_view` (fence B, naming the unopened federations), and `cycle_failed` for
every other skip — a cycle error, the occurrence overflow (`ALC-33`), a storage fault `ALC-38`
names, a tick row that could not be opened, or planning the reconcile did not authorize
(`ALC-47`) — with a detail naming the step. A cycle that plans, commits and then completes its
remaining steps without a fault MUST publish `automation_blocked: None`; a fault after the
commit (discovery, the deadlines, the watchdog) still publishes `cycle_failed`, because the
signal describes the whole cycle. Liveness is not readiness: `scheduler_alive` MUST NOT be read
as `automation_ready`.

**ALC-46** Three planning surfaces MUST refuse a partial or corrupt world rather than plan from
the healthy subset: the scheduler (fences A and B, `ALC-38`), `GET /v1/status` (503 before the
dry run, `API-15`), and standalone `tick`/`status` (refuse before opening, `HST-11`). Explicit
user and admin verbs keep their poison-tolerant behaviour (`STO-14`). A poison registry row is
not an absent federation: its funds may be part of the world the allocator would score
(`DOM-2`).

**ALC-47** When the planner's reconcile pass (`ALC-38` step 5) does not authorize planning, the
cycle MUST run as a **non-money** cycle: no tick row, no route pricing, no commit and no fresh
probe, while ledger repair, retained probe sessions, discovery and the deadlines still run. It
is a planning skip, and `ALC-45` applies to it — reason `cycle_failed`, the detail naming the
reconcile — because a wallet that skips its whole automated cycle every pass is not ready, and a
warning in a log is not a signal (`DEF-9`).

**ALC-48** A wallet MUST NOT withhold agent work silently. Every path on which it declines work
it would otherwise have done in a cycle MUST be observable at a boundary, as follows:

| Withheld | Observable |
|---|---|
| planning skipped for any reason — the fences, an unauthorized plan (`ALC-47`), the occurrence overflow, a tick row that could not be opened, a storage fault `ALC-38` names, a designation that could not be computed | `automation_blocked` with its reason and detail (`ALC-45`); a tick whose row could not be opened MUST NOT plan |
| a fresh probe not admitted — the budget pre-filter, or a refusal at admission (the budget exhausted or unreadable, `ALC-26`) | the `watch-probe-skip:<candidate>:<spending>:<amount>:<bucket>` row of `ALC-26`, `Started` then `Failed`, whose `error` names the cause; a probe the admission check refused is not retried before `retry_backoff` (`ALC-52`) |
| a fresh probe with no source, because no spending federation is designated (`ALC-52`) | `status` reports `spending_fed: null` (`API-15`); no row is written, since the key of `ALC-26` needs a source and there is nothing to probe from |
| a federation dropped from the snapshot because its light probe errored (`FMI-25`), and therefore neither scored, funded nor evacuated that tick | in a cycle that plans: a `Refusal` row keyed `refuse:unhealthy:<fed>:<occurrence>` (`STO-6`), reason `Unhealthy`, status `Succeeded`, diagnostics default, `error` beginning `light probe failed: ` followed by the error — the prefix is what tells this row from `ALC-17`'s no-destination refusal under the same key shape; a non-money cycle reports through `ALC-47` instead |
| a candidate whose candidate or probe record is unreadable, gated fail-closed (`ALC-37`) | `status` `scored[].gated_eligible = false` (`ALC-44`), and the `NotProbed` refusal row whenever funding it was wanted (`ALC-5`) |
| a destination marked unavailable inside one plan (`ALC-32`) | when the destination stays a funding target, the re-planned round's `NotProbed` refusal for it; when re-planning designates another destination instead, the `Move` into that one is the record and no refusal is synthesized for the first. Either way the mark MUST NOT outlive the plan, so the next cycle re-tests the route |
| the settlement-stall watchdog disarmed by a read fault (`ALC-40`) | `automation_blocked {cycle_failed}` for that cycle |

**ALC-49** The light probe runs **once** per federation per cycle (`ALC-38` step 8): one
threshold read, one pass over the vetted list for `gateway_available` and one read of the
shutdown signals per federation, whose facts planning, designation and the deadlines all
reuse. Only balances are re-read before commit (`ALC-53`), because commit requires them fresh
(`OPS-11`); a second light probe of the same federation in the same cycle is not permitted. The
`routing_info` reads of route pricing (`ALC-13`), the preflight (`ALC-32`) and the active
probe (`ALC-27`) are not light probes and are bounded by their own budgets.

**ALC-51** The `<reason>` component of the `refuse:` and `conflict-suppressed:` key shapes in
`STO-6` is the **tag** of the `ReasonCode` (`DOM-11`); this rule owns that mapping, and the wire
`reason` field (`API-12`, `API-15`) carries the same tag. The id placeholders' encoding is
`STO-6`'s. The key text is the prefix and its components joined by `:` with no padding:

| `ReasonCode` | tag |
|---|---|
| `SpendingBelowTarget` | `spending_below_target` |
| `StandbyBelowTarget` | `standby_below_target` |
| `ShutdownNotice` | `shutdown_notice` |
| `Unhealthy` | `unhealthy` |
| `OverCap` | `over_cap` |
| `NotProbed` | `not_probed` |
| `LowReputation` | `low_reputation` |
| `UneconomicRoute` | `uneconomic_route` |
| `UserInitiated` | `user_initiated` |
| `StandingInstruction` | `standing_instruction` |
| `ActiveProbe` | `active_probe` |

The refusal key omits the diagnostics on purpose: re-ticks of one `(fed, reason, occurrence)`
dedup to one row (`ALC-34`).

**ALC-52** Probe scheduling, evaluated once for admission (step 12) and once for the deadlines
(step 14) of `ALC-38`:

- Candidates: the probe-gated members (`ALC-37`), in ascending id order. The source is the
  in-flight session's `from` when one exists; else the designated spending federation (the
  candidate itself is skipped); with no spending federation a fresh candidate has no source and
  is neither admitted nor given a deadline (retained sessions keep theirs).
- `verdict` per `ALC-25` for `(candidate, source, now)`. `last_invocation` = the newest
  `max(created_at, updated_at)` over agent `Probe` rows with reason `ActiveProbe` for
  `(candidate, source)`, read with `horizon = max(7 d, retry_backoff)`: a ledger row is dropped
  when **both** its `created_at_ms` and `updated_at_ms` are below `now − horizon`, except a
  non-terminal `Probe` row with `cost_msat: None`, which is kept regardless of age (the budget
  reconstruction reads the same rows and fails `Permanent` on any undecodable row of its own
  class, `STO-22`). `base` = `None` for `NeverProbed`; the pass-expiry anchor (the oldest
  qualifying success whose expiry would break `Passed`) for `Passed`; else the newest
  same-source attempt's `at_ms`.
- `due`, with `build = max(min_interval, ceil(min_span / max(min_successes − 1, 1)))`,
  `refresh = min(probe_refresh_lead, ttl / 2)`, and `floor(t) = max(t, last_invocation +
  retry_backoff)` when a last invocation exists:

| Verdict | `due` |
|---|---|
| `NeverProbed` | `last_invocation + retry_backoff`, else `now` |
| `Insufficient`, `Expired` | `floor((base ∨ now) + build)` |
| `Failed`, `FailedSinceLastPass` | `floor((base ∨ now) + retry_backoff)` |
| `Passed` | `floor((base ∨ last_invocation ∨ now) + ttl − refresh)` |

  A retained session that has already journaled leg IN is due `now`.
- Admission order: retained sessions first (stable sort), each as a resume of its nonce; a
  fresh candidate needs `due ≤ now`, the budget pre-filter (`ALC-26`; a miss writes the skip
  row), an open candidate with a sampled baseline, and a current policy snapshot (`ALC-41`). If
  **any** retained session is admitted this cycle only the retained group is admitted and
  fresh probes are deferred.
- Deadlines: for every candidate with a source and not owned by a live probe drive, `wake =
  due` for a retained session; else `max(due, budget reset | now + min_interval when the budget
  is exhausted)`; then `max(wake, now + retry_backoff)` if admission refused this candidate this
  cycle, else `max(wake, now + min_interval)` if fresh probes were deferred.

**ALC-53** Commit's per-decision admission, after the whole-batch guards (`OPS-11`: `ALC-41`'s
policy generation, then the world generation, the plan authority, the balance authority, and a
single-occurrence check, each refusing the batch), in emission order, skipping advisory
decisions, each drop writing a `tick-drop` row (`ALC-34`) unless noted:

1. the destination has no fresh balance → `conflict`;
2. the balance facts of a federation the action touches changed since planning → `conflict`;
3. the key already maps to a `Done`/`Awaiting`/`Failed` intent → `conflict` (`OPS-8`); a
   journal read error fails the batch;
4. a goal blocker against a fresh scan of the live intents, folded forward per admitted
   decision → `conflict`, the row marked `conflict_suppressed` (`ALC-30`);
5. a goal admitted after the plan's eligibility snapshot → `conflict`, the row marked
   `conflict_suppressed`;
6. for a **new** funding `Move`: `amount > funding_shortfall(target, fresh destination
   balance, target_credit(to), 0)` with `target` chosen by the decision's reason → `conflict`
   ("replan"); a missing fresh balance here refuses with **no** row;
7. the admission of `OPS-6`/`OPS-7` under the allocator projection (`ALC-35`); on success the
   goal is held against the rest of the batch and, for a new intent, its reservation folded
   into the batch's projection; a refusal is a per-decision drop, any other error counts as
   failed and becomes the tick's error after the batch completes.

The advisory refusal rows are written after the loop; the tick row terminalizes when every
accepted driver finishes, else immediately. `CNF-13` demonstrates the whole path from probe to
a performed standby move.
