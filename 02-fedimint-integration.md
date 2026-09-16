# 02 — Fedimint integration

The boundary between the wallet and the Fedimint federations and lnv2 gateways it uses: what the
wallet derives from the seed, what it sends to a federation or a gateway, what it accepts back,
and what it does with the signals a federation emits. The federation and gateway protocols are
presupposed and cited freely; the client SDK's internal API is not (`ADR-0032`). A type named in
backticks is a wire or on-disk shape, or a Fedimint protocol type.

## Protocol behaviours the wallet depends on

**FMI-39** A single-guardian federation MUST be usable for every lnv2 operation: aggregating one
threshold-decryption share MUST yield the decrypted preimage, and MUST NOT panic or stop the
client's state machines. A one-guardian federation fails the structural floor (`ALC-14`), so
this binds only where such a federation is joined by a user or pinned — but a client that
freezes there freezes every operation on every federation it hosts (`DEF-16`).

**FMI-38** Every wait the wallet issues against a federation's API while driving an intent —
awaiting an incoming contract, a preimage or a decryption key share — MUST be bounded: a
request that has produced neither a result nor an error within **5 minutes** MUST be abandoned
and re-issued, re-issuing MUST be safe (each such wait is a pure read that a replay repeats
without skipping or duplicating), and abandoning it MUST NOT fail or abort any other request in
flight to the same guardian. The per-intent perform timeout (`FMI-22`, `OPS-15`) is a
second, outer bound and does not replace this one: without the transport bound a degraded
connection that still answers keep-alives stalls a receive for as long as the server-side
long-poll allows. Which transport a federation is reached over is `FMI-36`.

**FMI-3** A joined federation's client MUST expose the `mint`, `wallet`, `ln` (lnv1) and `lnv2`
modules: a federation config carrying any of these MUST decode, and seed recovery (`FMI-32`)
MUST rebuild each module's state. The `wallet` module is exposed only so that the config decodes
and the network can be read (`FMI-5`): the wallet MUST NOT peg in or peg out (`OVR-11`). The
wallet MUST NOT pay or receive through lnv1; it is exposed so that configs decode and its
recovery runs. The `meta` module is not consumed (`FMI-26`).

**FMI-4** A federation MUST have the `mint` and `wallet` modules to pass the structural floor
(`ALC-14`), and MUST have `lnv2` to be eligible at all: every money primitive requires the lnv2
module and MUST fail without it, and a federation without it has no available gateway
(`ALC-15`).

**FMI-5** `is_mainnet` MUST be derived from the wallet module's network in the
**authenticated** config — true iff it is Bitcoin mainnet — and a config with no wallet module
MUST be treated as not mainnet, for a joined federation and for a previewed candidate alike.
Whether it gates is `Policy.require_mainnet` (`DOM-15`), applied by the scorer (`ALC-14`) and
by discovery (`ALC-28`).

## Clients and partitions

**FMI-6** The wallet MUST hold one live client per open federation, all open at once, each in
its own partition of the client store (`STO-3`); the application journal is the separate store
`STO-1` owns. A money operation on one federation MUST NOT wait for a join, open or recovery of
another (`OVR-3`), and a join or open of one federation MUST NOT wait for a recovery of another
(`FMI-31`).

**FMI-7** One seed, many federations. "Same seed, same funds" is this derivation, which every
implementation MUST reproduce exactly — two wallets that derive differently recover different
ecash from the same twelve words:

| Step | Derivation |
|---|---|
| mnemonic → seed | twelve BIP-39 words; the BIP-39 seed (PBKDF2-HMAC-SHA512, 2 048 rounds) with the **empty** passphrase — 64 bytes |
| seed → root key | HKDF-SHA512 extract: `PRK₀ = HMAC-SHA512(key = "Fedimint Client Salt", data = seed)` |
| one derivation step | from a pseudo-random key `PRK` and a 16-byte `info`, the next key is the first HKDF-expand block: `PRK' = HMAC-SHA512(key = PRK, data = info ‖ 0x01)`. `child(c)` uses `info = "childkey" ‖ u64_be(c)`; `federation(id)` uses `info = id[0..8] ‖ u64_be(0)`, the first eight bytes of the 32-byte `FederationId` |
| root → per-federation client secret | `root → child(0) → federation(id) → child(0) → child(0)` |
| client secret → federation root secret | `→ federation(id)` a **second** time — the client applies its own federation tweak to whatever secret it is given |
| federation root secret → per-module secret | `→ child(0) → child(module_instance_id)`; the module's own keys (blinding keys, contract keys, tweaks) are derived from this secret by the Fedimint protocol |

No device index is part of the path, and the wallet MUST hand the client the per-federation
client secret, never a secret it has already tweaked with the federation id. The seed is stored
as its 16-byte entropy in the client store's client-secret slot (`STO-4`) and MUST never be
overwritten once written.

A store with no seed: `walletd` serve and every standalone verb that needs a client MUST mint a
fresh random twelve-word seed and persist it before use; a present seed MUST be reused; a
present-but-undecodable one MUST abort, never be replaced. `walletd init` and the standalone
journal-only verbs (`history`, `show`, `candidates`, `approve`) MUST NOT touch the seed. Only
`recover` and `walletd mnemonic` MUST refuse to mint (`FMI-33`, `SEC-11`, `HST-5`). A fresh
empty store therefore owns a new seed on first use.

**FMI-8** `join(invite)` MUST behave as follows. A federation that already has a live client is
returned as joined (no network call). One whose registry row (`STO-14`) exists but whose client
is not live is **opened**, not re-joined. One for which a recovery is in progress (`FMI-31`) is
refused. Otherwise the config is previewed under the 60-second bound (`FMI-21`), the wallet
allocates a fresh partition (`STO-3`), joins into it with the per-federation client secret
(`FMI-7`), verifies that the joined federation's id equals the invite's, writes the registry
row, and only then makes the client live; a failed join MUST leave no registry row and MUST NOT
reuse the partition, which is an orphan from then on (`FMI-35`: never collected automatically). A join MUST invalidate
any allocator plan computed over the world before it (`ALC-32`). A user `join` carries no bound
but the preview's. **Auto-join** — and only auto-join — runs under the remaining budget of the discovery pass that
called it (`FMI-22`, `ALC-28`): the preview and the join are each bounded by whichever of that
budget and the 60-second preview bound is tighter, and an elapsed budget is the distinct outcome
"deadline elapsed", not an error; a budget that elapses inside the join leaves no registry row,
exactly as a failed join does.

**FMI-9** Opening every registered federation at startup is best-effort per federation: a
partition that fails to open MUST be warned and skipped, and that federation is
registered-but-unopened (`DOM-2`). The scheduler MUST retry opening it every cycle and MUST fence
planning until it succeeds (`ALC-46`).

**FMI-20** A registered federation MUST never have two live clients on one partition, and a live
client MUST never be replaced by a second open of the same partition (`DEF-17`): however opens
and joins of one federation overlap, exactly one client becomes live, and a concurrent open that
finds the client already live MUST discard its own and use the live one. Money operations MUST
NOT wait for an open or join to complete (`OVR-3`). Before opening a registry row, the wallet MUST skip a federation whose recovery is in
progress or whose client is already live; a row whose invite does not parse is opened by its
partition alone and checked against the live set afterwards.

**FMI-21** The config preview under the join serialization MUST be bounded, at 60 seconds, for
both join and recovery (`DEF-18`).

## Gateways

**FMI-10** A federation's **vetted list** is the set of lnv2 gateway URLs that at least
`threshold` of its guardians each return, where `threshold` is the federation's consensus
threshold (`FMI-24`) — `ADR-0029`: "A federation's vetted list is the set of gateways that at least […] of its
guardians each return, read per guardian […]; the SDK's flattened union, where one guardian
could admit a gateway, is not the list". The wallet MUST read each guardian's list separately
and apply the threshold itself; a guardian that does not answer counts as listing nothing. The
list is ordered by descending number of guardians listing the URL; the order among equally
listed URLs is the implementation's, and MUST be stable within one resolution (the list read
twice while resolving one route gives one order). Every "first" and every tie-break in this
chapter inherits that order. An empty list is a valid list (`ALC-15`: no gateway available).

**FMI-11** Gateway validation is the lnv2 `routing_info` exchange: `POST {gateway}/routing_info`
— the gateway URL with `routing_info` joined as a path segment — with a request body that is the
federation id JSON-serialized as its 64-hex-character string, under a 5-second connect and
10-second total bound. A `200` body is JSON `Option<RoutingInfo>`: `null`, or
`{lightning_public_key, lightning_alias?, module_public_key, send_fee_minimum, send_fee_default,
expiration_delta_minimum, expiration_delta_default, receive_fee}`, where `module_public_key` is
**required** (a body without it is a decode failure), `lightning_alias` is optional and omitted
when absent, and each fee is `{base: <msat integer>, parts_per_million: <integer>}`. The
outcome is tri-state: a decoded `RoutingInfo` means the gateway **serves** that federation; a
`200` with `null` means it answered and does **not**; a transport failure, any non-`200`
status (an lnv1-only gateway's `404` included) or a decode failure means it is
**unavailable**. A selection MUST treat the last two alike — the candidate is skipped
(`FMI-12`) — and neither is an error of the operation; what a named gateway's refusal does to
a pay or receive is `FMI-16` and `FMI-17`. Where the request may go is `FMI-40`.

**FMI-40** The wallet MUST NOT let a guardian direct its egress. Before any gateway request
(`FMI-11`, and every quote or payment call to a gateway) the wallet MUST reject a URL whose
scheme is not `http` or `https`, MUST NOT follow redirects, and MUST treat as **unavailable** —
without connecting — a URL whose host is a link-local address (`169.254.0.0/16`, `fe80::/10`),
the cloud-metadata address `169.254.169.254`, or a loopback, RFC 1918 or unique-local address.
A host MAY offer an explicit configuration that permits private-network gateways — a test
environment's gateways are on loopback — and that configuration MUST default to off and MUST
NOT affect the link-local and metadata rule. A hostname MUST be resolved and the rule applied
to every address it resolves to; the address actually connected to MUST be one the rule
approved (connect to the resolved address, or re-apply the rule at connect time), so a name
that re-resolves between check and connect gains nothing; and an IPv4-mapped or
IPv4-compatible IPv6 address (`::ffff:a.b.c.d`, `::a.b.c.d`) MUST be judged as the IPv4
address it carries. A URL so rejected is never on the vetted list for selection
purposes and is never counted as a validating gateway (`07-security-requirements.md`, threat
model: a malicious or misconfigured guardian).

**FMI-12** Automated selection MUST choose the **cheapest** validated candidate (`DEF-5`). The
candidate set is the federation's vetted list (`FMI-10`), or the single break-glass gateway when
one is armed for this intent's key (`FMI-14`): for a raw pay, the **source** federation's list,
keeping the cheapest gateway whose gateway-plus-federation send quote fits the cap; for a raw
receive, the **destination**'s list, keeping the cheapest whose receive quote fits; for a
planned move, the cheapest `Routable` candidate by modelled fee (`ALC-13`); for a move whose
amount is final, every candidate on the **destination**'s list that serves the route (`FMI-13`)
is priced at that amount within a 10-second budget and the cheapest that fits is kept. A candidate whose gateway or federation
quote errors is skipped silently. Ties keep the **first-seen** candidate — a later candidate
replaces the incumbent only on a strictly lower total — so among equal-priced gateways the choice
follows `FMI-10`'s order.

**FMI-13** A gateway **serves** a route for a move only when it is on the vetted list of **both**
federations and answers `routing_info` with a `RoutingInfo` (`FMI-11`) at **both** ends —
`ADR-0029`: "Shared candidates come from the INTERSECTION of both federations' vetted lists".
Membership MUST be tested at resolution time, not only at planning time, so a gateway the source
federation has since revoked MUST NOT carry an automated move, and a route hint (`CONTEXT.md`
**Route hint**) holds only while it is on every list it needs to be on. The one gateway that may
travel a route without list membership is the operator's break-glass (`FMI-14`), and it still
MUST answer `routing_info` for the source federation before anything is minted (`ADR-0030`).

**FMI-14** Gateway precedence for a move, in order:

1. The operator's **break-glass**, when this invocation armed one for THIS intent's key
   (`CONTEXT.md` **Break-glass gateway override**), taken without a membership test —
   `ADR-0030` §4, "Committed routes replay; drafts never do": a **committed** route
   (`CONTEXT.md` **Committed route**: the record has a committed leg — an invoice minted or a
   send issued — whether held in the cache or recovered from the operation log) replays as
   recorded, flag or no flag; only a draft yields to the break-glass. A committed leg recovered
   from the operation log with no recorded route — one committed before the route was
   persisted with the leg (`STO-33`) — has none to replay and is treated as a draft here
   (`OPS-20`).
2. The action's route hint, if it still holds (`FMI-13`).
3. If the amount is final: the cheapest fitting candidate on the destination's list at that
   amount (`FMI-12`). If every candidate was priced and none fits the cap, the outcome is
   `Retryable` **without** trying step 4, so a tight cap keeps the move `Pending` even when a
   validating gateway exists; only a budget-truncated scan, or one in which nothing could be
   priced, falls through.
4. The first gateway on the destination's vetted list, in `FMI-10`'s order, that serves the
   route (`FMI-13`).
5. None → `Retryable`, never `Permanent`, so the intent stays `Pending` and a later run with a
   break-glass can resume it.

An evacuation tries its route classes in `ADR-0029`'s order — "swap first, hop only when no
shared gateway serves THIS attempt" (`OVR-13`) — and sizes each inside the same attempt
(`ALC-21`); probes and route economics consult the vetted list only, and the light probe's
`gateway_available` is true when any gateway on the list, scanned in the same order, serves.

**FMI-42** A gateway that quoted and did not **perform** MUST be set aside — `ADR-0029` §3: "A
bounded, in-memory set-aside with a skip-until time, written on a PERFORM-level failure only and
consulted by both route classes and by `Move`". The record is as wide as what the failure
proved: an endpoint failure (a rejected receive, a hang past the per-request bound, a refunded
send on a shared route) marks `(federation, gateway)` at the end that failed, a shared route's
failure marking the gateway on both federations; a hop's refunded send marks the route
`(source node key, destination node key)` and nothing else. An empty sizing result MUST NOT
write the record. The record is not persisted, and the skip-until duration is a constant of the
implementation, not a `Policy` field. A set-aside gateway does not serve (`FMI-13`) and a hint
naming it does not hold.

**FMI-15** A **direct inflow** is a receive-only move whose invoice is grossed up so the
destination is credited `amount` after gateway and federation receive fees — **never more, and
possibly less by a bounded shortfall**: the gross-up (`FMI-18`) MUST produce an invoice the
wallet has verified never over-credits and, when the federation's step fee prevents an exact
solution, the best verified under-crediting candidate, so the shortfall is bounded by one
receive-fee step of that federation plus the federation's mint output fee on the claim, which
the lnv2 receive quote does not include; `CNF-10` demonstrates it within 1 000 msat. The external payer pays the
invoice amount. A raw **receive** invoices `amount` and the recipient nets `amount` minus fees.
The two are different verbs with different ledger semantics (`STO-15`).

## The Lightning legs

**FMI-16** An lnv2 `receive` is **not idempotent**: each call creates a fresh incoming contract,
invoice and operation. The wallet MUST persist the `(operation id, invoice)` pair the moment the
call returns and MUST find an orphaned one by its correlation key in the operation's metadata on
resume (`OPS-18`, `STO-34`). Every receive the wallet issues MUST carry: invoice expiry
3 600 seconds, the **empty** description, and an explicitly chosen gateway (`FMI-12`). The
protocol refuses the receive, and the wallet MUST treat the refusal as `Retryable`, when the gateway's fresh `routing_info` says it
does not serve the federation, when its `receive_fee` exceeds the limit (`FMI-19`), or when the
contract `amount − receive_fee(amount)` is below the lnv2 minimum incoming contract of
5 000 msat — which the wallet MUST pre-check itself (`OPS-18`).

**FMI-17** An lnv2 `send` is deduplicated by an operation id the protocol derives from the
invoice: one payment attempt per invoice per client. A second `send` of the same invoice MUST
NOT fund a second outgoing contract; it reports the original operation, which the wallet MUST
attach to as **already in flight** rather than treat as an error. Re-issuing a send after a crash
therefore cannot double-pay as long as the source client's store survives; a seed recovery
mid-send discards that dedup and is the one real double-pay hazard (`FMI-32`). The wallet always
names the gateway. The protocol's own pre-fund refusals, and the class each MUST take
(`OPS-17`):

| Refusal | Condition | Wallet class |
|---|---|---|
| duplicate attempt | the invoice's operation already exists | already in flight — an outcome, not an error |
| invoice has no amount | | `Permanent` (invoice defect) |
| invoice expired | | `Permanent` (invoice defect) |
| wrong currency | invoice network ≠ the federation's network | `Permanent` (invoice defect) |
| federation not served | the gateway's `routing_info` returned `null` | `Permanent` (route defect) |
| gateway fee over limit | the send fee schedule exceeds the limit (`FMI-19`) | `Permanent` (route defect) |
| gateway expiration over limit | the gateway's expiration delta exceeds 1 440 blocks | `Permanent` (route defect) |
| gateway unreachable, consensus read failed, funding failed | transport, consensus-read or funding fault | `Retryable` |

A failure before the protocol call: an unparseable invoice is `Permanent` (an input defect that
no retry changes); an unparseable gateway URL or a missing lnv2 module is `Retryable`.

**FMI-18** Fee shapes. A gateway fee is `base + floor(amount × parts_per_million / 1 000 000)`,
the multiplication saturating in `u64` before the division — the protocol's `PaymentFee`. The
receive gateway fee is `routing_info.receive_fee`; the send gateway fee for a concrete invoice
is `send_fee_minimum` when the invoice's payee node key equals the gateway's
`lightning_public_key` (an internal swap) and `send_fee_default` otherwise, with the matching
`expiration_delta`. Before an invoice exists the wallet assumes the swap fee (`send_fee_minimum`)
for a shared route and the default fee for a hop leg (`ADR-0029`). Federation fees are the
federation's receive quote on the contract and send quote on the outgoing contract, each read as
the total in msat; the send quote selects real notes and can fail on insufficient balance.
`gross_up(net, gateway_fee, fed_fee)` is the smallest invoice amount such that `contract =
invoice − gw(invoice)` and `contract − fed(contract) ≥ net`; it has no solution when
`parts_per_million ≥ 1 000 000`. Because the federation fee is a step function of the contract,
the committed contract MUST be re-verified against the quote before the invoice is surfaced
(`OPS-23`).

**FMI-19** The protocol bounds what a gateway may post as its fee schedule: a send schedule
above `{base: 100 sat, parts_per_million: 15 000}` or a receive schedule above `{base: 50 sat,
parts_per_million: 5 000}` MUST be refused. "Above" is **component-wise**: a schedule is within
the limit iff its `base` is within the limit's base **and** its `parts_per_million` is within the
limit's — never a lexicographic comparison that stops at `base`, under which a gateway below the
base limit passes with any `parts_per_million` and the intended 1.5 % and 0.5 % envelopes do not
bind. The class each refusal takes is `FMI-16`'s and `FMI-17`'s. This is an admission filter on the posted schedule; the fee caps that bind **on the amount** are
the wallet's own (`OPS-29`, `SEC-7`).

**FMI-22** Bounds at the federation and gateway boundary. Each is a requirement; its owner is
named where it is not this chapter's:

| Boundary | Bound |
|---|---|
| config preview for join and recovery | 60 s (`FMI-21`) |
| discovery config preview | the watch policy's per-preview timeout, clipped to the pass budget (`ALC-28`) |
| auto-join | the remaining discovery pass budget (`FMI-8`) |
| `routing_info` request | 5 s connect, 10 s total (`FMI-11`) |
| invoice expiry | 3 600 s (`FMI-16`) |
| a federation-API wait while driving an intent | 5 min at the transport, then re-issued (`FMI-38`) |
| per-intent perform | the host's perform timeout (`OPS-15`, `HST-9`); never applied to join or recover |
| fallback route scan | 10 s (`FMI-12`) |
| route pricing per tick | `ALC-13` |
| Observer request | 20 s, 1 MiB body (`FMI-28`) |
| module recovery | fails after 600 s without progress (`FMI-30`) |

**FMI-23** A gateway that quotes but does not perform produces one of three outcomes, and the
wallet MUST NOT retry any of them through another gateway within the same operation: an invoice minted
and never funded expires after 3 600 seconds (a direct inflow stays `Awaiting` until then); a
send funded and never completed is refunded by the protocol's send state machine on gateway
forfeit or expiry, and the move terminalizes `Refunded`; a send that succeeds while the receive
reaches a terminal non-claim is `Stranded` (`OPS-27`). "Forfeit ⇒ `Refunded`" is the normal
case, not a guarantee: when a refund does not finalize — the refund transaction rejected because
the gateway claimed the outgoing contract after all, or accepted and the note issuance then
failed, which the wallet cannot tell apart (`FMI-37`) — the protocol re-reads the preimage one
last time and, if one verifying against the contract is there, the send is `Success`; a
forfeited send can therefore be promoted to a settled send and, meeting a non-claimed receive,
land `Stranded`. With neither a refund nor a preimage the send is `Failure` (`FMI-37`). The
gateway is set aside (`FMI-42`).

**FMI-37** What an lnv2 terminal `Failure` proves, and what it does not. The protocol folds two
distinct outcomes into each `Failure` terminal, and the wallet cannot tell them apart from the
operation state:

| Leg | `Failure` is reached when | Money position |
|---|---|---|
| send | (a) the **funding** transaction was rejected, nothing was funded; or (b) the refund did not finalize — the **refund** transaction was rejected, or it was accepted and note issuance then failed — **and** no verifying preimage was available (`FMI-23`) | (a) nothing moved; (b) the outgoing contract WAS funded and its position is unresolved |
| receive | the **claim** transaction was rejected and the retries `FMI-41` requires are exhausted (this wallet claimed nothing, which does not prove the contract is unclaimed), or it was accepted and note issuance then failed | unknown whether the incoming contract was consumed |

The wallet MUST record the send case with an error beginning `send failed:` and the receive case
with one beginning `receive failed:`; the two prefixes are the operator's anchors (`HST-28`) and
MUST NOT change. A move whose error starts `send failed:` is NOT evidence the money stayed put
(`OPS-27`). `Expired` on a receive and `Refunded` on a send are the only terminals that establish
the funds' position.

**FMI-41** A funded incoming contract the wallet has not claimed MUST remain claimable by the
wallet: a claim whose transaction is rejected MUST be retried until the contract's expiry has
passed before the receive reaches its terminal `Failure` (`FMI-37`) — so the transition
`OPS-27` maps from that terminal is reached only once the retries are exhausted — and the
wallet MUST provide an explicit re-claim, invocable for one operation by its operation key
(`API-42`), that claims an incoming contract the federation still holds funded and unclaimed —
the receive leg of a `Stranded` move included — and reports "not claimable" when the contract
is expired or already consumed. This is the recovery path for `Stranded`; it runs only after
`HST-28`'s evidence-preservation procedure, and it does not contradict `DEF-20`, because it
claims what the federation holds rather than reasoning from the preimage about what happened.

## Recovery

**FMI-30** Recovery is an explicit verb (`POST /v1/recover`, `wallet-cli recover`) with
**complete-or-fail** semantics: it MUST end in exactly one of two states — every exposed module
recovered and the federation registered, or failed with nothing registered — and MUST NOT park
indefinitely. A module recovery that fails MUST surface as the recovery's failure (`ADR-0025`:
"Recovery must be able to fail, not hang"), and a recovery MUST fail once no module has made
recovery progress for **600 seconds** — an unreachable federation makes none — rather than retry
the transport forever. Any error before the final commit leaves the fresh
partition unregistered, and a retry allocates the next partition. Every recovery error is
`Permanent` for the intent. A crash mid-recovery leaves the intent `Executing`; reconcile
re-drives it into a clean fresh partition or hits the refuse-if-registered guard (`DEF-15`).
"Unregistered" is not "empty": a failure after the modules have recovered and before the
registry row is written abandons a partition that already holds the seed's recovered notes; it
is never opened, because no registry row names it (`FMI-35`), and the retry recovers the same
notes into the next partition.

**FMI-31** The sequence, as observable: the wallet MUST refuse a recovery for a federation with a
registry row, open **or** unopened (`ADR-0025` §2); MUST reserve the id so that a `join` or an
open of that federation is refused while the recovery runs (`FMI-8`, `FMI-20`); MUST preview the
config under the 60-second bound (`FMI-21`); MUST allocate a fresh partition (`STO-3`) and
recover into it from the seed (`FMI-7`) with no federation-stored backup snapshot (`FMI-32`);
MUST treat "every module recovered" as the sole completion authority — recovery progress is a
signal, never completion — and MUST NOT hold joins and opens of other federations while it
waits for it (`FMI-6`); MUST verify the recovered federation's id equals the invite's; MUST
let every state machine the recovery started run to completion before the client is used; and
MUST, in **one** journal transaction, write the registry row, terminalize the intent `Done` and
write a `UserApproved` candidate (`STO-26`), making the client live with no other write between.

**FMI-32** What is recovered is what the protocol's module recovery rebuilds from the seed by
history replay: ecash and module state. The wallet MUST NOT rely on a federation-stored backup
to shorten the replay or to carry anything else. **Not** recovered: the operation log (the
cross-restart send-dedup authority), the journal and ledger, the federation list, in-flight
moves. This is why a registered federation is refused: a surviving journal with a non-terminal
pay plus an empty operation log is a double-pay (`ADR-0025`).

**FMI-33** Recovery MUST never be automatic and MUST never be a side effect of a join (`DEF-15`).
The partition rule is never-wipe: recovery into an initialized partition is refused by the
protocol, so in-place recovery would need a wipe with a crash window, and the wallet MUST NOT
wipe; orphaned partitions accumulate (`FMI-35`). `recover` MUST refuse a store with no seed
(`FMI-7`), because minting one there would rebuild an empty wallet under a bogus root and
occupy the slot a later `restore-mnemonic` needs.

**FMI-35** Orphaned client partitions — from a failed join, a failed recovery, or a lost
registry — MUST never be reused and MUST never be collected automatically; reclaiming them, if
offered, is a deliberate operator command (`ADR-0025`).

## Signals a federation emits, and what the wallet does with them

**FMI-24** From the authenticated `ClientConfig`: `guardian_count` is the number of API
endpoints; `threshold` is the federation's consensus threshold `n − floor((n − 1) / 3)` in
integer arithmetic (equal to `2f + 1` only when `n ≡ 1 mod 3`), and `0` when there are no
endpoints; module kinds are the `kind` string of every module entry, in module-instance-id
order; `has_lnv2`, wallet-module presence and `is_mainnet` (`FMI-5`) follow. The scorer rejects
a threshold below the BFT bound (`ALC-14`).

**FMI-25** Liveness is one `session_count` threshold read: success is `quorum_live`, its
wall-clock is `latency_ms`. A federation whose light probe **errors** is dropped from the
snapshot with a warning and is therefore neither scored nor evacuated that cycle (`ALC-48`).

**FMI-26** Shutdown is derived from three signals with a 24-hour trigger lead (`ALC-19`) —
`ADR-0019` ranks them, "`status.scheduled_shutdown` (consensus-reported, strong) primary;
`federation_expiry_timestamp` meta secondary"; the corroboration rule and the lead are this
set's: the merged meta `federation_expiry_timestamp` (which the federation's
`meta_override_url` host can serve, so it is **untrusted**, never schedules alone, and is warned
when uncorroborated); the at-join consensus config meta `federation_expiry_timestamp`; and
per-peer `/status` `scheduled_shutdown`, corroborated when `f + 1 = floor((n − 1) / 3) + 1`
peers report it. The meta module's consensus value is not an input (`FMI-3`). The combination
is pure in its inputs: a corroborated `/status` signal alone schedules; else a config expiry
within the lead schedules; the override-served expiry is read and **never** schedules on its
own. Mechanics:

- The config value is the config's global meta `federation_expiry_timestamp`, parsed as unix
  seconds from a trimmed plain decimal, a JSON number, or a JSON-quoted decimal; anything else
  is absent.
- A corroborated expiry schedules when `now + 86 400 ≥ expiry`, which includes an expiry
  already in the past.
- The `/status` signal is read from each peer in turn; a peer counts when its response carries a
  `scheduled_shutdown`, whatever session index it names; a transport or decode error counts as
  no signal and is warned; the scan stops at `f + 1` reports. Fewer than `f + 1` reports warn
  and do not schedule.
- The wallet MAY subscribe to the meta field's updates to **wake** the scheduler (`ALC-19`); a
  wake is never a trigger.

The runtime-mutable `Policy.evacuation_lead_secs` (default one hour) governs only when the
scheduler wakes, not when an evacuation triggers (`ALC-19`).

**FMI-27** Balances per federation: the **spendable** balance is the client's spendable ecash,
and is the only balance the allocator reads; the **in-flight** amount is the sum, in msat, of
the invoice amounts of the wallet's lnv2 sends that have no terminal outcome yet (an amountless
invoice adds 0; receives add nothing). Because a terminal outcome is known only once the wallet
has observed it, a freshly reopened client MAY over-report in-flight until it re-subscribes;
the value is advisory and MUST NOT be an input to an allocator decision.

**FMI-28** The Fedimint Observer is a discovery source only (`ADR-0020`): `GET
{base}/federations`, the base with trailing slashes trimmed, under a 20-second total bound; a
non-2xx status, a `Content-Length` above 1 MiB, or a streamed body exceeding 1 MiB is a source
failure. Parsing: an empty body is a healthy empty result; otherwise the body MUST be a JSON
array or an object with a `federations` array, else a source failure; each row needs string `id` and
`invite` — `id` parsed as a 64-hex federation id, `invite` as an invite code — with optional
string `network` kept as a hint; a row that fails any of these is skipped silently. A candidate
MUST be dropped unless its claimed `id`, the invite's embedded id and the previewed config's
computed federation id all agree. Every candidate's config is re-fetched by preview before it
is scored; nothing the Observer says is load-bearing.

**FMI-43** Nostr is a discovery feed at most (`ADR-0019`): a Nostr announcement MAY be a
candidate source with the same Sybil check as `FMI-28`, and Nostr ratings MUST NOT be a trust,
scoring or shutdown input. No requirement in this set produces a `Nostr` candidate (`DOM-12`).

**FMI-36** Transport. The wallet MUST support the iroh, WebSocket and HTTP federation
connectors, and MUST NOT route any of them over Tor (`OVR-12`); the same connector set serves
preview, join, open and recovery. Which transport a federation is reached over is decided by
its invite code and config, not by the wallet, and the connector configuration — which
transports exist and how they are wired — MUST NOT be read from the process environment; the
standard proxy variables are host environment, not connector configuration, and `HST-2` owns
them with the rest of the environment surface. The bound
on a wait over any of them is `FMI-38`.

## The active probe at the protocol level

**FMI-34** An active probe is two real `Move` intents through the ordinary move path: leg **in**
mints `probe_amount` (default 20 sats) on the candidate, paid by an lnv2 send from the source;
leg **out** redeems an affordably sized delta back, with the leg fee cap `max_fee` (default 10
sats per leg in the standalone verb). The candidate's baseline balance is sampled before leg in
so the exact delta can be isolated, and a no-sweep guard requires the candidate to hold exactly
`baseline + delivered_in` before leg out is journaled (`ALC-27`).
