---
status: accepted
---
# The wallet's total balance cap is an optional Policy field, unset by default

Chapter 11's question 2 asked whether the wallet's total balance is capped. Each federation is
capped by `per_fed_cap` (`ADR-0018`, enforced by `OPS-7`), so the total a policy permits is that
cap times the joined federations, and it rises with every join. The allocator moves balance
between federations and never raises the total (`ALC-9`); only the inflows a user initiates —
`receive` and `direct-inflow` — do. `ADR-0026` kept the pilot under a "willing-to-lose" ceiling as
an operator practice, not a wallet rule. Decided on 2026-10-01.

**Decided.** `Policy` gains `total_cap`, an optional amount, **unset by default**. While it is
unset the wallet has no aggregate limit, exactly as today. When it is set, admitting a `Receive`
or a `DirectInflow` — fresh, on retry, and again at perform time, like the per-federation check
(`OPS-7`, `OPS-45`) — gains one check: the wallet's **aggregate** plus the request's amount MUST
NOT exceed `total_cap`, else the request is refused `over_cap`. Moves, evacuations and pays never
trip the cap: they do not raise the total. Recovery from the seed (`FMI-31`) is never refused by
it: recovery rebuilds money the seed already owned, and `OPS-7` admits it without arithmetic; a
recovered total above the cap refuses new inflows like any total above it. While a recovery is in progress
(a non-terminal `Recover` intent), the balance it will add is unknown, so the check fails closed:
every inflow is refused as a transient refusal until the recovery commits or fails. Lowering the cap
below the current total refuses new inflows and touches nothing already held. A claim attempt on
a receive already admitted (`ADR-0037`) issues no new funding, so neither pre-fund admission
nor this check runs on it.

The aggregate is the check's account of what the wallet holds or may still come to hold through
the operations it has admitted, and it must keep three properties; the arithmetic that keeps them is `OPS-7`'s, not this ADR's:

- **Every sat at least once, and once where it can be.** Money in flight is counted where it can
  land, exactly once except for the brief over-count the third property allows: an inflow
  arriving from outside, an internal move or evacuation that has left its source, and a pay
  whose outgoing contract may still be refunded. A pay that ended in `FMI-37`'s ambiguous send
  `Failure` no longer counts (decided 2026-10-02): nothing in the set ever resolves it, so
  counting it would hold that room forever, and the residual — a rare late refund carrying the
  total above the cap — is accepted. The request being admitted counts once — its
  own reservation, on a retry or at perform time, is not added again.
- **Fail closed.** Any membership, balance, registry row, move record or projection the check
  cannot read or classify refuses the inflow as a transient refusal — retryable, nothing minted —
  and is never left out of the sum; `OPS-7` names the inputs and the refusal. Where a move's
  state is ambiguous, the check counts it on the side that refuses.
- **Over-counts only refuse.** Where the projection briefly counts money twice — an inflow
  credited before its intent's terminal write, as the per-federation check already does — the
  effect is a refused inflow, never an inflow admitted past the cap.

**Why.** An operator — the pilot today, any cautious deployment later — gets the ceiling it
already keeps by habit as a rule the wallet enforces, and a user who wants a hard "spending
amounts only" limit can set one; a wallet that wants neither pays nothing. A default value would
have refused receives for every user whose balance grew past an amount nobody chose for them.

**Rejected.** A cap on by default (a value of two federations' worth was proposed): it refuses
receives no user asked to limit. No cap at all: leaves the pilot's ceiling as a habit the
software cannot hold. Capping the allocator's moves too: they cannot raise the total.

**Consequences.** Chapter 11's question 2 moves to *Answered* with this ADR. `OPS-7` owns the
check; `DOM-15`, `STO-13` (the field, unset in the seeded row), `STO-30` (decodes when absent as
unset, with its counts and `CNF-18`), `API-20`, `API-27` and `CNF-26` gain the parameter, and every
count of the Policy parameters moves with it; ALC-54, the policy validity rule and the next free
ALC identifier, says a set value is positive; `ALC-9`'s and `SEC-9`'s sentences that called the
question open cite this ADR; CNF-57, the next free CNF identifier after CNF-56, demonstrates a
receive refused at the cap and a move unaffected.
