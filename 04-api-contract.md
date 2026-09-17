# 04 — API contract

What a frontend can rely on at the wallet's two scripted boundaries: the HTTP surface a
resident host serves and the CLI that speaks it. Every route, JSON field, status code, exit
code and stdout line here is a contract — a caller written against it MUST keep working across
any rewrite of the wallet that keeps the wire the same (`ADR-0032`). What is not here is how
the wallet produces it: the HTTP framework, the request-decoding library, the task or actor
that handles a request and the name of the routine that validates it are the implementation's.
A name in backticks is a wire type or field (`API-32`), a persisted shape (`STO-5`, `STO-6`,
`STO-15`) or a protocol fact. Where a rule about what a request *means* to the engine lives in
`03-operation-lifecycle.md`, this chapter cites it and states only what the wire carries.

## Transport and authentication

**API-1** The daemon serves plain HTTP. There is no TLS, no rate limiting and no CORS handling;
the trust boundary is the operating-system user (`SEC-1`), and the only safe non-loopback
deployment is an authenticated tunnel in front of the daemon (`SEC-3`). The wallet's own bounds
on a request are the body limit of `API-35` and the two request deadlines (`API-11`, `API-21`);
this set requires no request timeout and no connection cap of the daemon. `POST /v1/reconcile`
reads no body and accepts one of any size.

**API-2** Every route, including `/v1/health`, requires `Authorization: Bearer <token>`.
Authentication MUST run before routing: an unauthenticated request to an unknown path or an
unsupported method is `401`, never `404` or `405`. The header value MUST begin with the seven
bytes `Bearer ` (case-sensitive, exactly one space); the remainder is compared byte-for-byte,
in constant time over the content (`SEC-2`), against the token the daemon read at start (the
file's contents with surrounding whitespace trimmed, `HST-4`). A missing header, a non-`Bearer`
scheme, a length mismatch or a wrong token all return `401` with the body
`{"kind":"unauthorized","refuse_reason":null,"operation_key":null,"message":"missing or invalid
bearer token"}` and **no** `WWW-Authenticate` header.

**API-3** The token is 32 random bytes, lower-hex (64 characters), written `0600` by `walletd
init`, which rotates it (its entropy and comparison are `SEC-2`). Re-running `init` while the daemon runs MUST block on the
store lock rather than rotate the token underneath a running daemon.

**API-4** The bind address defaults to `127.0.0.1:9736`. It is a free-form string in
`walletd.toml`; `0.0.0.0` is accepted. Loopback is a default, not an enforced invariant
(`SEC-3`).

## Error envelope

**API-5** Every non-2xx response **the wallet itself produces** is

```json
{ "kind": "refused|failed|unauthorized|not_found|timeout",
  "refuse_reason": "<optional>", "operation_key": "<optional>", "message": "<text>" }
```

All four keys are always present: `refuse_reason` and `operation_key` are JSON `null` when
absent, never omitted. An **authenticated** request to an unknown path is `404` with an empty
body, and a known path with an unsupported method is `405` with an empty body and an `Allow`
header — neither is this envelope (an unauthenticated one is `401`, `API-2`).

`refuse_reason` is the wire spelling of the refusal reason `OPS-39` assigns. The nine unit
reasons are bare `snake_case` strings: `"insufficient_after_reservations"`,
`"fed_held_by_probe"`, `"over_cap"`, `"budget_exhausted"`, `"amount_required"`,
`"storage_error"`, `"policy_invalid"`, `"policy_superseded"`, `"conflict"`. The one structured
reason is an object, `{"sizing_conflict":{"field":"<name>"}}`, with two values of `field`:
`"amount"` when a pay's stated `amount` disagrees with the invoice (`API-18`), and `"request
sizing"` when a live operation key is re-submitted with **any** sizing field changed (`OPS-8`).
The sizing fields compared are `OPS-8`'s, per action kind; one consequence a caller sees is
that a `POST /v1/direct-inflow` re-sent with the same `nonce` and a different `fee_cap` is
refused, because `dinflow:<to>:<amount>:<nonce>` (`STO-6`) does not embed the cap. Which
condition yields which reason, and that the reason is stable under any change to the message
text, is `OPS-39`.

**API-6** Status codes map as follows and nowhere else:

| Status | Kind | When |
|---|---|---|
| 401 | unauthorized | `API-2` |
| 404 | not_found | unknown operation key; unknown candidate on approve |
| 422 | refused | `policy_invalid`, `amount_required`, `sizing_conflict`; and every request validation failure with no reason (bad invoice, `from == to`, unjoined federation, bad nonce, malformed JSON, bad query or path, unknown policy field, a reclaim of an operation that is not reclaimable) |
| 409 | refused | `insufficient_after_reservations`, `fed_held_by_probe`, `over_cap`, `budget_exhausted`, `storage_error`, `policy_superseded`, `conflict` |
| 409 | failed | a journaled terminal failure surfaced synchronously; carries `operation_key` |
| 503 | failed | shutting down, engine stopped, destination federation joined but not open (fresh key, or a retry of a `Failed` key), a balance read failing on an open source federation during money-verb admission, or a `/v1/status` precondition (`API-15`) |
| 504 | timeout | a long-poll or invoice deadline elapsed; carries `operation_key` when the operation was admitted |
| 500 | failed | storage fault (`API-37`) |

The two `refused` rows are exhaustive over the ten reasons — the nine `OPS-39` enumerates plus
`amount_required`, which only a `pay` request produces (`API-18`): `policy_invalid`,
`amount_required`, `sizing_conflict` → `422`; `insufficient_after_reservations`,
`fed_held_by_probe`, `over_cap`, `budget_exhausted`, `storage_error`, `policy_superseded`,
`conflict` → `409`; every one of them carries `"kind":"refused"` and no `operation_key`.
(`storage_error` as a *refusal* is the fail-closed read on the admission path of `OPS-39` and is
`409`; a storage fault anywhere else in a request is the `500` `failed` of `API-37`.)

The `message` of every `422` with no reason MUST carry a fixed prefix by class: `invalid JSON
request body: <detail>` (any body-decoding failure, `API-35`), `invalid query parameters:
<detail>` (any query-string failure), `invalid path parameter: <detail>` (any path-segment
failure); `<detail>` is informative text. The verb-specific validation messages are verbatim
in `API-36`.

**API-7** A `refused` response with no `operation_key` means nothing was journaled. A `failed`
response with a key means the operation exists and terminalized. Callers MUST branch on the
key's presence, not the status code alone (`OPS-38`).

## Routes

**API-8** The complete route table. There are nineteen routes on eighteen paths.

| Method | Path | Returns |
|---|---|---|
| GET | `/v1/balance` | `{total, federations:[FederationView]}` |
| GET | `/v1/federations` | `[FederationView]` |
| GET | `/v1/history` | `{operations:[OperationView], next_before_seq}`; with `status=open` also `skipped_unreadable` (`API-43`) |
| GET | `/v1/operations/{key}` | `OperationView` |
| POST | `/v1/operations/{key}/reclaim` | 200 `{operation_key, outcome}` (`API-42`) |
| GET | `/v1/status` | dry-run of the next tick (`API-15`) |
| GET | `/v1/watch/status` | `{occurrence, last_discover_ms, discover_cursor, discover_backlog}` |
| GET | `/v1/health` | `HealthView` (`API-16`) |
| POST | `/v1/pay` | 202 `{operation_key}` |
| POST | `/v1/move` | 202 `{operation_key}` |
| POST | `/v1/receive` | 200 `{operation_key, invoice}` |
| POST | `/v1/direct-inflow` | 200 `{operation_key, invoice}` |
| POST | `/v1/join` | 202 `{operation_key}` |
| POST | `/v1/recover` | 202 `{operation_key}` |
| POST | `/v1/approve` | 200 `{operation_key}` |
| GET | `/v1/candidates` | `[CandidateView]` |
| POST | `/v1/reconcile` | `{redriven, awaiters_rehydrated, executing_normalized}` |
| GET | `/v1/policy` | `Policy` |
| PUT | `/v1/policy` | `Policy` as stored |

### Reads

**API-9** `GET /v1/balance` sums the balances of every *open* federation (`DOM-2`). A
`FederationView` is `{id, balance, invite, joined_at_secs}`: `id` a federation-id array
(`API-32`), `invite` the canonical invite-code string, `joined_at_secs` the registry's
joined-at seconds (`DOM-1`), and `balance` msat or `null`. A federation that is joined but
failed to open is still listed with `balance: null` and is excluded from `total`. The response
is 200 regardless; a caller that wants "every joined federation is open" MUST check for nulls
(the CLI does, `API-39`). `GET /v1/federations` returns the same list.

**API-10** `GET /v1/history` reads exactly three query parameters: `limit` (unsigned integer,
default 50; values above 500 are silently capped to 500), `before_seq` (unsigned integer) and
`status` (`API-43`).
`before_seq` is **exclusive**: the page holds rows with `seq < before_seq`, newest first
(`STO-19`). `next_before_seq` is the `seq` of the last row the page **reached** — returned or
skipped as unreadable (`STO-19`, `OVR-14`), so a skipped row never strands the rows older than
it — when `limit > 0` and the scan stopped before the ledger's first row, else `null`; pass it
back as `before_seq` for the next page. `limit=0` returns
`{"operations":[],"next_before_seq":null}` (with `status=open`, `API-43`'s extra field too).
A non-integer or negative value for either
parameter is `422` `invalid query parameters: …` (`API-6`). **Any other query parameter
(`actor`, `fed`, `kind`, …) is ignored and adds no filtering** — a `status=open` (`API-43`)
beside it still applies. The route carries no federation filter: the CLI emulates
actor and status filters by paging client-side (`API-40`), and `history --fed` is
standalone-only (`API-25`). A caller MUST NOT infer filtering from a `200`. Undecodable ledger
rows are skipped without signal on the unfiltered route (`STO-19`); only a `status=open` page
counts them (`API-43`).

**API-11** `GET /v1/operations/{key}` reads the ledger row for `key` and returns `404`
`no operation found for key <key>` if none exists. `wait` is a boolean query parameter: absent
means `false`, the literals `true`/`false` are accepted, anything else is `422` `invalid query
parameters: …`. `?wait=true` first waits for the operation to reach terminal and only then
reads the ledger row. That wait is decided against the **intent**, not the ledger: a key with
no intent (`refuse:`, `probe:`, `tick:`, `discover:`, `autojoin:`, `approve:` and `reclaim:`
keys are ledger-only, `STO-6`) is `404` under `wait=true` even though the same GET without
`wait` returns its row; "terminal" means the intent is `Done` or `Failed` (`OPS-16`), and an
already-terminal intent resolves immediately. The deadline is **60 s**, after which the
response is `504` `operation wait deadline elapsed` carrying the key. `show` additionally
projects `evacuation_refusal` and `evacuation_refusal_active` from the exact intent (`OPS-31`);
`history` does not.

**API-12** `OperationView` carries: `seq, updated_at_ms, kind, status, amount?, fee_cap?,
receive_fee?, send_fee_quoted?, actor, reason, operation_key, error?`, plus `superseded_by?,
supersedes?, refusal?, evacuation_refusal?, evacuation_refusal_active?` when present; the
per-field types and null-versus-omitted rules are the table in `API-33`, and the `refusal` /
`evacuation_refusal` object schemas are `API-34`. `kind` ∈ `join, recover, receive, pay,
direct-inflow, move, evacuation, refusal, probe, tick, discover, autojoin, approve, reclaim` —
the persisted `OperationKind` variant names of `STO-15` lower-cased (`AutoJoin` → `autojoin`),
with exactly two exceptions: `DirectInflow` → `direct-inflow`, and a `Move` row whose
`evacuation` flag is set → `evacuation`. `status` ∈ `started | awaiting | succeeded |
failed`. `actor` is `"user"` or `"agent:<occurrence>"`. `reason` is the `reason_tag`
vocabulary `ALC-51` owns (eleven `snake_case` tags), shared with `/v1/status`; every user-verb
row is `user_initiated`. On the wire `reason` is always the tag; the **persisted** row stores
the PascalCase variant (`"UserInitiated"`, `STO-5`), which only the standalone `--json`
renderings expose (`API-30`). `fee_cap` is the row's `fees.fee_cap` (`STO-15`): the admitted
cap from the row's first write (`STO-16`), restamped together with `amount` to the cap enforced
at the delivered net once a move artifact exists (`STO-17`), so the cap a money operation was
held to is auditable through a running daemon. The view carries no federation id.

**API-13** A recovery whose ledger row is `succeeded` (intent `Done`) but whose federation is
still registered-but-unopened (`DOM-2`: "a recovery has committed the registry row and not yet
made the client available") MUST be reported as `started`, so a caller never observes
"succeeded" alongside a zero balance.

**API-14** `GET /v1/watch/status` is a pure journal read of `WatchState` (`STO-12`).

**API-15** `GET /v1/status` is a dry run of the next scheduler tick against the stored policy
at `occurrence + 1` (`ALC-44`). It returns `{spending_fed, standby_fed, decisions:[{operation_key,
reason, action}], scored:[{id, gated_eligible}], deferred:[{dest, source, reason, want_msat,
floor_msat, floor_source}], suppressed:[{operation_key, reason, held_by}]}`, where `suppressed`
is every conflict-withheld candidate with `held_by` the operation key of the intent whose goal
holds it (`ALC-30`, `ALC-44`). Value domains: `spending_fed`, `standby_fed`, `deferred[].source`
are 64-character lower-hex federation ids or `null`; `scored[].id` and `deferred[].dest` are the
same hex, never null (this is the one place a federation id is hex on the wire, `API-32`);
`decisions[].reason` and `deferred[].reason` use the `reason_tag` vocabulary of `API-12`, and
`suppressed[].reason` is the withheld decision's tag — the `<reason>` of its
`conflict-suppressed:` key (`STO-6`, `ALC-51`); `deferred[].floor_source` ∈ `protocol_min_move | route_min_viable`
(`ALC-10`); `want_msat`, `floor_msat` are unsigned integers; `gated_eligible` is a bool.
**`decisions[].action` is explicitly non-contractual**: it is display text describing the
would-run decision, which MAY change between builds. A caller MUST treat it as opaque and MUST
NOT parse it; the CLI prints it verbatim. The route returns **503** before the dry run when the
engine is absent, the federation registry reports a skipped corrupt row (`status dry-run
refuses an incomplete federation registry: …`), any joined federation is unopened (`status
dry-run requires every joined federation to be open; unopened: <hex, …>. …`), the watch
occurrence is at its fail-closed maximum, or probing errors (`status probe failed: <error>`;
the fences of `ALC-46`). The CLI's client-mode `status` MUST render every list in this
response, `deferred` and `suppressed` included (`API-39`): an operator using the CLI MUST be
able to see a withheld funding goal and a conflict-suppressed candidate.

**API-16** `GET /v1/health` always returns 200 when authenticated (`SEC-4`). Body:
`{actor_queue_depth, inflight_drivers, scheduler_alive, automation_ready, automation_blocked?}`.
`scheduler_alive` is `true` for as long as the resident scheduler (`ALC-38`) is running —
sleeping between cycles included — and `false` once it has stopped (`ALC-42`: "MUST read
`false` from then on"); `automation_ready` and `automation_blocked` are the readiness signal `ALC-45`
owns: `automation_ready` is `true` exactly when `automation_blocked` is `null`, and
`automation_blocked` is `{reason, detail}` (two strings) with `reason` ∈ `cycle_failed |
partial_federation_view | corrupt_federation_registry`. All five keys are always emitted;
`automation_blocked` is JSON `null` when ready, never omitted. A caller reading a daemon whose
body lacks `automation_ready` MUST treat readiness as unknown, not healthy. `inflight_drivers`
is best-effort: a count that cannot be read is reported as `0`, not as an error. Liveness and
readiness are different answers, and a
supervisor that reads only the status code learns neither. The CLI's `health` verb MUST print
all five fields (`API-39`).

**API-17** `GET /v1/candidates` returns the candidate registry in raw key order with
`{id, invite, source, discovered_at_ms, structural, structural_checked_at_ms, state,
updated_at_ms}`; `source` ∈ `observer|nostr|manual`, `state` ∈
`discovered|autojoined|userapproved|rejected` (the vocabularies of `DOM-12`, lower-cased),
`structural` is `passed` or `rejected:<reason>` where `<reason>` is the text the structural
check recorded (`DOM-12` `Rejected(reason)`): the scorer's rejection reason (`ALC-14`) or the
literals `IdMismatch` / `MissingModule` (`ALC-29`); it is not an enumerated vocabulary.
`id` is a federation-id array (`API-32`); `invite` is the canonical invite-code string; the
three `*_ms` fields (`discovered_at_ms`, `structural_checked_at_ms`, `updated_at_ms`) are
unsigned integers and never null. Newest-first ordering is a CLI convenience (`API-40`), not a
wire property.

### Money verbs

Every money verb is admitted as one user decision (`reason: user_initiated`, `actor: user`),
with the balance of every open federation it names sampled before admission — `pay`: `from`;
`move`: `from` and `to`; `receive` and `direct-inflow`: `to` — and submitted to the wallet's
single admission point (`OPS-5`, `API-36`). The response does not say whether the admission was
fresh or attached to an in-flight operation with the same key (`OPS-8`); a caller cannot
distinguish the two from the status code.

**API-18** `POST /v1/pay {invoice, amount?, fee_cap?, fed?}` (unknown fields rejected,
`API-35`; `fed` is a federation-id array, `API-32`). Validation runs in this order, and the
first failure is the response: the stored policy is read (a fault is `API-37`'s `5xx`); the
invoice is parsed (failure is `422` `invalid BOLT11 invoice: <error>`); the amount is
reconciled; `fee_cap` and `fed` are resolved; the source balance is
sampled (`API-36`); the request is admitted. An amountless BOLT11 invoice is `422
amount_required` **whether or not** `amount` is supplied (an lnv2 send carries no amount of its
own; the invoice fixes it); a stated amount that disagrees with the invoice is `422 sizing_conflict{amount}`,
message `stated amount does not match the invoice amount`. `fee_cap` defaults to the policy's
`max_fee`; `fed` defaults to the policy's spending federation, else the sole joined federation,
else `422` (messages in `API-36`). The source federation's **openness is not gated**: a
joined-but-unopened source samples no balance, admission sees zero spendable, and the request
is `409 insufficient_after_reservations` — not `503` (`OPS-5`). The operation key is derived
from the payment hash (`STO-6`), so paying the same invoice twice attaches to the same
operation (`OPS-8`). There is no gateway field on the wire (`ADR-0030`).

**API-19** `POST /v1/move {from, to, amount, fee_cap?, occurrence}`; `occurrence` is required
and, with the resolved `fee_cap`, is part of the operation key (`STO-6`). A caller that omits
`fee_cap` and retries after a policy edit therefore derives a *different* key and admits a
second move; a retry that is meant to attach sends the same values as the first request.
Validation order: `from == to` is `422` `move from and to must be different federations (from
== to is a no-op)`; then `from` and `to` are each checked against the registry (`422`
`federation <hex> is not joined`); then the policy is read and the key derived. A destination
that is joined but not open is `503` **for a fresh key, and for a retry of a `Failed` key** — except a `Failed` move
whose record is `Stranded`, which `OPS-10` refuses `409 conflict` before this check —
(`OPS-5`, `OPS-10`); a replay of a live or `Done` key attaches before that check runs and
succeeds, unless the key is an active probe leg's, which a user request never attaches to:
`409` `conflict` (`DOM-21`). As for `pay`, an unopened **source** is not gated and surfaces as
`409 insufficient_after_reservations` (`API-18`).

**API-20** `PUT /v1/policy` accepts a JSON object (a non-object body is `422` `policy must be
a JSON object`) and rejects any key that is not one of the twenty-eight `Policy` fields
(`STO-13`), with `422` `unknown policy field(s): <k1>, <k2>` — the unknown keys in
**lexicographic** order, comma-space separated, checked before any field is decoded. Exactly
five missing fields are tolerated: `max_fee_bps_of_move`, `evac_fee_base_msat` and
`evac_fee_bps` take the defaults `STO-30` names for them, and the two pins `spending_fed` /
`standby_fed` decode as `null` when absent — so a body that omits a pin **unpins** that
federation rather than being refused. Any other missing field, or a field of the wrong type, is
`422` `policy is not well-formed: <detail>`. `spending_fed`/`standby_fed` are federation-id
arrays or `null` (`API-32`); the other twenty-six fields are unsigned integers or booleans; all
twenty-eight keys are always present in the `GET` and `PUT` responses. The decoded policy is
then validated (`DOM-15`) and an invalid one is refused `422 policy_invalid` naming the field.
The stored `Policy` type itself is permissive (`STO-31`); this route is where strictness lives,
and it MUST stay here so the wire contract cannot drift from the stored type.

**API-21** `POST /v1/receive {to?, amount, fee_cap?, nonce}` and `POST /v1/direct-inflow` (same
shape). `nonce` is non-empty RFC 3986 unreserved characters (verbatim refusals in `API-36`) and
is part of the key (`STO-6`). `to` resolves exactly as `fed` does for `pay` (explicit → policy
`spending_fed` → sole joined → `422`). The daemon admits the intent and then **blocks up to 30
seconds** for the invoice artifact: terminal without an invoice is `409 failed` with the key and
message `the operation terminalized without a payable invoice`; the deadline is `504 timeout`
with the key and message `invoice mint deadline elapsed; settlement continues asynchronously`.
Re-submitting the same key re-yields the same invoice (`OPS-8`). `receive` deducts fees from the
invoice; `direct-inflow` grosses the invoice up so the destination is credited `amount`, never
more and possibly less by a bounded receive-fee step (`FMI-15`).

**API-22** `POST /v1/join {invite}` and `POST /v1/recover {invite}` are 202 and asynchronous;
await them with `GET /v1/operations/{key}?wait=true`. The invite is parsed as an invite code
(failure is `422` `invalid invite code: <error>`) and **canonicalised** by re-serialising the
parsed value before the key is derived, so two spellings of one invite share a key (`STO-6` for
the `join:`/`recover:` key shapes). Neither verb samples balances; neither gates on the
registry synchronously — `join` records whether the membership pre-existed, and whether the
join is new is decided during execution (`OPS-42`). A recovery of an already-registered
federation is refused during execution, so the operation terminalizes `failed` rather than the
request returning 4xx (`FMI-30`).

**API-23** `POST /v1/approve {fed}` promotes an `autojoined` candidate to `userapproved`
(`ALC-37`). `404` `candidate <hex> was not found` if no such candidate; `409 conflict`
`candidate <hex> is <State>, not AutoJoined` (`<State>` is the persisted variant name,
`Discovered`, `UserApproved` or `Rejected`, `STO-5`) if the state is not `autojoined`; a
concurrent approval that wins the race after that check is also `409 conflict` (`OPS-39`). The
response is **200** (not 202) `{operation_key}` with a fresh random key
`approve:<hex>:<32 hex chars>` per call, so the verb is not idempotent: the second identical
request is the `409`. The row is written in the promotion's own transaction (`OVR-4`,
`STO-26`); no intent is created.

**API-24** `POST /v1/reconcile` runs a durable reconciliation pass (`OPS-35`, preserve mode)
then a best-effort ledger repair (`STO-24`); a repair fault is logged and the response is still
200 with the counts of the pass.

## The CLI

**API-25** `wallet-cli` is a thin HTTP client by default. It resolves the daemon from
`$XDG_CONFIG_HOME/walletd/client.toml`, else `~/.config/walletd/client.toml` (written by
`walletd init`, `{url, token_path}`, `HST-4`), unless both `--url` and `--token-path` are
given, in which case the pointer is not read at all. `--url` alone overrides the pointer's URL,
`--token-path` alone its token path; the base URL's trailing `/` is stripped; the token file is
read and trimmed. A missing pointer with no `--url`, or a missing/empty token file, is the
not-running error (exit 4); a pointer that exists but does not parse is exit 1; an unset `HOME`
without both overrides is exit 1. Every request carries a **90 s** client-side timeout, chosen
to exceed the daemon's 60 s long-poll (`API-11`). `--standalone`, `--url`, `--token-path` and
`--gateway` are global flags (accepted before or after the verb); `--data-dir` and
`--perform-timeout` are top-level only and MUST precede the verb. `--standalone` opens the
stores directly under the exclusive lock (`HST-9`) and is the only mode for `discover`,
`probe`, `tick`, `status` with policy overrides, `history --fed`, `show <numeric seq>`, and the
`--gateway` break-glass (`ADR-0030`, `HST-10`). Passing a standalone-only flag or verb in
client mode is a usage error, exit 1, before any request is made: `--data-dir`,
`--perform-timeout` and `--gateway` are each refused with a message naming the flag; the three
agent verbs with `standalone-only verb: rerun with --standalone (this agent verb has no daemon
endpoint)`.

**API-26** The verbs: `join, recover, discover, candidates, approve, balance, list-feds,
receive, pay, await-receive, await-send, direct-inflow, await-move, move, probe, reconcile,
tick, status, health, policy get, policy set, history, show, reclaim`. Exactly four initiate
movement on the user's behalf: `pay`, `receive`, `move`, `direct-inflow` (`CONTEXT.md` **Money
verb**); `reclaim` (`API-42`) claims what the wallet is already owed and initiates nothing.

**API-27** Every one of the twenty-eight `Policy` fields (`STO-13`) is settable through `policy
set` flags. `policy set` is a read-modify-write: it GETs the whole policy, applies the flags,
and PUTs the whole document back. The document it PUTs MUST carry every key the GET returned,
unchanged where no flag named it — including keys this CLI build does not know — and no key
the GET did not return, so an edit from an older CLI against a newer daemon never resets a
field the CLI has no flag for, an edit from a newer CLI against an older daemon never adds a
field that daemon refuses, and the daemon's unknown-key refusal (`API-20`) is the only thing
that rejects a field. A flag naming a field the GET did not return is a usage error (exit 1,
naming the field) before any PUT, so a requested edit is never silently dropped. An
implementation that round-trips the policy through a fixed field set fails this rule.
`--clear-spending-fed` and `--clear-standby-fed` conflict with their pin flags. Flag names are
the field names with `_` → `-`; msat fields take unsigned integers; `--auto-join` and
`--require-mainnet` take an explicit `true|false` value; `--max-fee-bps-of-move` is
range-checked `1..=10000` and `--evac-fee-bps` `0..=10000` **at parse time** (`ALC-7`,
`ALC-20`), so an out-of-range value is a usage error (exit 1) and never reaches `PUT`. Both
`policy get` and `policy set` print the resulting `Policy` as pretty-printed JSON on stdout.

**API-28** Exit codes:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | usage, not found, any non-JSON 4xx other than 401, argument parse error |
| 2 | refused at decision time; nothing journaled |
| 3 | failed; a journaled terminal failure, message carries the key |
| 4 | transport: connection refused, timeout, any 5xx, missing pointer or token, await deadline |
| 5 | authentication (401) |

The mapping from an error envelope (`API-5`) is by `kind`, with one status edge:
`unauthorized` → 5; `refused` → 2; `failed` with a **5xx** status (503/500, nothing journaled)
→ 4, `failed` with any other status (the 409 + key shape) → 3; `timeout` → 4; `not_found` → 1.
A non-JSON error body maps by status class: 401 → 5, 5xx → 4, anything else → 1. A 2xx whose
body fails to decode is 4. Argument errors: a usage error is exit **1** (2 is reserved for
refusals); `--help` and `--version` exit 0. `balance` and client-mode `status` exit 1 after
printing when any joined federation is unopened (`API-9`, `API-39`). The stderr line is
prefixed by layer: `refused: <message>: <reason>`, `failed: <message> (operation key: <key>)`,
`auth error: <message>`; transport and usage messages carry no prefix, and the not-running case
is the two-line `walletd is not running (or not initialized): <detail>` / `start walletd, or
rerun with --standalone`. stderr text is informative; the exit code is the contract.

**API-29** Output shapes are frozen: a money verb prints `<word> <key>` to stdout and `key: <key>`
to stderr; `receive`/`direct-inflow` print the invoice to stdout; await verbs print `claimed`,
`success`, `done` or `failed: <error>` (`API-38`). `--json` exists on `discover`, `candidates`,
`history` and `show` only. `history` is a ten-column TSV: `seq, updated_at, kind, status,
amount, recv_fee, send_fee_quoted, actor, reason, key`. The remaining verbs' stdout shapes are
the table in `API-39`; the CLI-supplied defaults for the idempotency inputs (`nonce`,
`occurrence`) are `API-41`.

**API-30** Standalone `show --json` and `history --json` render the flattened persisted record:
every `OperationRecord` field of `STO-15` at the top level in its stored form per `STO-5` —
`kind` as the externally-tagged `OperationKind` object with operation ids and gateways, `fees`
with the enforced cap, `status` and `reason` as PascalCase variant names, `actor` as the
variant object, `correlation_key` rather than `operation_key`, plus `repaired` — with
`supersedes`, `superseded_by`, `evacuation_refusal`, `evacuation_refusal_active` appended when
present; client mode renders `OperationView` (`API-33`). The two are different shapes by
design: one is the audit form of the row, the other the frontend view.

## What the wire does not carry

**API-31** Deliberate absences, each owned elsewhere: no gateway on any money request or await
(`ADR-0030`: the break-glass is a standalone flag bound to one operation key, never a wire
field); no federation or actor filter on `/v1/history` (`API-10`; `status=open`, `API-43`, is its one filter); no preimage on any
response (`API-38`); no cause attached to a money state the wallet did not observe (`OPS-40`).
A field this chapter does not list is not on the wire, and a caller MUST NOT depend on one.

## Wire encoding

**API-32** The JSON representation of every wire type follows the encoding rules `STO-5` owns
(objects keyed by field name verbatim, `snake_case`; external tagging; a 32-byte identifier as
an array of 32 integers; an optional value as `null`). The wire deltas an implementer MUST
know: a `FederationId` is that **array of 32 integers 0–255** on every request and response
field that carries one — `PayRequest.fed`, `MoveRequest.from/to`, `ReceiveRequest.to`,
`DirectInflowRequest.to`, `ApproveRequest.fed`, `Policy.spending_fed/standby_fed`,
`FederationView.id`, `CandidateView.id`, `WatchStatusView.discover_cursor`,
`RefusalDiagnostics.source` — and is **64-character lower-hex** only inside the `/v1/status`
body (`API-15`); no route accepts hex in a request. `Msat` and `Occurrence` are bare unsigned
integers (`STO-5`). The
operation status, the error `kind` (`API-5`) and the nine unit refusal reasons are `snake_case`
strings, and the one structured reason is the `sizing_conflict` object of `API-5`;
`kind`, `actor`, `reason`, `source`, `state` and `structural` on the views are plain strings
whose vocabularies `API-12` and `API-17` list. No wire object renames, flattens or nests a
field other than as this chapter shows it.

**API-33** `OperationView` field table. "always" means the key is present in every response
and is `null` when the value is absent; "omitted" means the key is absent from the JSON when
the value is absent and a caller MUST decode a missing key as absent.

| Field | Type | Absent |
|---|---|---|
| `seq` | u64 | never |
| `updated_at_ms` | u64 | never |
| `kind` | string (`API-12`) | never |
| `status` | `started\|awaiting\|succeeded\|failed` | never |
| `amount` | msat | always, `null` |
| `fee_cap` | msat | always, `null`: the row's `fees.fee_cap` (`STO-15`, `STO-16`, `STO-17`); `null` on a kind that carries no cap (`join`, `recover`, `refusal`, `probe`, `tick`, `discover`, `autojoin`, `approve`, `reclaim`) |
| `receive_fee` | msat | always, `null` |
| `send_fee_quoted` | msat | always, `null` |
| `actor` | string | never |
| `reason` | string (`API-12`) | never |
| `operation_key` | string | never |
| `error` | string | always, `null` (cleared on success) |
| `superseded_by` | string (key) | omitted |
| `supersedes` | string (key) | omitted |
| `refusal` | object (`API-34`) | omitted; emitted only when `kind == "refusal"` **and** the diagnostics are populated — at least one of the nine optional figures is non-null, or `conflict_suppressed` is `true` (a figure-less refusal has no key) |
| `evacuation_refusal` | object (`API-34`) | omitted; `show` only, never on `history` |
| `evacuation_refusal_active` | bool | omitted on `history` and when `show` finds no readable intent; `true` = a live Pending agent-evacuation marker, `false` = the intent is readable but not live (`OPS-31`) |

`amount` is the invoiced amount for `receive`, the invoice amount for `pay` (null when unknown),
the net amount for `direct-inflow`/`move`/`evacuation`, the probe amount for `probe`, and null
for every other kind.

**API-34** The two nested objects. `refusal` is the `RefusalDiagnostics` object of `STO-15`
with all ten keys always present: `source` (federation-id array or `null`), `want`, `available`,
`source_spendable`, `max_fee`, `cap_room`, `amount`, `min_move` (each msat or `null`),
`max_fee_bps` (u16 or `null`), `conflict_suppressed` (bool, never null); the meaning of each
figure is `ALC-9`. `evacuation_refusal` is the `EvacuationRefusalEvidence` object of `STO-9`,
seven keys, none nullable: `cap_components` (`{"base_msat": <msat>, "bps": <u16>}`),
`requested_net` (msat), `source_spendable` (msat), `low` and `high` (each `{"delivered_net":
<msat>, "total_fee": <msat>, "fee_cap": <msat>}`), `diagnostic` (string), `measured_at_ms`
(u64). Its semantics are `OPS-31`.

## Request decoding and daemon-side validation

**API-35** Every request body MUST be decoded as JSON, and every decoding failure is `422
refused` with message `invalid JSON request body: <detail>` — a missing or
non-`application/json` `Content-Type` header, a syntax error, a type mismatch, an unknown key
(every request object rejects unknown fields), and a body over **2 MiB**. A request's optional
fields MAY be omitted or sent as `null`; `null` for a required field is a type mismatch. `PUT
/v1/policy`'s unknown-key and missing-field refusals are `API-20`'s messages, not this one. This rule applies to every route that takes a request body (`API-18`–`API-23`); `POST /v1/operations/{key}/reclaim` takes an empty body and decodes nothing (`API-42`), and `POST /v1/reconcile` reads no body: its body is ignored whatever its
size or content type. Request order of keys is irrelevant everywhere, including the `unknown
policy field(s)` listing, which is lexicographic (`API-20`).

**API-36** Trust-boundary validation the daemon performs itself before admission, with the
verbatim `422` message (no `refuse_reason`) unless stated:

| Check | Where | Message |
|---|---|---|
| nonce empty | `receive`, `direct-inflow` | `nonce must not be empty` |
| nonce charset: only `A-Z a-z 0-9 - . _ ~` | same | `nonce must contain only unreserved URL characters (A-Z a-z 0-9 - . _ ~)` |
| invoice does not parse | `pay` | `invalid BOLT11 invoice: <error>` |
| invoice amountless | `pay` | `refuse_reason: "amount_required"`, `API-18` |
| stated amount ≠ invoice amount | `pay` | `refuse_reason: {"sizing_conflict":{"field":"amount"}}`, `stated amount does not match the invoice amount` |
| `from == to` | `move` | `move from and to must be different federations (from == to is a no-op)` |
| named federation not in the registry | `pay`, `receive`, `direct-inflow` (explicit or pinned), `move` (both) | `federation <hex> is not joined` |
| no federation named, none joined | `pay`, `receive`, `direct-inflow` | `no federations joined; join one first` |
| no federation named, several joined | same | `multiple federations joined; name the federation explicitly` |
| invite does not parse | `join`, `recover` | `invalid invite code: <error>` |
| `limit`/`before_seq` not unsigned integers | `history` | `invalid query parameters: …` (`API-10`) |
| `wait` not a bool literal | `operations/{key}` | `invalid query parameters: …` (`API-11`) |
| policy body not an object / unknown key / missing or mistyped field | `policy` PUT | `API-20` |

Balance sampling then reads the live balance of every *open* federation the verb names; a
federation that is joined but not open is omitted from the sample (admission treats it as zero
spendable, `OPS-5`); a balance read that **fails** on an open federation is `503 failed`
`reading balance for federation <hex> failed: <error>` and nothing is admitted. Amounts and fee
caps are not range-checked by the daemon (`0` is passed through to admission, `OPS-7`).

**API-37** `5xx` bodies. A journal read or write fault anywhere in a request — except the
three admission reads `OPS-39` names (the key read, the goal-blocker scan, a probe-record
read), where it is the refusal `storage_error` and `API-6` answers `409` with nothing
journaled, and best-effort work, whose failure `OVR-4` says "MUST NOT fail the work it
records" — the whole ledger-repair pass after a reconcile, its scan included (`API-24`), and
the `Reclaim` row of a re-claim
(`STO-15`), whose responses report the pass and the claim outcome with `200` — is `500` `{"kind":"failed"}` whose `message` is the storage fault's error text verbatim, as the wallet's
storage layer reports it — informative, never parsed, and it MAY contain storage paths and the
data directory (`SEC-6`), so a frontend MUST NOT show it to an untrusted party. `503 failed`
messages are `wallet service is shutting down`, `wallet service actor stopped`, the
destination-unavailable text of `OPS-38` for a fresh destination-side admission (`API-19`), the
balance-read text of `API-36`, and the `/v1/status` fences of `API-15`. No 5xx carries a
`refuse_reason`. The two `504`s — the `?wait=true` deadline (`API-11`) and the invoice mint
deadline (`API-21`) — carry `operation_key` when the operation was admitted; `500` and `503`
carry neither.

## CLI verb details

**API-38** The await verbs. `await-receive <key>`, `await-send <key>` and `await-move <key>`
take `--timeout <secs>` (default **600**) and poll `GET /v1/operations/{key}?wait=true` until
terminal: a `2xx` with a terminal `status` ends the wait; a `2xx` that is not terminal, or a
`504`, is re-polled after 200 ms; any other non-`2xx` is mapped by `API-28` and **not** retried (a dead
daemon fails fast); when `--timeout` elapses the exit is 4 with `await timed out after <n>s
waiting for operation <key> to terminalize`. Before printing, the verb checks the row's `kind`:
`await-receive` accepts only `receive`, `await-send` only `pay`, `await-move` accepts `move`,
`evacuation`, `direct-inflow`, `join` and `recover`; a mismatch is exit 1 `operation <key> is a
\`<kind>\` operation, not awaitable with \`<verb>\`` with nothing on stdout. A `succeeded` row
prints `claimed` / `success` / `done` respectively and exits 0; a `failed` row prints `failed:
<error>` — on **stdout**, with `(no diagnostic)` when `error` is null — and exits 3 with
`operation <key> failed: <error>` on stderr. `await-send` prints no preimage (the wire carries
none).

**API-39** Client-mode stdout shapes for the verbs `API-29` does not list. `<hex>` is a
64-character lower-hex federation id; one line per row unless stated.

| Verb | stdout |
|---|---|
| `balance` | `<hex>: <n> msat` per federation, or `<hex>: unavailable (failed to open)` when `balance` is null; then `total (<open>/<joined> federations): <n> msat`; exit 1 if `open < joined` (`API-9`) |
| `list-feds` | `<hex> invite=<invite> joined_at=<secs>` |
| `health` | one line, `actor_queue_depth=<n> inflight_drivers=<n> scheduler_alive=<true\|false> automation_ready=<true\|false\|unknown> automation_blocked=<none\|unknown\|<reason>: <detail>>` — every field of `API-16`; both read `unknown`, and only then, for a body without `automation_ready` (`API-16`'s caller rule) |
| `reconcile` | `redriven=<n> awaiters_rehydrated=<n> executing_normalized=<n>` |
| `status` | `spending_fed: <hex\|none>`, `standby_fed: <hex\|none>`, `<hex> gated_eligible=<bool>` per `scored`, `<hex>: unavailable (failed to open)` per federation whose `/v1/federations` balance is null (a second GET the verb makes), `decision: <key> reason=<reason> action=<action>` per decision, `deferred: <dest> source=<hex\|none> reason=<reason> want_msat=<n> floor_msat=<n> floor_source=<floor_source>` per `deferred`, `suppressed: <key> reason=<reason> held_by=<key>` per `suppressed` — every list of `API-15`; exit 1 if any unopened |
| `approve <hex>` | `<hex>`; `key: <key>` on stderr |
| `policy get` / `policy set` | pretty-printed `Policy` JSON (`API-27`) |
| `candidates` | 8-column TSV `id state source discovered_at_ms structural structural_checked_at_ms updated_at_ms invite`; `--json` prints the filtered, sorted array as ONE line of JSON (`CandidateView` objects) |
| `history` | the `API-29` TSV; `-` for a null `amount`/fee; `updated_at` as `YYYY-MM-DDTHH:MM:SS.mmmZ` (UTC, millisecond precision); `--json` prints one `OperationView` object per line (JSONL), the wire shape verbatim |
| `show <key>` | one `<label>: <value>` line each for `seq, key, kind, status, actor, reason, updated_at, amount_msat, fee_cap_msat, receive_fee_msat, send_fee_quoted_msat, supersedes, superseded_by, evacuation_refusal` (the object as one-line JSON), `evacuation_refusal_active`, then the refusal diagnostic lines when `refusal` is present, then `error`; `-` for every absent value; `--json` prints the `OperationView` as one line |

**API-40** Client-mode filter emulation. `history --limit N` (default 50) requests pages of
`limit=N` (the daemon caps each at 500, `API-10`), applies `--actor user|agent` (`agent`
matches any `actor` tag beginning `agent`) and `--status started|awaiting|succeeded|failed`
to each page, and follows `next_before_seq` until `N` matching rows are collected or the cursor
is `null`; filters therefore apply before the limit, matching the standalone contract, at the
cost of unbounded paging over a long ledger. `candidates --state
discovered|autojoined|userapproved|rejected` filters client-side, then sorts descending by
`(updated_at_ms, id)` before printing.

**API-41** CLI-supplied idempotency inputs. `receive --nonce` is optional: when omitted the CLI
generates 16 random bytes as 32 lower-hex characters (the generated nonce shape of `STO-6`), so
every nonce-less `receive` is a distinct operation. `direct-inflow --nonce` defaults to the
literal string `"0"`, so two nonce-less `direct-inflow` calls with the same `--amount` and
destination **attach to one operation and re-yield the same invoice** (`OPS-8`); a caller
wanting a second inflow MUST pass a fresh nonce. `move --occurrence` defaults to `0`; the wire
field is required (`API-19`) and the CLI always sends it. `--fee-cap` and `--to`/`--fed` are
omitted from the request when not given, so the daemon-side policy defaults of
`API-18`/`API-19`/`API-21` apply.

**API-42** `POST /v1/operations/{key}/reclaim`, with an empty body, and the CLI verb
`reclaim <key>` carry the re-claim `FMI-41` requires. `{key}` MUST name an operation whose
incoming contract reached a terminal non-claim — a `receive` whose state is `Expired` or
`Failed`, or a `direct-inflow`, `move` or `evacuation` whose receive leg did, a `Stranded` move
included (`OPS-27`); an unknown key is `404 not_found`, and any other operation is `422 refused`
with nothing attempted (`API-6`). The wallet attempts the claim synchronously; the response is
`200 {operation_key, outcome}`, where `operation_key` is `{key}` — the reclaimed operation's,
never the attempt's own `reclaim:` row key, which `history` lists (`STO-6`, `STO-15`) — and
`outcome ∈ claimed, not_claimable`: `claimed` when the
wallet holds the contract's notes after the call, whether this call or an earlier one claimed
them; `not_claimable` when the contract is expired or was consumed by another claimant. The
call is idempotent — repeating it returns the same outcome and never claims twice — and every
attempt leaves a ledger row, written best-effort, so it "MAY be absent after a storage error
and for no other reason" (`OVR-4`) and its absence never changes the response. It requires the bearer token like every route (`API-2`),
and the break-glass gateway override is ignored on it, as on every verb that resolves no route
(`ADR-0030`). The verb prints the outcome and exits 0 on `claimed`, 3 on `not_claimable` with
the key in the message, and per `API-28` otherwise.

**API-43** The open-history filter. `GET /v1/history?status=open` (`ADR-0028`:
"`/v1/history` gains a `?status=open` filter — a read-only journal query") returns only rows
whose status — the projected `OperationView` status `API-13` defines, not the persisted row's
own — is `started` or `awaiting`: the scan reads at most `limit` rows and returns the
open ones among them, so a page may be shorter — the rule `STO-19` states for unreadable rows,
applied to terminal ones too — and `next_before_seq` is still the last row reached
(`API-10`). The response additionally carries `skipped_unreadable` (unsigned integer): the
rows the scan passed over as undecodable — `0` when `limit=0` — because an unreadable row may
be an open operation the caller cannot rebuild (`ADR-0028`: the filter lands "together with
its skipped-undecodable-row signal"; `STO-19` carves it out; `HST-31` says what a frontend
does with it). `open` is the only value; any other is `422` `invalid query parameters: …`.
