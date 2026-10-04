---
status: accepted
---
# A rejected claim is retried by the wallet until the federation answers definitively

When a gateway funds an incoming contract, the wallet's claim transaction can fail: the
federation rejects it, or accepts it and then fails to issue the notes. The client SDK submits
the claim once and reports `Failure`; it does not retry, and a claim the client cannot build can
stop the client outright. A funded, unconsumed incoming contract has
no claim deadline — the federation checks expiry only when the contract is funded — so the money
is still recoverable. `FMI-41` required a retry "until the contract's expiry has passed", which
has no referent for a funded contract, and offered an explicit re-claim for the operator
(`spec-u3u`). Decided on 2026-09-27.

**Decided.** The wallet drives recovery itself. A receive whose claim failed does **not**
terminate: it stays non-terminal, keeps its inbound reservation, and each reconcile pass
re-submits the claim with backoff (the retry cadence is the reconcile cadence, `OPS-14`) until
one of the **definitive** answers arrives:

- **claimed** — the notes are issued; the receive is `Done` (a move's receive leg `Settled`);
- **not claimable** — the contract was consumed by another claimant; the receive terminates `Failed` with `FMI-37`'s `receive failed:`
  anchor and its evidence kept, and a move with a settled send becomes `Stranded`;
- **uneconomical** — the claim's federation fee is at least the contract's amount; the receive
  terminates `Failed` with that reason, without stopping the client.

A transient failure — the federation unreachable, a rejected claim transaction, a timeout — is
never definitive. A receive whose claim is being retried is a known state, not a stall: it is
outside the settlement-stall watchdog's count (`ALC-40`), so a federation that keeps rejecting
claims cannot make the daemon exit and crash-loop, and it holds no slot of the external driver
cap (`OPS-6`) between attempts; each attempt is one perform under the perform timeout (`OPS-15`). The explicit re-claim (`API-42`) stays as the operator's manual trigger for the
same work and answers the same three outcomes plus a transient one and an issuance-pending one; it is
no longer the only
recovery path. A contract **this wallet** consumed whose note issuance failed is reported as
not claimable by the federation, but that is not definitive for the wallet: its notes may still
be issued from the operation's issuance evidence, never by a second claim. The receive stays
non-terminal, keeping its reservation, until its notes are issued (`Done`), so no inflow is
admitted into room those notes will fill. Nothing ends the wait short of that — no timeout, no
attempt count, no failed retrieval — because nothing the wallet observes shows that the notes can
never be issued (decided 2026-10-02). "This wallet consumed it" is the wallet's own evidence, not the federation's answer: its
issuance evidence holds an accepted claim transaction for the contract. While its issuance is pending, the receive has the same
standing as a retrying claim: outside `ALC-40`'s count and holding no `OPS-6` driver-cap slot
between attempts.

**Why.** A transient federation hiccup should not turn into operator work, and a user's
already-settled payment should not wait on someone running a command (`Incoming contract`: "A
delayed app open does NOT forfeit an already-settled payment"). Keeping the receive open also
keeps its reservation, so the per-federation cap still accounts for money that is on its way.

**Rejected.** A fixed number of automatic attempts followed by `Failed`, with `reclaim` as the
only recovery afterwards: it still hands transient failures to the operator after an arbitrary
count. No automatic retry at all: every transient failure becomes operator work. Giving up on
pending issuance when the client reports a final issuance failure: notes issued afterwards would
land in room already admitted to another inflow. Keeping a never-funded `Expired` receive
eligible for `reclaim` with an outcome of its own: it adds an exit code and a journaled attempt
that tries nothing, on every call.

**Consequences.** `FMI-41` owns the rule (the retry, the three definitive outcomes, the
transient class, the backoff bound as an engineering value) and loses the expiry clause.
`FMI-37`'s receive row, `OPS-16`'s receive map, `OPS-27`'s move mapping (a move strands only on
a definitive non-claim), `ALC-40`'s count, `OPS-6`'s driver cap and `HST-32` align. `API-42`
gains a transient answer and an issuance-pending answer for a contract this wallet consumed
whose issuance is unresolved (never `not_claimable`), and its precondition becomes an explicit
list (decided 2026-10-02): a receive or receive leg in claim retry or with issuance pending, a
receive `Failed` with `FMI-37`'s `receive failed:` anchor, the receive leg of a `Stranded` move,
and a receive whose contract this wallet claimed (a replay answers `claimed`). A receive that
ended `Expired` was never funded, so nothing is owed: it is not eligible, and `reclaim` refuses
it `422` (`API-6`) with a fixed `API-36` message, attempting and journaling nothing. `CNF-26`
gains the precondition and an exit code for each outcome. A new prohibition, DEF-26 (the next
free DEF identifier), says an uneconomical claim ends in a state and never stops the client. The
client SDK has no re-claim entry point, so an implementation provides one.
