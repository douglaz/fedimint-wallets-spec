---
status: accepted
---
# Reassembly that cannot rule out this attempt's send is unknown, never "no send"

`OPS-45` makes a `Move` and a `DirectInflow` reassemble their effects (`OPS-20`) before choosing
the pre-fund arithmetic: a `Move` with no recovered send operation id is checked as a fresh move.
At `OPS-28`'s fourth killpoint the send has committed but its operation id never reached the
cached move record, so reassembly must find it in the operation log. Two things made it find
nothing although the send committed: the required log read can fail, and `OPS-20` assigns that
no outcome; and the send's entry can carry metadata that does not decode, which `STO-33` warns
about and skips. Either way the fresh source check ran against a source the send had already
debited, refused `Permanent`, and marked `Failed` a move whose money was in flight. The client
resumes both legs on its own (`ADR-0022`), so the money still moves, but `OPS-10` lets a user
retry a `Failed` move unless its record is `Stranded`, and a retry mints a fresh invoice: the
transfer could happen twice. Decided on 2026-10-02.

**Decided.** `OPS-20` owns one rule for every caller that reassembles — perform (`OPS-45`), the
`DirectInflow` awaiter (`OPS-16`) and `Evacuate` (`OPS-19`):

- A required operation-log read that fails makes the result **unknown**: the intent stays
  non-terminal (`Retryable`), keeps its reservation and funds nothing new.
- A `Move` whose reassembled record holds an invoice also looks on its source for a send of that
  invoice, as `OPS-17` does for a `Pay`. The protocol derives the send's operation id from the
  invoice (`FMI-17`), so a found send counts as a recovered send operation id however its
  metadata reads.
- An entry whose metadata does not decode, but whose `move_id` equals this attempt's correlation
  key, also makes the result unknown. Every other undecodable entry is still warned about and
  skipped (`STO-33`).

**Why.** A read error already means "retry later" everywhere else in the set; it was unstated
only here. The invoice lookup reuses a query the set already requires and adds evidence without
presuming any, so `OPS-45`'s rule for a move with no send stands. Bounding the corrupt-entry
case to this attempt stalls only the one move that cannot be told apart.

**Rejected.**

- Keep skipping every corrupt entry and treat only a failed read as unknown: a corrupt entry can
  still mark a sent move `Failed`, and a retry can then move the money twice.
- Treat any undecodable move entry in a scanned log as unknown: every `Move` reassembles before
  funding, so one old corrupt entry would stall new moves through that federation, and the set
  has no verb that ends a stuck intent.
- Record such a move as `Stranded`: that state is "a settled send with a preimage and an
  op-terminal non-claim on the receive" (`OPS-27`, as `OPS-40` quotes it), and here neither has
  been observed.
- Treat a cached invoice as proof that a send exists: it reopens `OPS-45`'s row for a move with
  no send, and the lookup gives the same protection without guessing.

**Consequences.** `OPS-20` gains the rule. `STO-33`'s warn-and-skip sentence cites it for an
entry whose `move_id` equals this attempt's key. `OPS-16`'s "require the receive operation id
(absent → `Permanent`)" applies only when reassembly is not unknown. `OPS-45` is unchanged.
`CNF-55` gains the cases: a failed log read, a send found by its invoice behind an undecodable
entry, and an undecodable entry for this attempt. `spec-dgj` carries the edits.
