# 05 — Persistence

What a compliant wallet writes to its durable stores and what it MUST be able to read back: the
two stores, the key layout of the journal, every persisted row field by field, the properties
every write MUST have, the ledger's write discipline, and the compatibility rules a type written
to a live store MUST obey. The shapes here are an **upgrade-in-place contract**: a build MUST
read every row the build before it wrote, and MUST write rows the build before it can still
read (`OVR-14`). How a store is opened, which task performs a write and what the writing routine
is called are the implementation's (`ADR-0032`); what is on disk after each write, and what a
reader may rely on, is not. A name in backticks is a persisted or serialized type or field
(`STO-29`) or a stored key prefix — it names a shape, never code. `Retryable` and `Permanent`
are the outcome classes of `03-operation-lifecycle.md`.

## Physical layout

**STO-1** A data directory holds **two** RocksDB stores, not one. `client.db` holds the
federation clients' partitions and the seed; `journal.db` holds the application journal. Inside
`journal.db` every journal key is prefixed `0x00`; inside `client.db` every client partition is
prefixed `0x01`; a key outside its store's prefix is not part of that store's contents. The two
MUST be separate stores; a single store carrying both prefixes does not satisfy this.

**STO-2** One process owns both stores. The lock is an advisory lock **file**, `client.db.lock`,
beside the `client.db` directory (not the store's own internal lock inside it), taken when
`client.db` is opened, and `client.db` MUST be opened before `journal.db`: it is the
exclusivity anchor. A second opener MUST block (a resident host) or refuse after a non-blocking
probe (the standalone process) — `HST-1`, `HST-9`, `SEC-23`. `init`, `mnemonic` and
`restore-mnemonic` (`HST-2`) therefore run only while no resident host holds the lock.

**STO-3** Client `i` lives at `[0x01] ++ u32_le(db_prefix)`, exactly five bytes; the fixed
length prevents prefix aliasing. The next prefix to allocate is `1 + max(the greatest
db_prefix in the registry, the greatest prefix found by a raw scan of client.db)`, where the
scan reads bytes `1..5` of every key under the `0x01` prefix as `u32_le` and ignores, with a
warning, any key shorter than five bytes; when the registry is empty **and** the scan finds
nothing the result is `0`; when the greater of the two is the largest representable `u32` the
allocation is an error, never a wrap. The raw scan closes the crash window in which a partition
was created and the registry never recorded it. An orphaned partition MUST never be reused
(`FMI-35`, `ADR-0025`). A failed join SHOULD remove its fresh partition.

**STO-4** The seed is twelve BIP-39 words stored as their **16-byte entropy** in the SDK's own
client-secret slot at the root of `client.db`: the `EncodedClientSecretKey` (client-store
prefix byte `0x28`), whose value is the fedimint consensus encoding of the entropy as a byte
vector, written once and never overwritten (`FMI-7`). The root secret every client partition
derives from is `FMI-7`'s derivation of those twelve words; a wallet that derives differently
recovers different ecash from the same words. There is no mnemonic file. It is plaintext
(`SEC-10`).

## Journal key layout

**STO-5** Every journal key is `[tag] ++ id_bytes`. Every value except the three flagged below
is a JSON envelope `{"version":1,"data":<T>}` (`version` is a `u8`; any other version decodes
as `Permanent`; the envelope itself tolerates unknown keys). `<T>` is the JSON form below, and
this rule is the single owner of that encoding for every stored type in `STO-29` and every wire DTO that embeds one of them (`API-…`
rules cite it rather than restate it):

| Shape | JSON form |
|---|---|
| struct | object; keys are the persisted field names verbatim (`snake_case`), never renamed |
| enum, unit variant (`IntentStatus`, `OperationStatus`, `MovePhase`, `ReasonCode`, `CandidateState`, `DiscoverySource`, `Actor`'s `User`, `SourceStatus`'s `Ok`, `StructuralOutcome`'s `Passed`) | the variant name as a JSON string, PascalCase verbatim: `"Pending"`, `"UserInitiated"`, `"User"` |
| enum, struct variant (`Action`, `OperationKind`, `Actor`'s `Agent`) | **externally tagged**: `{"Move":{"from":…,"to":…}}`, `{"Agent":{"occurrence":7}}` |
| enum, newtype variant (`SourceStatus`'s `Failed(String)`, `StructuralOutcome`'s `Rejected(String)`) | `{"Failed":"…"}`, `{"Rejected":"…"}` |
| newtype over a scalar (`Msat`, `Occurrence` over `u64`; `IdempotencyKey`, `GatewayUrl`, `Invoice` over `String`) | **transparent**: the bare inner value (`123`, `"move:…"`) |
| 32-byte identifier (`FederationId`, `OperationId`, `Preimage`, `payment_hash`) | a JSON **array of 32 integers** `[170,170,…]`, never hex, never base64 |
| `u64` / `u32` / `u16` / `bool` | JSON number / boolean; a `u64` is written and read at full precision (values above 2⁵³ are legal) |
| optional field (`T?`) | `null` or the value; the key is always **present** (`"gateway":null`). A field `STO-30` lists additionally *decodes* an absent key (a row written by an older build) as its stated default; the current build still writes the key |
| list | JSON array |
| `InviteCode` (only in `CandidateRecord.invite`) | the invite's `fed1…` string; an unparsable string is a `Permanent` decode failure |

No stored type departs from that table: a key is never renamed, a variant is always
externally tagged, a nested object is never flattened into its parent, and a key is never
omitted (`MoveMeta`, which rides the operation log rather than the journal, is the one
exception: `STO-33`). There are exactly thirteen tags:

| Tag | Key | Value |
|---|---|---|
| `0x01` | `++ utf8(idempotency_key)` | `Intent` |
| `0x02` | `++ utf8(key)` | `MoveRecord` |
| `0x03` | `++ FederationId[32]` | `FederationInfo {invite, db_prefix, joined_at (seconds)}` |
| `0x04` | `++ status_byte ++ utf8(key)` | **empty** — the pending index |
| `0x05` | `++ be64(seq)` (exactly 9 bytes) | `OperationRecord` — the ledger |
| `0x06` | `++ utf8(correlation_key)` | **raw `be64(seq)`** |
| `0x07` | (single key) | **raw `be64(next_seq)`** — the ledger counter |
| `0x08` | `++ FederationId[32]` | `ProbeRecord` |
| `0x09` | `++ FederationId[32]` | `CandidateRecord` |
| `0x0a` | (single key) | `WatchState` |
| `0x0b` | (single key) | `Policy` |
| `0x0c` | `++ utf8(old_key)` | `EvacuationSupersessionRecord` |
| `0x0d` | `++ utf8(new_key)` | the old key: the ordinary envelope around a JSON string, `{"version":1,"data":"<old_key>"}` |

`status_byte`: Pending 0, Executing 1, Done 2, Awaiting 3, Failed 4. `be64` is the big-endian
eight-byte encoding of a `u64`; a `0x06`/`0x07` value that is not exactly eight bytes is a
`Permanent` "corrupt ledger seq index"/"ledger counter is corrupt" error.

**STO-6** Correlation and idempotency keys are strings with these shapes, and repair
(`STO-24`) classifies rows by their prefix:

| Shape | Producer |
|---|---|
| `move:<from>:<to>:<occurrence>` | allocator |
| `move:<from>:<to>:<amount>:<fee_cap>:<occurrence>` | user move, **and both active-probe legs**, whose `<occurrence>` is derived from the session nonce (below) |
| `evac:<from>:<to>:<occurrence>` | allocator, scheduler |
| `refuse:<reason>:<fed>:<occurrence>` | allocator refusal |
| `conflict-suppressed:<candidate-key>:<reason>` | allocator, suppressed candidate |
| `tick-drop:<occurrence>:<decision-key>` | commit-time drop (`ALC-34`; row shape `STO-15`) |
| `pay:<payment_hash>` | user pay |
| `recv:<to>:<amount>:<nonce>` | user receive |
| `dinflow:<to>:<amount>:<nonce>` | direct inflow |
| `join:<fed>:<sha256(invite)>` | intent-backed join |
| `join:<fed>:<nonce>` | agent auto-join ledger row |
| `recover:<fed>:<sha256(invite)>` | recovery |
| `tick:<occurrence>:<nonce>` | one per tick invocation |
| `probe:<fed>:<nonce>` | active probe umbrella row |
| `discover:<label>[:<index>]:<nonce>`, `autojoin:<nonce>`, `approve:<fed>:<nonce>` | discovery |
| `watch-probe-skip:<candidate>:<spending>:<amount>:<bucket>` | scheduler (repair classifies it as a discovery row, `STO-24`) |
| `reclaim:<nonce>:<key>` | one per re-claim attempt (`API-42`; row shape `STO-15`), `<key>` the reclaimed operation's key verbatim |

Placeholder encodings, all fixed: `<from>`, `<to>`, `<fed>`, `<candidate>`, `<spending>` are
the 64-char lowercase hex of the 32-byte `FederationId`; `<amount>` and `<fee_cap>` are
decimal millisatoshis and `<bucket>` is decimal milliseconds; `<occurrence>` is the decimal
`u64`; `<payment_hash>` and `<sha256(invite)>` are 64-char lowercase hex, the latter of SHA-256
over the invite string's UTF-8 bytes; `<index>` is a decimal source index; `<label>` is the
discovery source's label; `<reason>` is the `ReasonCode` **tag** owned by `ALC-51` (the
snake_case form, e.g. `spending_below_target`), not the PascalCase JSON value of the stored
`reason` field; `<bucket>` in `watch-probe-skip:` is the probe budget's reset time in ms when
one is known, else `floor(now_ms / 604_800_000) × 604_800_000` (the rolling 7-day window of
`ALC-26`), so repeated skips of one `(candidate, spending, amount)` within a window dedup to
one row. The user-move shape doubles as the active-probe leg key (`ALC-27`).

A **generated** `<nonce>` is **32 lowercase hex characters** encoding 16 bytes drawn from a
cryptographically secure random source. A **caller-supplied** nonce on `recv:`/`dinflow:` keys
(`POST /v1/receive`, `/v1/direct-inflow`, and the standalone `receive`/`direct-inflow` verbs)
is any non-empty string of URL-unreserved bytes (`API-36`) embedded verbatim — `foo` is a
valid nonce, and the CLI's `direct-inflow` default is the literal `0` (`API-41`) — so a parser
of stored keys MUST NOT assume the fixed width there. A `ProbeSession.nonce` (`STO-26`) is the
generated shape, and both probe legs' `move:` keys embed the first sixteen hex characters of
that nonce read as a big-endian `u64`, so the leg keys are reconstructible from the session
alone (`DOM-16`). Probe legs are **not** namespaced away from user moves: a user-supplied
occurrence is any `u64`, so a user move with the same endpoints, amount and cap and an
occurrence equal to a nonce head resolves to that leg's key and is refused (`DOM-21`). The
separation is probabilistic (a random 64-bit head against the small occurrences users and the
scheduler actually supply), not excluded; the key shape is not namespaced and does not move.

`pay:` keys carry the payment hash and no nonce, so paying the same invoice twice attaches to
one operation (`OPS-8`). The key an intent writes into the **operation log** differs from its
journal key after a manual retry: `STO-34`.

## Transaction model

**STO-7** Every journal write MUST be atomic: a write that touches several keys — an intent and
its index entry, an intent and its ledger row, a probe session and its appended attempt —
commits wholly or not at all, and no reader ever observes part of one. A read MUST observe one
consistent snapshot of the store. A plain (unconditional) write that loses a write conflict
reports `Retryable` to its caller and is not retried inside the store. A row that fails to
decode is `Permanent`; a storage fault is `Retryable`.

**STO-8** A compare-and-swap write — one whose guard is read inside its own transaction — MUST
be retried on a write conflict until it commits or its guard fails, and MUST NOT surface the
conflict to its caller (`DEF-14`). The timestamp such a write stamps MUST be taken once, before
its first attempt, so every retry writes the same one. Six writes are of this kind: the
conditional status transition (the claim of `OPS-43` and every other fenced status write), the
retryable reset (`OPS-4`), the fenced raw-terminal write (`OPS-46`), the marker clear
(`OPS-31`), the supersession exchange (`OPS-30`), and the recovery commit (`FMI-31`).

**STO-9** The `Intent` row (`0x01`), field by field (`?` marks an optional field; per `STO-5`
every key is present, `null` when `None`, except the one field `STO-30` lists):

| Field | Type | Source |
|---|---|---|
| `idempotency_key` | `IdempotencyKey` | must equal the row key or the read is `Permanent` |
| `attempt` | `u32` | `0` on first admission; `+1` per retry (`OPS-10`) |
| `action` | `Action` (`DOM-7`) | |
| `max_fee` | `Msat?` | the action's `fee_cap` for `DirectInflow/Move/Evacuate/Pay/Receive`, `None` for `Join/Recover` |
| `status` | `IntentStatus` | |
| `reason` | `ReasonCode` | the decision's reason; user verbs `UserInitiated` |
| `actor` | `Actor` | |
| `created_at_ms` | `u64` | unix millis at admission; becomes the ledger row's `created_at_ms` |
| `operation_id` | `OperationId?` | raw `Pay`/`Receive` artifact |
| `invoice` | `Invoice?` | raw `Receive` artifact |
| `evacuation_refusal` | `EvacuationRefusalEvidence?` | decodes when absent as `None` (`STO-30`); `{cap_components: EvacFeeCap {base_msat, bps}, requested_net: Msat, source_spendable: Msat, low: EvacuationQuoteSample, high: EvacuationQuoteSample, diagnostic: String, measured_at_ms: u64}` with `EvacuationQuoteSample {delivered_net: Msat, total_fee: Msat, fee_cap: Msat}` (`DOM-19`) |

Every write to an intent MUST name the attempt it expects. An unconditional write — the admission
insert, a plain status write, the retryable reset — whose stored attempt differs is a
`Permanent` error; a fenced write — a conditional status transition, a move-record write, the
recovery commit, every write `OPS-13` calls attempt-fenced — writes nothing and reports that
it did not apply. Every status write enforces the transition table `OPS-2` owns. `Failed→Pending`
happens only through the retry write (`OPS-10`), which requires the caller's copy of the row to
be `Pending` at exactly `attempt + 1`, refuses a superseded parent (a `0x0c` row under the key,
`STO-25`), and in one transaction moves the `0x04` entry from `Failed` to `Pending`, deletes the
`0x02` move row, appends a **fresh** ledger row and repoints `0x06` to it (`STO-20`), so a
crashed attempt and its retry are two truthful rows. `OPS-31` owns which writes touch `evacuation_refusal`; on disk, the `Pending→Executing` claim
clears it to `None` (a fresh claim consumes the planning handoff), the retryable reset —
which requires `Executing` and writes `Pending` — sets it to exactly the evidence the caller
supplies, `None` clearing it, and the deliberate clear blanks it and nothing else.

**STO-10** The pending index `0x04` holds `Pending`, `Executing`, `Awaiting` and `Failed`
intents; **`Done` is never indexed**, which is what makes finished work unscannable. Index and
intent row move in one transaction. The scan of re-drivable intents returns `[Pending,
Executing]` — it **includes `Executing`** — and tolerates a corrupt entry; the scan of awaiting
intents returns `[Awaiting]` and is never re-driven (`OPS-36`); the reservation scan returns
`[Pending, Executing, Awaiting]` and **fails closed** on any corrupt entry, so admission stops
rather than under-reserve (`OPS-9`).

**STO-11** `MoveRecord` (`0x02`) is the **partially** rebuildable cache of a two-leg operation
(`DOM-10`). Its fields:

| Field | Type | Note |
|---|---|---|
| `key` | `IdempotencyKey` | must equal the row key; a write whose `key` differs from the row key is `Permanent` |
| `from` | `FederationId?` | `None` for a receive-only `DirectInflow` |
| `to` | `FederationId` | |
| `amount` | `Msat` | the net the receive was committed at (`OPS-24`'s `net`; `STO-17`) |
| `fee_cap` | `Msat` | the cap actually enforced; for an `Evacuate` recomputed from `fee_cap_components` at the sized net |
| `gateway` | `GatewayUrl` | **required**: the one gateway of a shared route, or the receive-leg (destination) gateway of a hop; recorded when the record is created, replayed once the move is committed (`OPS-20`) |
| `send_required` | `bool` | `true` for `Move`/`Evacuate`, `false` for `DirectInflow` |
| `invoice` | `Invoice?` | |
| `recv_op` | `OperationId?` | |
| `send_op` | `OperationId?` | |
| `phase` | `MovePhase` | `Created, Invoiced, Sending, Settled, Refunded, Failed, Stranded` |
| `outcome` | `String?` | terminal diagnostic; the ledger's `error` fallback (`STO-16`) |
| `preimage` | `Preimage?` | |
| `receive_fee_quoted` | `Msat?` | |
| `send_fee_quoted` | `Msat?` | |
| `send_gateway` | `GatewayUrl?` | on a **hop** (`OVR-13`), the source-leg gateway the route was committed with; `None` on a shared route; decodes when absent as `None` (`STO-30`). `ADR-0029`: "a hop row shows both gateways" |

From the operation log (`STO-33`) the wallet can rebuild `recv_op`, `send_op`, `invoice`,
`amount`, `fee_cap`, `gateway` and `send_gateway` (`OPS-20`); the terminal `phase`, `preimage`,
`outcome`, and both quoted fees survive only in this row. A move has an **artifact** exactly
when `invoice`, `recv_op` or `send_op` is `Some`. A move record of an intent-backed move MUST be
written only while the intent is at the expected attempt, non-terminal, and carries no
refusal marker; a write that observes otherwise writes nothing and reports that it did not
apply. A record write MUST NOT leave behind a record that belongs to a retired attempt or to
an intent that became terminal or marked while the record was being written; how a wallet
whose record write can race a status write keeps that invariant is its own.

**STO-12** `WatchState` (`0x0a`): `occurrence`, `last_discover_ms`, `discover_cursor?`,
`discover_backlog`, `discover_rotation` (decodes when absent as `0`, the value a fresh `WatchState` starts at; `STO-30`). A cycle's
occurrence is allocated by a checked `+1` on the stored value, which fails only when that value
is already the largest representable `u64`, so it can write that value once; an observation
(a standalone tick recording its operator-supplied occurrence as the floor, `DOM-16`) writes
`max(stored, observed)` and rejects an **input** equal to the largest representable value
before writing. That value is the fail-closed value (`ALC-33`).

**STO-13** `Policy` (`0x0b`): twenty-eight fields (`API-27`), seeded insert-if-absent at `init`
and again at every resident-host start (`HST-4`, `HST-6`), which then validates the stored row
and refuses to start on an invalid one. A policy write is a plain overwrite of the row; **the
store does not validate** — validation is the admission surface's (`DOM-15`), and the HTTP
handler rejects unknown keys (`API-20`). The stored type is permissive (`STO-31`);
`max_fee_bps_of_move`, `evac_fee_base_msat` and `evac_fee_bps` decode when absent as `300`,
`Msat(200_000)` and `300` (`STO-30`), because rows written before them exist. The seeded row
is: `per_fed_cap 1_500_000_000`, `spending_target 500_000_000`, `standby_target 150_000_000`,
`max_fee 200_000` (all msat), the three defaults above, `spending_fed`/`standby_fed` `null`,
`probe_min_span_secs 86_400`, `probe_min_successes 3`, `probe_ttl_secs 604_800`,
`probe_amount 20_000`, `max_probe_attempts_per_week 10`, `max_probe_spend_per_week 500_000`,
`base_interval_secs 600`, `min_interval_secs 30`, `evacuation_lead_secs 3_600`,
`discover_every_secs 21_600`, `probe_retry_backoff_secs 3_600`, `probe_refresh_lead_secs
43_200`, `max_auto_joins_per_week 5`, `auto_join_lifetime_cap 20`, `max_candidates_per_pass
256`, `per_preview_timeout_secs 20`, `discover_pass_deadline_secs 60`, `auto_join false`,
`require_mainnet true`. Field types: every `*_msat`/`_cap`/`_target`/`_amount`/`_spend_*`/
`max_fee` is `Msat`; `max_fee_bps_of_move` and `evac_fee_bps` are `u16`; the two federation fields are
`FederationId?`; `probe_min_successes`, `max_probe_attempts_per_week`,
`max_auto_joins_per_week`, `auto_join_lifetime_cap`, `max_candidates_per_pass` are `u32`; every
`*_secs` is `u64`; the two flags are `bool`.

**STO-14** The federation registry (`0x03`) is written by a plain overwrite after the client
partition exists and before the client is made live (`FMI-8`). A read of one federation fails
closed on a corrupt row; the listing skips a malformed key or undecodable value, reports the
number skipped, and warns. That count is what `ALC-46`'s three planning surfaces refuse a partial world on; explicit
user and admin verbs keep the poison-tolerant list.

## The operation ledger

**STO-15** `OperationRecord` (`0x05`): `seq: u64, correlation_key: IdempotencyKey, kind:
OperationKind, actor: Actor, reason: ReasonCode, status: OperationStatus ∈ {Started, Awaiting,
Succeeded, Failed}, created_at_ms: u64, updated_at_ms: u64, fees: FeeBreakdown {fee_cap: Msat?,
receive_fee: Msat?, send_fee_quoted: Msat?}, error: String?, repaired: bool` (`repaired`
decodes when absent as `false`, `STO-30`). `reason` is mandatory and stored as the PascalCase
variant (`"UserInitiated"` on user verbs; the `user_initiated` spelling is the key tag of
`STO-6`). `Actor` is `"User"` or `{"Agent":{"occurrence":<u64>}}`. `OperationKind` has
thirteen externally-tagged variants:

| Variant | Fields (in order) |
|---|---|
| `Join` | `fed: FederationId` |
| `Recover` | `fed: FederationId` |
| `Receive` | `fed: FederationId, amount_invoiced: Msat` (gross), `op_id: OperationId?, gateway: GatewayUrl?` |
| `Pay` | `fed: FederationId, invoice_amount: Msat?, payment_hash: [u8;32]?, op_id: OperationId?, gateway: GatewayUrl?` |
| `DirectInflow` | `to: FederationId, amount: Msat, recv_op: OperationId?, gateway: GatewayUrl?` |
| `Move` | `from: FederationId, to: FederationId, amount: Msat, send_op: OperationId?, recv_op: OperationId?, gateway: GatewayUrl?, evacuation: bool` (`true` for an `Action` `Evacuate`), `send_gateway: GatewayUrl?` (a hop's source-leg gateway, `None` on a shared route; decodes when absent as `None`, `STO-30`) |
| `Refusal` | `fed: FederationId, diagnostics: RefusalDiagnostics` (decodes when absent as all-`None` with `conflict_suppressed: false`, `STO-30`) |
| `Probe` | `fed: FederationId, from: FederationId, amount_msat: Msat, cost_msat: Msat?` |
| `Tick` | `occurrence: Occurrence, decisions: u32, performed: u32, failed: u32` |
| `Discover` | `source: DiscoverySource ∈ {Observer, Nostr, Manual}, status: SourceStatus ∈ {"Ok", {"Failed": String}}, found: u32, structurally_passed: u32, rejected: u32` |
| `AutoJoin` | `considered: u32, joined: u32, blocked_concurrent: u32, blocked_weekly: u32, blocked_lifetime: u32` |
| `Approve` | `fed: FederationId` |
| `Reclaim` | `fed: FederationId` (the federation holding the contract)`, target: IdempotencyKey` (the key of the operation whose contract is claimed)`, op_id: OperationId?` (its receive operation) |

An intent-backed row is seeded from its action: `Move`/`Evacuate → Move` (operation ids and
both gateways `None`, `evacuation` per variant), `DirectInflow → DirectInflow`, `Pay → Pay
{fed: from, invoice_amount: Some(amount), payment_hash: Some(hash), op_id: None, gateway}`,
`Receive → Receive {fed: to, amount_invoiced: amount, op_id: None, gateway}`, `Join/Recover →
{fed: federation}`, `RefuseInflow → Refusal`. A refusal row MUST carry the figures that
produced it in `diagnostics` (`DEF-2`): `RefusalDiagnostics {source: FederationId?, want:
Msat?, available: Msat?, source_spendable: Msat?, max_fee: Msat?, max_fee_bps: u16?, cap_room:
Msat?, amount: Msat?, conflict_suppressed: bool, min_move: Msat?}` (`max_fee_bps` and
`conflict_suppressed` decode when absent, `STO-30`). Refusal identity is `(fed, reason)`; the
diagnostics do not distinguish two refusals. A commit-time drop of an executable decision
(`ALC-34`) is also a `Refusal` row: keyed `tick-drop:<occurrence>:<decision-key>`, `fed` is
the decision's `Move.to` or `Evacuate.from` — the only two arms a stored row can take, since
the allocator emits no `DirectInflow`, `Join`, `Recover`, `Pay` or `Receive` (`ALC-4`) and a
refusal never reaches commit — `actor Agent{occurrence}`, `reason` = the dropped decision's
reason, **`status Succeeded`** (the drop itself succeeded; the money did not move), `fees`
default, `error = "commit-time admission refused <decision-key>: <message>"`, `repaired
false`, and `diagnostics` all-`None` except that a nonzero conflict-suppressed candidate records
`amount: Some(0)` and `conflict_suppressed: true`. It is create-if-absent (a re-drop of the
same key is a no-op).

A re-claim (`API-42`, `FMI-41`) writes one `Reclaim` row per attempt, keyed
`reclaim:<nonce>:<key>` (`STO-6`): `actor User`, `reason UserInitiated`, `fees` default,
`repaired false`; `status Succeeded` with `error` `None` on the outcome `claimed`, and `status
Failed` on `not_claimable` — the attempt claimed nothing — with an `error` that states why
(expired, or consumed by another claimant; the text is informative, `OPS-40`). It describes no
intent and is written best-effort (`OVR-4`); the reclaimed operation's own row is not touched.

**STO-16** Write discipline. A ledger row is created on first observation of its key; it is
updated only to advance status (rank `Started < Awaiting < terminal`) and to fill fields; a
terminal row accepts no further write **except** that a terminal row written by repair
(`repaired: true`) may be superseded exactly once by an authoritative write. **Nothing deletes
a `0x05`, `0x06` or `0x07` key.** Every intent status change MUST write its ledger row in the
same transaction — the admission insert, every plain and conditional status write, the
retryable reset, the recovery commit, the supersession exchange, the artifact and raw-terminal
writes — so ledger and journal cannot disagree about an intent-backed operation (`OVR-4`).

The **advance rule**, given the stored row, a target status, the clock, an optional enrichment
(operation ids, gateway, amount, hash, fees), an optional error, and the write's kind
(authoritative or repair), exactly: (1) a terminal stored row is left unchanged unless
`repaired` is set and the write is authoritative; (2) a non-terminal row is left unchanged when
`rank(target) < rank(stored status)`; (3) otherwise the copy gets `status = target`,
`updated_at_ms = now`, `repaired = (the write is a repair write && target is terminal)`; (4)
the enrichment fills the kind's operation ids, gateways, amount and hash only where the
incoming value is `Some` (a `None` never clobbers), and `fees` merge field-wise the same way
**except** when the enrichment is marked *definitive*, in which case `receive_fee` and
`send_fee_quoted` are replaced outright (a settlement that could not derive a fee clears a
stale estimate) while `fee_cap` still merges; (5) `error`: if the stored row was terminal (the
repaired supersession) or the status changes, `error` is set to **exactly** the incoming value
— `None` clears a prior diagnostic; on a same-status enrichment an incoming `Some` overwrites
and a `None` leaves the stored text. `seq`, `correlation_key`, `actor`, `reason`,
`created_at_ms` and the kind's identity fields never change.

The intent-backed write maps the intent status (`Pending|Executing → Started`, `Awaiting →
Awaiting`, `Done → Succeeded`, `Failed → Failed`), carries no enrichment (the row is refreshed
from the move record instead, `STO-17`), and carries an error only when the mapped status is
`Failed`: the caller's diagnostic if any, else `MoveRecord.outcome`, else `None`. A fresh
intent-backed row takes `created_at_ms` from `Intent.created_at_ms` (not the clock),
`updated_at_ms = now`, `fees.fee_cap = Intent.max_fee`, `repaired = false`. A
create-if-absent write (a row that describes no intent, and the first observation of any key)
never advances an existing row. An enrichment write (an operation id, fees or an error
supplied outside an intent status change: `OPS-17`, `OPS-46`) chooses its target status as: an
operation id newly supplied while the row is `Started` (or a repaired terminal) → `Awaiting`;
a repaired `Failed` with any enrichment → `Started`; a repaired terminal with no enrichment →
no write; otherwise the current status (pure enrichment).

**STO-17** On every intent-backed ledger write the row refreshes operation ids, gateways and
quoted fees from the `0x02` record, and — once a move artifact exists (invoice, receive
operation or send operation, `STO-11`) — refreshes **both** `amount` and `fee_cap` to the
net the receive was committed at and the cap enforced at that net (`DEF-4`). Refreshing one without the other is forbidden:
an auditor recomputing the cap from a planned amount would derive a number nobody enforced.
Precisely: on a `Move` kind `send_op`/`recv_op` are copied when `Some` on the record, `gateway`
is set to `Some(record.gateway)` unconditionally, `send_gateway` is set to
`record.send_gateway` unconditionally (so a hop row shows both gateways, `ADR-0029`), and
`amount`/`fees.fee_cap` are stamped only when the artifact exists; a `DirectInflow` kind is
treated identically — `recv_op` copied when `Some`, `gateway` set unconditionally,
`amount`/`fees.fee_cap` stamped once the artifact exists, so the `DEF-4` pairing holds there
too; on every kind `fees.receive_fee`/`fees.send_fee_quoted` are copied when `Some`. After
that, a `Pay`/`Receive` kind's `op_id` is set to `Intent.operation_id` whenever that is
`Some`. The record `OPS-24` writes for a receive refused after commit — phase `Failed`,
`recv_op` set, `amount` and `fee_cap` at the committed pair, no invoice — has an artifact, so
this rule stamps that row with the committed pair and names the orphan.

**STO-18** Sequence assignment is fenced without a ledger scan: before any fresh append the counter `0x07`
MUST equal `tail_seq + 1`, where the tail is the lexicographically greatest `0x05` key, which
MUST be a canonical nine-byte key whose embedded `seq` matches. Any disagreement is a
`Permanent` error that fences **every** fresh append, user and agent, with an operator message
to restore the stores from a snapshot (`STO-28`). An absent `0x07` reads as `0`; a nonzero counter over an empty ledger,
a tail key that is not exactly nine bytes, or a tail `seq` equal to the largest representable
`u64` are all the same fence. The first row of a fresh store is `seq 0`. The counter is
exhausted at the largest representable value.

**STO-19** History is read newest-first: a page of `limit` rows whose `seq < before_seq`, in
descending `seq`, and `before_seq` is exclusive (`API-10` owns the query parameters and the
cap on `limit`). An undecodable row MUST be skipped with a warning and no other signal — the
page is shorter, never an error (`STO-22`).

**STO-20** `0x06` maps a correlation key to exactly one current row. A retry appends a fresh row
and repoints the index, so older attempts' rows are reachable by `seq` only. A lookup by key
resolves through the index; a lookup by `seq` reads `0x05` directly.

**STO-21** On every fresh insert of an `Agent {occurrence}` row, and in the retry write
(`OPS-10`), the wallet MUST raise `WatchState.occurrence` to `max(current, occurrence)` **in
the same transaction**. User rows never touch `0x0a`. This is what keeps the checkpoint at or
above every Agent occurrence ever appended, whatever path admitted it (`DOM-16`).

**STO-22** An unreadable ledger row MUST NOT fence automation (`DEF-12`). Operational scans
(history, the re-drivable-intent scan, the failed-intent scan) skip and warn. The scans that
decide money — the probe budget, the auto-join caps, the reservation scan — fail closed on a
corrupt row, so the blast radius of one bad row is a disabled subsystem with an explicit error,
never a silent under-count and never a permanently stopped scheduler.

**STO-23** An absent `WatchState` is seeded from the ledger's highest `Agent` occurrence by one
scan of the ledger. Discovery cursor, backlog and rotation are not recoverable.

**STO-24** Ledger repair (`OPS-37`) scans `0x05` and repairs only these classes, each write
fenced on a re-read of `seq`, federation, role, operation id and status inside its own
transaction: `join:` rows are arbitrated per federation against the registry (present → the
already-succeeded attempt, else the newest within ±60 s of `joined_at`, else the newest,
soft-Succeeded; losers soft-Failed "superseded"; absent and older than one hour → soft-Failed
"not registered"); `pay:`/`recv:` rows are observed from the operation log by correlation key
(the operation whose metadata `correlation_key` equals the **attempt** correlation key of
`STO-34` — the backing intent's, which is the row's key only on attempt 0 and
`retry:<len>:<key>:<attempt>` after a manual retry; a raw row with no backing intent is matched
on the row's key), else by payment hash (a repair write with a dedup note; an in-flight or
failed original is never adopted for a later attempt), else after one hour soft-Failed "never
reached the federation"; `tick:` and discovery rows older than one hour → soft-Failed
"interrupted". The classes are decided by key prefix alone: `join:` → join; `tick:` → tick;
`discover:`, `autojoin:`, `approve:`, `watch-probe-skip:` → discovery; `pay:`, `recv:` → raw;
everything else (move-shaped intent rows, `recover:`, `refuse:`, `probe:`, `dinflow:`,
`reclaim:`, …) is never repaired. The verbatim strings repair writes, which `STO-35` freezes,
are:

| Written when | Stored `error` text |
|---|---|
| a join attempt loses the arbitration | `superseded by a later join attempt` |
| a join row's federation is absent from the registry after one hour | `join did not complete — federation not in the registry; re-run join` |
| join attempts overlap and the winner is uncertain | `overlapping attempts; correlation uncertain — membership itself is registry-proven` |
| a tick or discovery row is interrupted | `interrupted — no terminal report` |
| a raw row has no operation after one hour | `never reached the federation` |
| a raw row is matched by payment hash rather than by attempt | `correlated by payment hash to an existing payment of this invoice; attempt-level correlation uncertain (deduped retry or never-sent attempt); the matched operation is authoritative` |

When a note accompanies an operation's own terminal error the stored text is `"{note}
({err})"`. A raw terminal repair re-drives the intent to its terminal (`OPS-37`) except for the
never-reached case, which is recognised by `status == Failed && repaired && error == "never
reached the federation"` exactly.

**STO-25** Evacuation supersession writes two sidecars in the same transaction as the exchange:
`0x0c old_key → {old_key, old_attempt, new_key, new_attempt, old_occurrence, occurrence, source,
old_cap_components?, new_cap_components?, refusal, superseded_at_ms}` and `0x0d new_key →
old_key`. A superseded parent can never be retried; a child's namespace MUST be empty across
`0x01/0x02/0x06/0x0c/0x0d` and all five `0x04` status keys before creation; at most one live
Agent evacuation per source may exist at exchange time; the replay path validates that both
sidecars exist and agree before returning success without writing (`OPS-30`).

**STO-26** `ProbeRecord` (`0x08`): `{attempts: Vec<ProbeAttempt>, in_flight: ProbeSession?}`
(both keys always present). `ProbeAttempt` is `{at_ms: u64, ok: bool, from: FederationId,
amount_msat: u64, leg_fee_cap_msat: u64, error: String?}` (`DOM-13`). `attempts` is chronological append order and is pruned in two steps on
every outcome write — first keep every attempt with `now_ms − at_ms ≤ 604_800_000` (a
**constant** 7-day window, never `Policy.probe_ttl_secs`), the newest attempt, and per `from`
source the newest `ok` attempt and the newest **default-qualifying** attempt, where
default-qualifying means `ok && amount_msat ≥ 20_000 && leg_fee_cap_msat ≤ 10_000`; then keep
only the newest **256**, which **overrides** the keep rules when more than 256 survive them.
`ProbeSession` is `{nonce: String (32 lowercase hex, STO-6), from: FederationId, amount_msat:
u64, leg_fee_cap_msat: u64, c_spendable_before_in_msat: u64, out_net_msat: u64?,
started_at_ms: u64}`: written before leg IN is journaled, updated with `out_net_msat` before
leg OUT is journaled, and cleared in the same transaction that appends the attempt. The nonce
is exclusive: an outcome whose nonce differs from the stored session, or arrives when no
session is stored, is ignored (not applied, with a warning), and the umbrella ledger row is
then not touched either.

`CandidateRecord` (`0x09`): `{id: FederationId` (must equal the key or the read is
`Permanent`)`, invite: InviteCode` (string form, `STO-5`)`, source: DiscoverySource,
discovered_at_ms: u64, structural: StructuralOutcome ∈ {"Passed", {"Rejected": String}},
structural_checked_at_ms: u64, state: CandidateState ∈ {Rejected, Discovered, AutoJoined,
UserApproved}, updated_at_ms: u64}`. A candidate write cannot demote `UserApproved`: when the
stored row is `UserApproved` and the incoming one is not, the write keeps `UserApproved` and
`max(incoming.updated_at_ms, stored.updated_at_ms)`; every other field is overwritten. The
`approve` verb (`API-23`) only promotes from `AutoJoined` (absent or any other state is
`Permanent`), sets `updated_at_ms`, and writes the `Approve` ledger row (`actor User`, `reason
UserInitiated`, `status Succeeded`, create-if-absent) in the same transaction. Seed recovery
(`FMI-31`) promotes **any** state including `AutoJoined` to `UserApproved`, leaves an existing
`UserApproved` untouched, and replaces an unreadable row with `{source: Manual, structural:
Passed, state: UserApproved}` stamped `now`.

## What is and is not durable

**STO-27** Not durable, and MUST NOT be relied on across a restart: the probe verdict policy and
the watch/discovery policies (derived from `Policy` at start), the policy generation
(`ALC-41`), drive and await ownership (`OPS-14`), and any recovery-in-progress marker — a
registered-but-unopened federation is the documented ambiguity (`DOM-2`).

**STO-28** Losing `journal.db` loses the registry, and with it every client partition's
address: `client.db` still holds the ecash, unreachable. The supported path is seed recovery
(`FMI-30`), not a store copy. Losing `client.db` loses the seed and the send-dedup state; seed
recovery from the twelve words rebuilds balances but not dedup (`FMI-32`). The wallet is not
required to provide an application-level backup, snapshot or export of either store: the backup
unit is the seed plus the joined federations' invite codes, "never the local stores"
(`ADR-0025` §1; `SEC-24`). A copy of the stores is an operator's *restore*, outside this set,
under one rule that is `ADR-0025`'s: the two stores are "restored together from a single
snapshot, or not at all" — a wallet started on a mismatched pair is out of contract, and no
requirement in this set holds for it.

## Compatibility rules for types written to a live store

**STO-29** The types a wallet writes to a live store are: `Intent` (and every `Action` variant
inside it), `MoveRecord`, `FederationInfo`, `OperationRecord` (and every `OperationKind`
variant), `ProbeRecord`, `CandidateRecord`, `WatchState`, `Policy`,
`EvacuationSupersessionRecord` — **and every type serialized inside one of them**,
transitively (`FeeBreakdown`, `RefusalDiagnostics`, `EvacuationRefusalEvidence` and its
samples, `ProbeAttempt`, `ProbeSession`, `EvacFeeCap`, …), because a field added to a nested
type is a field added to the row — plus `MoveMeta`, which rides the operation log rather than
the journal (`STO-33`). A type is on this list because the wallet writes it, directly or
embedded (`DEF-13`).

**STO-30** A field added to a type on that list — including to an already-shipped variant —
MUST decode when absent from a stored row, and the value it decodes to MUST be the one the
requirement that introduced it names: for a numeric field that is never an unstated zero
(`DEF-10`; a zero evacuation cap is a livelock). The fields that decode when absent, and what
they decode to, are: `Intent.evacuation_refusal` (`None`), `Action` `Move.gateway` (`None`),
`Action` `Evacuate.gateway` (`None`) and `Evacuate.fee_cap_components` (`None`),
`OperationKind` `Refusal.diagnostics` (all-`None`, `conflict_suppressed: false`), `RefusalDiagnostics.max_fee_bps` (`None`)
and `RefusalDiagnostics.conflict_suppressed` (`false`), the three `Policy` fields of `STO-13`,
`OperationRecord.repaired` (`false`), `WatchState.discover_rotation` (`0`),
`MoveRecord.send_gateway` (`None`) and `OperationKind` `Move.send_gateway` (`None`) — fourteen
in the journal — plus `MoveMeta.fee_cap`, `MoveMeta.from`, `MoveMeta.gateway` and
`MoveMeta.send_gateway` (`STO-33`), which ride the operation log's metadata in `client.db`
(`OPS-25`): eighteen. `CNF-18` demonstrates each by stripping the key from a serialized row
and reading it back.

**STO-31** No type on that list may reject a row for carrying an unknown key (`DEF-11`): a row
written by a newer build MUST stay readable by the previous build, or a rollback cannot start.
Strictness belongs at the request surface (`API-20`), never on the stored type.

## The operation-log side: what the wallet writes into `client.db`

**STO-33** Every lnv2 `receive`/`send` a move commits MUST carry a `MoveMeta` as the
operation's metadata (a JSON value the protocol stores atomically with the operation). Its JSON
is:

| Key | Type | Rule |
|---|---|---|
| `move_id` | `String` | the attempt's operation correlation key (`STO-34`): equal to the intent key on attempt 0 |
| `role` | `"send"` \| `"receive"` | lowercase — the one lowercase enum in the system |
| `amount` | `u64` msat | the net the destination should receive, after any evacuation down-sizing |
| `fee_cap` | `u64` msat | optional: **omitted** when none, never `null`; absent decodes as none and reassembly falls back to the intent's planned cap — never to zero |
| `from` | `[u8;32]` | optional, same omission rule; absent for a `DirectInflow` |
| `to` | `[u8;32]` | required |
| `gateway` | `String` | optional, same omission rule: the URL of the gateway this leg was committed through, so a committed route replays after cache loss (`OPS-20`); absent on an operation an older build wrote, and decodes as none |
| `send_gateway` | `String` | optional, same omission rule: on the receive operation of a **hop** (`OVR-13`), the URL of the source-leg gateway the route was committed with, so the whole route replays before any send operation exists; absent on a shared route and on a send operation |

A receive operation additionally carries `receive_contract_quoted` (`u64` msat): the exact
contract amount the quote expected before minting (`OPS-23`); absent means an operation an
older build wrote, malformed is corruption; a send operation never
carries it, and a reader of `MoveMeta` ignores it as an unknown key. The operation-log backfill
(`OPS-20`) recognises a move operation by the **presence of the `move_id` key** alone: an
operation without it is skipped silently; one with it whose value fails to decode as a
`MoveMeta` is corruption (warned and skipped). The leg is taken from the protocol's own
send-or-receive operation variant, which is authoritative over `role`.

**STO-34** A raw `Pay` writes the metadata `{"role":"send","correlation_key":"<k>"}` and a raw
`Receive` writes `{"role":"receive","correlation_key":"<k>"}`, where `<k>` is the **attempt
correlation key**: the intent's `idempotency_key` when `attempt == 0`, and otherwise
`retry:<len>:<key>:<attempt>` with `<len>` the decimal byte length of the idempotency key,
`<key>` the idempotency key verbatim and `<attempt>` the decimal attempt number (a `pay:` key
is 68 bytes, so its first retry is `retry:68:pay:<64 hex>:1`). The same value is
`MoveMeta.move_id` for a move attempt. Repair's primary operation-log lookup (`STO-24`) and
every backfill therefore match on this per-attempt key, so a retry can never adopt the
operation that terminally failed the previous attempt (`OPS-1`). Neither metadata object
carries any other key; both are recognised as non-move operations by the absence of `move_id`
(`STO-33`).

**STO-35** Ledger `error` text is persisted verbatim and never re-derived on read: the
perform's diagnostic, `MoveRecord.outcome`, a repair note, or `"{note} ({err})"` is stored as
written. It can be *rewritten* only by the writes `STO-16` permits — a repaired soft terminal
(such as "never reached the federation") is superseded exactly once by an authoritative write
that replaces or clears the error when protocol evidence arrives, and a same-status
non-terminal enrichment may overwrite it; an unrepaired terminal row's `error` is immutable.
Every wording ever written to a row that reached an unrepaired terminal therefore lives in the
store forever, and any classifier that reads `error` — the auto-join count that excludes a
`Succeeded` agent `Join` row carrying "already joined (concurrent/prior); no-op re-open"
(`OPS-42`, `ALC-29`), the never-reached recogniser of `STO-24`, and the operator reading
history — MUST match the stored text exactly as listed here and in `STO-24`, and a change to any of
these strings MUST keep matching the wording already on disk or it silently changes the money
accounting of rows already written.
