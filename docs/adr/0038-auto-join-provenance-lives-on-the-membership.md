---
status: accepted
---
# Auto-join provenance lives on the membership record; approval never frees auto-join budget

Auto-join is capped by `auto_join_lifetime_cap` (20) and `max_auto_joins_per_week` (5), and the
set never said what those counts count or where the wallet remembers it (`spec-60q`). The only
records were the auto-join's ledger row, which `OVR-4` makes best-effort, and the candidate row's
`AutoJoined` state, which `approve` overwrites to `UserApproved` — so each approval lowered the
count. The same gap left `ALC-28`'s repair step deciding on an "agent-created" fact no row
carried (`spec-nwm`). Three independent analyses (2026-09-29) agreed on what the caps are for and split on where the fact lives. Decided on 2026-09-29.

**What the caps are for.** A membership is permanent: there is no leave verb, nothing deletes a
registry row, every membership is opened at every start (`FMI-6`) and light-probed every cycle
(`ALC-15`), and an unopened one fences all planning (`ALC-46`). The lifetime cap bounds how many
memberships the agent ever created on its own; the weekly cap bounds how fast; the constant limit
of three bounds how many are unproven at once. Approval releases the probe gate and the
unproven slot and nothing else.

**Decided.**

- The registry row (`FederationInfo`, `STO-14`) gains `auto_joined: bool`, written with the row
  in the join's own transaction — `true` when auto-join (`ALC-29`) created the membership,
  `false` when a user `join` (`OPS-42`) or a recovery (`FMI-31`) did — and never changed by any
  later write. A row without it — one a build before the field wrote, after a rollback —
  decodes as `true` (`STO-30`): that only counts a user's join against the agent's budget,
  while `false` would let a membership the agent created escape both caps and `ALC-28`'s
  repair to `AutoJoined`.
- `lifetime` is the number of registry rows with `auto_joined` true; `weekly` is the number of
  those whose `joined_at` lies within the last seven days; `ALC-29` states the window's
  boundary and how an unreadable row counts. Neither count reads a candidate row or the ledger, so `approve`,
  a lost or repaired `join:` ledger row, and a reopen that writes no registry row change nothing.
- `ALC-28` step 2's "agent-created" is `auto_joined` true, and its second branch uses the same
  field: a joined federation with no candidate row gets `AutoJoined` when `auto_joined` is true
  and `UserApproved` when it is false.
- Losing the journal resets both counts, as it resets everything local; a federation recovered
  afterwards is user-owned (`FMI-31`, `ADR-0025`). 20, 5 and 3 are the inherited defaults, not
  re-derived here.

**Rejected.**

- Counting only agent-joined federations the user has not approved: approving them in batches
  gives unbounded growth at five a week, and it duplicates the limit of three.
- An `agent_joined_at_ms` field on the candidate row: candidate rows are rewritten by every
  discovery refresh and by `approve`, and recovery replaces an unreadable one, so the field needs
  a new never-clear rule to survive — the registry row needs none.
- Making the auto-join's ledger row mandatory in the join transaction: an exception to `OVR-4`'s
  "MUST NOT fail the work it records", and a money decision resting on classifying ledger
  strings (`STO-24` can soft-fail the row).
- A counter in `WatchState`: `STO-23` reseeds an absent `WatchState` from the ledger, silently
  resetting it.
- A separate append-only table of auto-join events: it duplicates the registry.

**Consequences.** `STO-14` owns the field and its write-once rule; `STO-5`'s `0x03` value,
`STO-30` (the decode-when-absent default and its counts, with `CNF-18`), `DOM-1` and `API-9`
(`FederationView`, and the `list-feds` line) gain it; `ALC-29` owns both counts; `ALC-28` step 2
cites the field; the sentences that made the ledger the count source (`STO-22`'s "the auto-join
caps", `STO-35`'s auto-join classifier, `OPS-42`'s "keeps a re-open out of the auto-join
counts") go. `joined_at` is unsigned Unix seconds, which `STO-14` states. Should a removal verb ever
exist, its decision must say whether removing an agent-created membership frees budget. Orphan
client partitions left by failed auto-joins (`FMI-8`, `FMI-35`) are not memberships and no cap
bounds them.
