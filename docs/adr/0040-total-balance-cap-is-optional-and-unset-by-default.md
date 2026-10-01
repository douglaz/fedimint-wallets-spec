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
unset the wallet has no aggregate limit, exactly as today. When it is set, the admission
arithmetic gains one check for `Receive` and `DirectInflow`: the wallet's **aggregate**, plus the
request's amount, MUST NOT exceed `total_cap`, else the request is refused `over_cap` like a
per-federation over-cap, with the same re-checks at retry and perform time (`OPS-7`, `OPS-45`).
The aggregate counts every sat exactly once: the balances of the joined federations, plus the
inbound reservations of non-terminal `Receive` and `DirectInflow` intents (money arriving from
outside), plus, for a non-terminal `Move` or `Evacuate`, its amount at the destination only once
its send has left the source — its move record's phase is `Sending` or later — because before
that the same sats are still in the source's balance. A move whose record is not trusted
(`OPS-9`) counts at the destination as well: an over-count refuses an inflow, which is the safe
side. `OPS-9`'s strict projection cannot be summed as it stands, since it reserves a pending
move's amount at the destination while the source still holds it. Moves, evacuations and pays
never trip the cap: they do not raise the total. Lowering the cap below the current total refuses new inflows and touches
nothing already held. A receive retrying its claim (`ADR-0037`) holds its inbound reservation and
counts. The aggregate shares the per-federation check's window (`OPS-7`): an inflow credited
to a balance before its intent's terminal write lands is counted twice until that write
lands. That over-count refuses an inflow for that window and never admits one past the cap;
removing it would need credited evidence the reservation projection (`OPS-9`) does not carry,
for this check and the per-federation one alike.

**Why.** An operator — the pilot today, any cautious deployment later — gets the ceiling it
already keeps by habit as a rule the wallet enforces, and a user who wants a hard "spending
amounts only" limit can set one; a wallet that wants neither pays nothing. A default value would
have refused receives for every user whose balance grew past an amount nobody chose for them.

**Rejected.** A cap on by default (a value of two federations' worth was proposed): it refuses
receives no user asked to limit. No cap at all: leaves the pilot's ceiling as a habit the
software cannot hold. Capping the allocator's moves too: they cannot raise the total.

**Consequences.** Chapter 11's question 2 moves to *Answered* with this ADR. `OPS-7` owns the
check; `DOM-15`, `STO-13` (the field, unset in the seeded row), `STO-30` (decodes when absent as
unset, with its counts and `CNF-18`), `API-20`, `API-27` and `CNF-26` gain the parameter and their
parameter counts move from twenty-eight to twenty-nine; the policy validity rule (`spec-pe4`)
says a set value is positive; `ALC-9`'s and `SEC-9`'s sentences that call the question open cite
this ADR instead; a scenario demonstrates a receive refused at the cap and a move unaffected.
