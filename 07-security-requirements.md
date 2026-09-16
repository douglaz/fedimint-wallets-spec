# 07 — Security requirements

The threat model the wallet is built against, and the controls a compliant wallet MUST hold
against it. Each control is a behaviour observable at a boundary — the data directory, the
daemon's listener, what leaves the host for a federation or gateway — and cites the requirement
that owns its mechanics. Where the set decides *not* to defend against something, the decision
and its ADR are named here rather than left implicit.

## Threat model

The assets are the seed (which is the funds), the bearer token (which is every operation), and
the ledger (which is the user's whole payment history). Adversaries, in descending order of how
much the design defends against them:

1. **A network adversary between the wallet and a gateway or guardian.** Defended by the
   protocol: blind signatures, hash-locked legs, guardian-verified preimages. The wallet adds
   the never-over check (`OPS-23`) and validates every gateway's `routing_info` at each end
   (`FMI-13`).
2. **A misbehaving or malicious gateway.** It sees both legs of every move (`SEC-13`) and can
   quote without performing; the wallet bounds the loss to one operation's amount and
   terminalizes honestly (`FMI-23`). A move it carries strands only when its send settles and
   the receive reaches a terminal non-claim (`FMI-23`, `OPS-27`).
3. **A malicious or misconfigured guardian.** Cannot place a gateway in the vetted list on its
   own (`SEC-17`, `FMI-10`); with enough colluding guardians can list any URL, so the wallet
   restricts where a gateway request may go — loopback, link-local, RFC 1918, cloud metadata
   (`FMI-40`); can serve a false shutdown notice through the overridable meta field, which the
   wallet requires corroborated (`FMI-26`); cannot forge the authenticated config the wallet
   re-fetches (`FMI-28`).
4. **A poisoned discovery feed.** Every candidate's config is re-fetched and structurally
   scored, the Sybil check requires three ids to agree, and nothing is funded before a
   sats-spending probe passes (`ALC-28`, `ALC-37`).
5. **Another process on the same host, or a reader of a copy of the data directory.** Defended
   as far as `SEC-25` reaches: the seed is not readable from the directory alone. Everything
   else in it — the ecash notes in the client store, which are spendable bearer instruments;
   the ledger; the bearer token — is protected by the operating-system user boundary (`SEC-1`)
   and nothing else. The operator's own controls (host disk encryption, a balance ceiling) are
   outside this set.

Explicitly not defended against: a compromised operating-system user; a compromised host,
including the memory of the running process (the wallet is not required to wipe secrets from
memory); a copy of the data directory run as a second wallet (`SEC-23`); network-level
deanonymization (no Tor, `ADR-0002`, `SEC-19`); and a compromised build or dependency, whose
provenance is the code repository's concern.

## The trust boundary

**SEC-1** The trust boundary is the operating-system user. The daemon MUST bind loopback by
default (`SEC-3`) and MUST authenticate every request with one bearer token (`API-2`), which
`init` writes to a file with mode `0600` (`API-3`, `HST-19`), by default inside the data
directory, at the path `HST-4`'s precedence resolves. On every start the daemon MUST re-assert
the data directory's `0700` mode (`HST-19`); the token file's protection is that directory's,
and the wallet is not required to re-check the file's own mode when it reads it — an operator
who configures a `token_path` outside the data directory owns its mode. Anything that can read
the token file, or the data directory, can do everything the wallet can; no requirement in this
set defends against it.

**SEC-2** The token MUST be 32 bytes from a cryptographically secure random source, rendered as
64 lower-hex characters (`API-3`), written with mode `0600` (`HST-19` owns how it reaches
disk), and never logged (`SEC-6`). It never expires and is rotated only by re-running `init`
while the daemon is stopped; `init` against a running daemon MUST block on the store lock
rather than rotate the token underneath it (`API-3`). The daemon MUST compare a presented token in constant time over its content
after an early return on a length mismatch — the token's length is observable, its bytes are
not — and MUST answer every failure with `API-2`'s `401`.

**SEC-3** The daemon MUST bind `127.0.0.1` unless configured otherwise (`HST-3`, `address`). The
wallet provides no transport security — no TLS, no rate limiting, no CORS handling (`API-1`
owns those absences and the request bounds the set does require: `API-35`, `API-11`,
`API-21`) — so on a non-loopback bind the bearer token crosses the network in cleartext and a
passive observer can replay it against every route. An operator who binds beyond loopback has
extended the trust boundary to the network with a static bearer token; the only non-loopback
exposure this set treats as safe is an authenticated tunnel in front of a loopback bind. A
CLI frontend sends the token to the daemon URL the operator configured (`API-25`); the set
places no loopback or scheme restriction on that URL, because a tunnel's or overlay's local
end is where the CLI legitimately reaches a remote daemon (`ADR-0028`: "via a private overlay
(Tailscale/WireGuard) or their own reverse proxy"). The browser sidecar is the exception and
accepts a loopback IP literal only (`SEC-22`).

**SEC-4** No route is reachable without the token, `/v1/health` included (`API-2`), and an
authenticated `/v1/health` answers `200` whatever the wallet's readiness (`API-16`): an
unauthenticated uptime probe cannot use it, and an authenticated one learns nothing from the
status code alone.

**SEC-5** Configuration files MUST hold no secret. `walletd.toml` holds paths and the bind
(`HST-3`); the CLI's pointer file holds the token's **path**, never the token (`HST-4`); both
MAY be written under the ambient umask. The one exception is the sidecar's `wallet-web.toml`,
which holds an Argon2id password hash and MUST therefore be written `0600` (`HST-19`) and
MUST be refused at every start unless its mode and its directory's ownership and mode pass
`HST-26`'s checks.

**SEC-6** The wallet MUST NOT write the seed, the bearer token or a password to any log line
at any level, nor into any error returned to a caller, and MUST NOT log a full invoice at its
default log level. The one exception is `walletd mnemonic`, which prints the twelve words to
stdout while the daemon is stopped (`HST-5`); `restore-mnemonic` takes them from stdin only
(`SEC-11`), never from an argument. A `500` body carries the storage fault's text verbatim and
MAY contain filesystem paths and the data directory — paths are not secrets under `SEC-1`,
which is why `API-37` forbids a frontend from showing that body to an untrusted party.

## The seed

**SEC-25** The seed MUST NOT be stored in plaintext. What the wallet persists is the twelve
words' entropy (`STO-4`) under an AEAD, keyed by a key that is not stored beside it — `ADR-0026`:
"the seed must not be readable from the data directory alone. The key therefore has to come
from **outside** the encrypted store". When the key source is unavailable at start the wallet
MUST fail closed — it MUST NOT serve, MUST NOT mint a seed (`SEC-11`) and MUST NOT fall back to
plaintext ("fail closed, do not fall back to plaintext"). `walletd mnemonic` and
`restore-mnemonic` MUST keep working under encryption ("decrypt on demand"): export decrypts,
restore stores the entropy encrypted (`SEC-11`). A store that holds the entropy in plaintext,
from before this requirement, MUST be re-encrypted once, in one store transaction, on the
first start that has the key ("A one-time re-encrypt of the existing plaintext store on
upgrade"); the wallet MUST tell a plaintext slot from an encrypted one without the key, so
that a start without it refuses rather than mints. That re-encryption is the one write this
set exempts from `OVR-14`'s rollback rule — `ADR-0026`: "greenfield — a migration step, not
a serde compat layer" — and the exemption is bounded: a build that predates this requirement
MUST fail to start on a re-encrypted store, and MUST NOT open it as a wallet on a fresh or a
wrongly derived seed. Where the key comes from — an operator passphrase through a memory-hard
KDF, or a key wrapped by an external key-management service — is `ADR-0026`'s
*recommendation*, not its decision; this requirement is silent on it, and the encrypted slot's
layout (its discriminator, nonce and ciphertext, and where the key source's own parameters
live) is fixed under a `STO` identifier with that decision. Whichever it is, the seed's
protection reduces to the protection of the key source.

**SEC-11** A wallet started to serve on a store with no seed MUST mint a fresh twelve-word seed,
stored as `SEC-25` requires, and a seed once stored MUST never be replaced (`STO-4`; `SEC-25`'s
re-encryption changes the slot's representation, never the entropy).
`restore-mnemonic` (`HST-5`) MUST refuse when a seed already exists, checked before the words
are parsed; MUST read the words from stdin only, with all whitespace collapsed; MUST require a
valid BIP-39 checksum and **exactly twelve words**; and MUST write nothing on any failure.
Because serving mints, the order is `init → restore-mnemonic → serve`; reversed, the wallet
serves on a fresh seed and the restore is refused.

**SEC-12** What a lost store costs — `client.db` the seed and the send-dedup state,
`journal.db` the federation list and the ledger — and that no backup of either is required of
the wallet, is `STO-28`. What the operator holds instead is `SEC-24`.

**SEC-23** One seed, one live client store, one process — `ADR-0025`: "there is one seed, one
live client store, one daemon". The wallet MUST hold an exclusive lock on its data directory
while any process has the stores open, so a second process on the same directory blocks or is
refused (`HST-9`). The lock excludes only that directory: a restored copy of the stores, a
cloned volume or a copy of the directory at any other path — on this host or another — carries its own lock and
runs as a **second spender of the same notes**. The federation lets exactly one of them win
each spend, both processes' bookkeeping is then false, and a send re-driven from the copy
misses the original's dedup state (`FMI-32`). The wallet is not required to detect this; the
invariant is the operator's to hold, and the stranded-move procedure in the code repository's
runbook assumes it. This is a money-loss rule, not a confidentiality one.

**SEC-24** The recovery unit the operator MUST hold outside the wallet is the twelve-word seed
(`walletd mnemonic`, daemon stopped, `SEC-6`) **plus the invite code of every joined
federation** (`wallet-cli list-feds`), re-recorded after every join. Recovery (`FMI-30`) takes
the seed and one invite per federation and nothing else; the seed alone recovers ecash only in
federations whose invites the operator still has. An invite is not secret **unless it carries
the optional `api_secret` part**, which the SDK sends as guardian API authentication: such an
invite is a live credential and MUST be stored and shared as one. `journal.db` is bookkeeping
and is not part of the unit (`ADR-0025`).

## Money-path controls

**SEC-7** Every fee cap that binds **on the amount** is the wallet's own (`OPS-29`). The
protocol's limits on a gateway's posted fee schedule are `FMI-19`'s — compared component-wise,
an admission filter on the schedule, not a bound on what a payment costs — and the class each
refusal takes is `FMI-16`'s and `FMI-17`'s. The wallet selects by its own cap (`FMI-14`),
and a selected gateway whose schedule is over the protocol's limit fails the attempt in that
class rather than being skipped for the next candidate. A move MUST be refused before minting
if the receive leg alone exceeds the cap, and again before paying if both legs do (`OPS-29`).

**SEC-8** A committed receive whose contract differs from the quote MUST be refused before the
invoice is surfaced (`OPS-23`); a gateway that lowers its fee between quote and mint cannot
over-credit the wallet, and one that raises it cannot make it pay more than the cap.

**SEC-9** No operation is admitted whose source cannot cover `amount + fee_cap` after
reservations, and none whose destination would exceed the per-federation cap (`OPS-7`), except
that an evacuation has no source check by design and is sized at perform time (`OPS-21`).
Whether there is an aggregate ceiling across federations is open (`11-open-questions.md`,
question 2); the set is silent on it.

**SEC-13** A gateway that carries a move sees both legs and therefore learns the wallet's
cross-federation movement pattern. The set requires no gateway diversity and gives the
operator's own gateway no standing preference: a gateway carries a move only in `FMI-14`'s
precedence, where an operator's gateway appears solely as the break-glass armed for one
intent. Independence is claimed for nothing here, as
`ADR-0006` already holds for federations — "**best-effort diversification** across two
distinct federations, NOT a verified-independent sudden-death guarantee".

**SEC-14** Shutdown signals are trusted only when corroborated: the merged meta expiry (which a
federation's override host can serve) never triggers an evacuation alone; the at-join consensus
meta or `f+1` peers' `/status` do (`FMI-26`).

**SEC-15** The Fedimint Observer is a discovery source and nothing else; no field it returns
reaches a scoring or funding decision without a re-fetched, authenticated config (`FMI-28`,
`ADR-0020`).

**SEC-16** A federation the agent joined is fundable only after a sustained window of real
round-trip probes, and a pin does not bypass that gate (`ALC-37`). A user's own `join` is
trusted as the user's decision — **except** over a federation the agent already auto-joined,
whose candidate row stays agent-owned and probe-gated until the audited `approve` verb releases
it (`OPS-42`; seed recovery cannot, since it refuses a registered federation, `FMI-31`).

**SEC-17** The vetted gateway list is the threshold-vetted, per-guardian list `FMI-10` defines,
so no single Byzantine or misconfigured guardian can place a gateway in the automated candidate
set, and a gateway serves a route only while it is on both federations' lists at resolution
time (`FMI-13`). The list's order among equally vetted gateways is the implementation's and is
stable within one resolution (`FMI-10`); where the wallet takes "the first that validates"
(`FMI-14`), the fee cap, not gateway identity, is the money backstop. Where any listed URL may
send the wallet is `FMI-40`.

## Builds

**SEC-18** A release build MUST honour no fault-injection input. The crash killpoints `OPS-28`
demonstrates and the forced shutdown `FMI-26`'s scenarios use MAY be reachable in a debug build
through `WALLET_CLI_CRASH_AT` and `WALLET_CLI_FORCE_SHUTDOWN`; those two are the complete set
(`HST-2` owns the release environment surface), and a release build MUST ignore both. The
conformance scenarios that use them run debug wallet binaries (`CNF-14`).

## Network privacy

**SEC-19** No Tor and no network-level anonymity (`ADR-0002`). Receiving is private (the
gateway cannot tie funds to an identity); sending leaks the destination to the gateway.

## The browser sidecar

**SEC-22** The sidecar MUST enforce its posture before it serves anything (`ADR-0028`). It MUST
bind `127.0.0.1` and offer no other bind ("The wallet ships no public listener, no
certificates, and no renewal story"); MUST refuse to start without a configured Argon2id
password hash validated at pinned minimum parameters ("There is no default credential and no
first-load setup page"); MUST accept a `daemon_url` only when its host is a loopback IP
literal, so a mistyped URL cannot ship the daemon's bearer token to a remote host; MUST apply
`SEC-5`'s file and directory checks at every start; MUST bound sessions by an idle ceiling of
4 h and an absolute ceiling of 24 h that configuration MAY only tighten; MUST canonicalize
`public_origin` to the form a browser sends in `Origin` (`HST-27`); and MUST fail closed on any
configuration defect (`HST-26` owns the checks). Once it serves routes, the request-time
controls are `ADR-0028`'s — an unauthenticated allowlist of exactly `GET /login`, `POST /login`
and `GET /healthz`; a rate-limited login compared in constant time; an `HttpOnly`,
`SameSite=Strict`, host-only session cookie; sessions held in memory only; no `/v1/recover` —
and their surface is `HST-26`'s to specify. Reaching the sidecar from beyond the host is the
operator's overlay or reverse proxy ("Reaching it from a phone is the **operator's** job"), and
behind a proxy the bind is not an authentication boundary: the password is. A sidecar in front
of a wallet that does not meet `SEC-25` MUST NOT be exposed beyond loopback or a trusted
overlay — `ADR-0028`: "Public-internet exposure should wait for ADR-0026".
