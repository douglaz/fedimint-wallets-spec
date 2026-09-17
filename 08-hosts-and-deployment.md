# 08 — Hosts and frontends

How the engine is run: the `walletd` daemon, the standalone one-shot mode, the CLI as a
frontend, the browser sidecar as `ADR-0028` requires it, the data directory on disk, and what
the wallet guarantees an operator after a stranded move. `ADR-0031` names the roles: the
**engine** decides, a **host** drives it, a **frontend** talks to it and never schedules or
admits work. Nothing here describes a build, a repository or a deployment (`ADR-0032`); how an
implementation is built, tested and run in one place is the code repository's.

## The daemon

**HST-1** `walletd` is the only resident host on a server. One process MUST own both stores
under the exclusive lock (`STO-2`); while it does, every other process reaches the wallet
through its HTTP API (`04-api-contract.md`), and a one-shot process that opens the stores
itself (`HST-4`, `HST-9`) does so only while no resident host holds them.

**HST-2** Subcommands: none (serve), `init`, `mnemonic`, `restore-mnemonic`. The host config
file is `$XDG_CONFIG_HOME/walletd/walletd.toml`, else `~/.config/walletd/walletd.toml`;
`--config` overrides. This rule owns the complete environment-variable surface the wallet's
binaries read in a release build (variables the language runtime or a library beneath the
wallet reads are not the wallet's, and the code repository documents them). Every variable
in the table is read in a release build. An empty value counts as unset for every variable in
the table. A variable set to a non-empty value the wallet cannot parse fails startup (`HST-29`),
never falls back silently to a default. Two further variables
exist only in debug builds and are compiled out of release: the fault-injection seams
`WALLET_CLI_CRASH_AT` (`OPS-28`) and `WALLET_CLI_FORCE_SHUTDOWN` (`FMI-26`), owned by
`SEC-18`.

| Variable | Read by | Effect | Empty / invalid |
|---|---|---|---|
| `WALLETD_TOKEN_PATH` | `walletd` (all subcommands) | token file, over `walletd.toml` (`HST-4`) | empty = unset; a relative path, or one that is not a direct child of `data_dir` (`HST-3`), fails startup |
| `WALLETD_PERFORM_TIMEOUT_SECS` | `walletd` serve | the per-intent perform deadline `OPS-15` bounds (`FMI-22`); unset or empty → 600 s, `0` disables it, as for the standalone flag (`HST-9`) | unparseable fails startup (`HST-29`) |
| `WALLETD_SETTLEMENT_STALL_SECS` | `walletd` serve (the standalone mode runs no scheduler) | the settlement-stall deadline `ALC-40` owns, with `ALC-40`'s default; `0` is a zero-second deadline | unparseable fails startup (`HST-29`) |
| `RUST_LOG` | all three binaries | overrides the log level (`HST-8`). The value MUST be accepted as a bare level `error`, `warn`, `info`, `debug` or `trace` — in that order of increasing verbosity, a selected level enabling itself and every more severe one — and this is the whole contract; an implementation MAY also accept a comma-separated list of `<target>=<level>` directives with at most one bare level, whose targets are its own and outside this set | unset → `walletd.toml` `log_level` for the daemon, `warn` for the CLI, `info` for the sidecar; a value that is neither a bare level nor an accepted directive list fails startup (`HST-29`) |
| `XDG_CONFIG_HOME` | all three | config home | empty or relative → ignored, `~/.config` (the XDG base-directory rule) |
| `XDG_DATA_HOME` | `walletd`, standalone `wallet-cli` | default `data_dir` | empty or relative → ignored, `~/.local/share` (the same rule) |
| `HOME` | all three | `~` expansion and the XDG fallbacks | read only when a path actually falls back to it; unset or empty then fails startup, before any file is written (`HST-29`); never read when every path the command touches is absolute (`XDG_CONFIG_HOME` and `XDG_DATA_HOME` absolute, an explicit `--config` whose paths are absolute for `mnemonic` and `restore-mnemonic` — `init` writes the pointer under the config home (`HST-4`) and serve reads it (`HST-33`), so both need an absolute `XDG_CONFIG_HOME` as well; standalone `--data-dir`; or client-mode `--url` with `--token-path`, `API-25`) |
| `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` (and lowercase), `NO_PROXY` | `walletd`, `wallet-cli` | every outgoing HTTP connection the two make — the CLI's connection to the daemon, gateway `routing_info` (`FMI-11`), the Observer (`FMI-28`) — with these semantics: `HTTPS_PROXY` for `https` destinations, `HTTP_PROXY` for `http`, `ALL_PROXY` for either when the scheme's variable is unset; the lowercase form of a variable takes precedence over the uppercase, and an empty variable counts as unset — it neither proxies nor suppresses the fallback; `NO_PROXY` is a comma-separated list of entries, whitespace around an entry trimmed, each a host name (a leading `.` is stripped before matching, so `.example.com` and `example.com` are the same entry and both match the apex and its subdomains), an IP literal or a CIDR block — an IPv4 literal or block MUST be a canonical dotted quad, as `HST-27` requires of an origin host, and any other numeric spelling fails startup (`HST-29`) — optionally `:port` on a name or an IP literal (a CIDR entry carries no port) — an IPv6 literal with a port MUST be bracketed, `[::1]:9736`, and an unbracketed entry with more than one `:` is an IPv6 literal without a port — or `*` for every destination, and an entry exempts a destination whose host equals or is a subdomain of the name, compared case-insensitively, or — for an IP or CIDR entry — whose host is an IP literal equal to or inside it (a host name is matched by name only and is never resolved for the exemption), and whose port matches when one is given — compared against the destination's effective port, the scheme's default when the URL omits it; no destination is exempt that no entry matches, loopback included, so an operator who sets a proxy owns the exemption for the daemon's own address (`SEC-3`). The sidecar is the exception and ignores them (`SEC-22`) | a proxy URL MUST be `http://` or `https://` (an HTTP proxy, reached over plain TCP or TLS respectively; the CONNECT method for `https` destinations) with a host and optional port and nothing else — no userinfo, path, query or fragment; any other scheme or component, or a value that does not parse as a URL, fails startup (`HST-29`) |

**HST-3** `walletd.toml` has five keys and MUST reject any other — including the retired
`gateway` key (`ADR-0030`), so a file that still carries it fails startup loudly:

| key | default |
|---|---|
| `data_dir` | `$XDG_DATA_HOME/walletd`, else `~/.local/share/walletd` |
| `address` | `127.0.0.1` |
| `port` | `9736`; 1 to 65535, `0` failing startup (`HST-29`) — an ephemeral port is one no pointer can name |
| `token_path` | env `WALLETD_TOKEN_PATH`, else the key, else `<data_dir>/token` |
| `log_level` | `info`; one of the five bare levels the `RUST_LOG` row of `HST-2` orders, with the same threshold meaning, anything else failing startup (`HST-29`); `RUST_LOG` overrides it |

Paths MUST be absolute once `~` and `~/…` are expanded; anything else fails startup.
`token_path` MUST resolve to a direct child of `data_dir` — after every filesystem link in
either path is resolved, so a link cannot place one file in two stores, and a direct child
rather than any descendant, so a store nested inside another's directory cannot share its
token — so the token file belongs to exactly one store and its rotation is serialised by that
store's lock (`HST-4`, `HST-33`) — and MUST NOT name `client.db`, `client.db.lock`,
`journal.db` (`HST-21`), the config or pointer file, or `client.toml.lock` (`HST-4`), so a token write can never replace a
store, lock or configuration entry; a path
elsewhere fails startup (`HST-29`). `address`
is not validated: a bare IPv6 literal is bracketed wherever it is rendered into a URL or a
bind string, and a hostname is resolved by the bind. Environment knobs are the table in
`HST-2`.

**HST-4** `walletd init` MUST, in this order: read the config or take its defaults and
resolve and check every path and value it will use (`HST-29`: a failure here leaves nothing
behind); create the data directory `0700`; take the lock and open both stores (`STO-2`: blocking while a resident host holds it, so
the token is never rotated under a running daemon, `API-3`) — and hold it for every write that
follows, the config file included, so two concurrent `init`s serialise as wholes and the
config, token and pointer a daemon and a frontend later read were written by one of them —
and, because two stores may share a config home, it MUST also hold an exclusive lock on
`client.toml.lock` beside the pointer for the whole of the same span, so `init`s of different
stores serialise on the pointer too;
write every config key back canonicalised; seed the default policy row if absent (`STO-13`); mint and write the token `0600`
(`API-3`); and write the CLI's pointer file `client.toml` `{url, token_path}` under the config
home. It does **not** mint a seed (`SEC-11`). A path it cannot resolve, or a host config path that equals, lies under or contains the pointer path, either lock
file (`client.db.lock`, `client.toml.lock`), a store entry or anything inside either store
directory (`HST-21`), or a `data_dir` that equals, lies inside or contains the
host config path, the pointer path or the pointer lock path (`client.toml.lock`), or an
output target — config, token or pointer — that exists but is not a regular file, fails it
with nothing written (`HST-29`) — a config write can never replace a pointer, lock or store
entry. It prints six stdout lines: `initialized walletd`, then `  host config:`,
`  data dir:`, `  token (0600):`, `  client pointer:`, `  api url:` each followed by the
resolved value.
Token path precedence, for every subcommand, is `WALLETD_TOKEN_PATH` (when set and non-empty)
> `walletd.toml` `token_path` > `<data_dir>/token`. On serve the token file MUST be a regular file, not a link, owned by the running user and
with no group or other permission bit, else startup fails (`HST-29`) — a hard link kept by
another user is excluded only by the mode; its contents are whitespace-trimmed and an empty
file fails startup (`bearer token file <path> is empty`).

**HST-5** `walletd restore-mnemonic` reads twelve BIP-39 words from stdin only, refuses if a
seed already exists, and stores the entropy as `SEC-25` requires (`SEC-11` owns the rules).
The order is `init → restore-mnemonic → serve`, because serving on a store with no seed
**mints a random one** when the key source is available and refuses to start when it is not
(`SEC-11`). `walletd mnemonic` prints the twelve words to stdout while the daemon is stopped
(`SEC-6`).

**HST-6** Serve MUST proceed in this order, and a failure at any step exits non-zero with
nothing admitted: load the config → log to stderr (`HST-8`) → re-assert the data directory
`0700` (`HST-19`) → take the lock and open both stores (`STO-2`) → read the token under the
lock (`HST-33`; fail if empty, `HST-4`) → seed or validate the policy row (`STO-13`) → load the seed, or mint one
(`SEC-11`) → open each joined federation's client, tolerating one that fails to open (it is
joined but not open, `DOM-2`; the scheduler's fence B answers for it, `ALC-46`) → **bind the
listener before the scheduler admits any work**, so a port conflict fails startup with nothing
admitted → start the scheduler (`ALC-38`) → serve. The dry run behind `GET /v1/status`
(`ALC-44`) is not bounded by the perform timeout.

**HST-7** Shutdown begins on `SIGTERM` or `SIGINT`, on the listener exiting, or on a critical
service task exiting (which one, in the log). It MUST then, in order: stop admitting
(`ALC-42`; while the listener still runs, new requests get `503` `wallet service is shutting
down`, `API-37`) → abort every
in-flight drive, leaving its intent re-performable (`OPS-15`) → answer every parked long-poll
(`API-11`) with that error → exit. A fatal exit is non-zero, so a supervisor configured to
restart on failure restarts it; a clean shutdown on a signal exits zero.

**HST-33** The daemon MUST read the token only while it holds the store lock. `init` rotates
the token only under that lock (`API-3`), so a daemon that reads it there serves with the
token the last completed `init` wrote, and an `init` racing a start cannot leave the daemon
holding a token no frontend has. The daemon MUST refuse to start when the token path it
resolves (`HST-4`'s precedence, in its own environment) differs from the `token_path` the CLI
pointer names, or when the URL it will serve at differs from the pointer's `url` — both
compared from `walletd.toml` and `client.toml` as re-read after taking the store lock and
`client.toml.lock` (held from before the comparison, and kept), since an `init` completing
before either lock was taken may have replaced what was read before it; and the re-read
`walletd.toml` MUST itself equal the one that selected the store and the token path, else the
daemon MUST refuse to start rather than serve a store its current config no longer names — since every
frontend would then present a different file's token or reach a different address — which is
also what an `init` interrupted between its files leaves behind, and the refusal is how that
mixed state is caught: re-running `init` repairs it. The daemon keeps `client.toml.lock` exclusively for its lifetime, so an `init` of any store sharing the
config home blocks until it stops (`HST-4`), as an `init` of its own store does on the store
lock, and the pointer cannot be repointed under a running daemon.

**HST-8** The daemon MUST log to stderr and to nothing else, at the level `HST-3`'s
`log_level` or `RUST_LOG` selects. Redaction is `SEC-6`'s: no code path logs the token, the
seed or a password. `walletd mnemonic` prints the seed to stdout by design.

**HST-29** A misconfiguration fails loudly and leaves nothing behind. Every host MUST refuse
to start — exit non-zero with an error naming the cause, before any file, store row or
network request, the standalone lock probe's own directory and lock file excepted (`HST-9`) —
on: an environment variable set to a non-empty value it cannot parse
(`HST-2`); a config key it does not know or cannot parse (`HST-3`, `HST-26`); a path it cannot
resolve to an absolute one (`HST-3`, `HST-4`); and, for the standalone process alone, a store
lock a resident host holds (`HST-9`) — `init` is the one one-shot command that blocks on the
lock instead (`HST-4`, `API-3`). It MUST NOT substitute a default for a value it could not parse, and an `init` that fails
validation MUST leave nothing behind: every path it writes is resolved and every value checked
before its first write. An `init` interrupted after a write is a different case — each file is
atomic on its own (`HST-19`), the mixed state is what `HST-33` refuses, and re-running `init`
repairs it. The
reason is `HST-3`'s: a stale key fails "loudly", and a knob that falls back silently is a
misconfiguration nobody sees.

## The standalone mode

**HST-9** `wallet-cli --standalone` is a one-shot process that takes the exclusive lock and
opens both stores (`STO-2`). Every verb of it that admits work — the money verbs, `join`,
`recover`, `probe`'s legs — is admitted through the same admission point as every other host's
(`OPS-5`, `OPS-12`); only its `tick` is the documented exception `ADR-0031` names (`OPS-12`);
its reads and admin verbs admit nothing. The live reads (`balance`, `list-feds`, `status`) perform nothing, so no
perform deadline applies to them (`ALC-44`); every verb that performs, `join` and `recover`
excepted (`OPS-15`: they "MUST NOT be timed out"), runs under `--perform-timeout <secs>`
(default 600; `0` disables), which bounds one perform as `WALLETD_PERFORM_TIMEOUT_SECS` does
for the daemon (`OPS-15` owns what a timeout leaves behind); the environment variable is not
read by the CLI. It resolves `data_dir` from
`--data-dir`, else `walletd.toml` (parsed with the daemon's own closed schema, so a stale
`gateway` key fails here too, `HST-3`), else the default. The lock comes first — after
creating the data directory `0700` if it does not exist, the one write a lock file needs:
open-or-create `<data_dir>/client.db.lock` and take it with a non-blocking exclusive lock
that is then held until both stores are closed (`STO-2`) — the probe is the acquisition, not a
check released before the open; contention MUST exit 1 with `another process owns the wallet
store (walletd?); stop it, or use client mode (drop --standalone)` before an existing
directory's mode or anything else is touched, never an indefinite wait (`HST-29`). Holding the
lock, it asserts the directory `0700` (`HST-19`), verifies that `client.db.lock` still names
the inode it locked — a directory that was writable by another user until that moment could
have had the entry replaced — failing otherwise (`HST-29`), and opens the stores.

**HST-10** The standalone-only verb shapes and flags are the set `API-25` enumerates (client
mode refuses exactly those with exit 1). The break-glass `--gateway` (`ADR-0030` owns its
dispatch) is accepted on `pay`, `receive`, `move`, `direct-inflow` and the three await verbs, where it is
armed for that ONE operation's key; it is a usage error on `tick`, `probe`, `discover`,
`status` and `reconcile`; it is ignored on verbs that resolve no route (`ADR-0030`). Standalone
`tick` and `status` accept ephemeral policy overrides (`--per-fed-cap`, `--evac-fee-*`,
`--occurrence`, …) that are validated but never persisted (`ALC-3`).

**HST-11** Standalone `tick` and `status` MUST refuse an incomplete federation registry before
opening or planning; explicit user and admin verbs keep their poison-tolerant behaviour
(`ALC-46`).

**HST-12** The standalone process is not a resident engine: it admits work only while it
holds the exclusive lock, through the one admission point (`OPS-13`), and admits nothing once
it exits; a resident host MUST admit every intent, its own cycle's included, through that same
point (`OPS-12`, `OVR-10`). `ADR-0031` calls the standalone tick "a deliberately isolated
compatibility exception, not a resident host or a model for a future frontend"; how a
resident host is constructed is the reference design's, and this set judges it only by the
admission invariant.

## The CLI as a frontend

**HST-13** `wallet-cli` in client mode holds no state beyond the pointer file. It never opens a
store. `04-api-contract.md` `API-25`–`API-31` own its behaviour.

## The browser sidecar

**HST-26** The sidecar `wallet-web` is a separate process that talks to the daemon over its
HTTP API with the bearer token, exactly as the CLI does, and renders HTML (`ADR-0028`). It
MUST NOT open either store. It reads the token from `token_path` before each daemon request,
as the CLI does on each invocation, so a rotation by `walletd init` takes effect on the next
request; a missing or empty file fails that request as the daemon being unreachable. Its posture — loopback bind, fail-closed start, a loopback-literal
`daemon_url` reached directly — is `SEC-22`'s; this rule owns its provisioning and its
configuration, and `HST-31` its request-time surface.

**Provisioning.** `wallet-web init` takes `--port` (default 9737), `--daemon-url` (default
`http://127.0.0.1:9736`), `--token-path` (required), `--public-origin` (required),
`--session-idle-timeout` (default `4h`), `--session-absolute-timeout` (default `24h`), and the
global `--config` (default `$XDG_CONFIG_HOME/wallet-web/wallet-web.toml`, else
`~/.config/wallet-web/wallet-web.toml`). It MUST refuse to run if the config file already
exists (`sidecar config <path> already exists; …`), checked before any prompt, and if
`--config` and `--token-path` resolve to the same file or one lies under the other
(`HST-29`): rotating the
password is delete-then-init. It MUST prompt for the password twice on the controlling
terminal with echo disabled, never read it from stdin or an argument (`SEC-6`); the two
entries MUST match, and a mismatch or an abort at the prompt MUST exit non-zero with nothing
written. The password MUST be at least 12
Unicode scalar values and at most 1,024 bytes of UTF-8 (bytes checked first), and is hashed as
the UTF-8 bytes entered, with no normalisation. It MUST hash with Argon2id v19 with
at least m = 19456 KiB, t = 2, p = 1, a fresh salt of at least 16 bytes and a 32-byte output, validate the whole
config through the same checks startup applies, and write the file `0600` atomically
(`HST-19`) into a directory it creates `0700` or verifies is owned by the running user and
writable by no one else.

**Configuration.** The file has exactly the keys `port, daemon_url, token_path,
password_hash, session_idle_timeout, session_absolute_timeout, public_origin`, every one
required; there is no bind-address key (the bind is `127.0.0.1`, `SEC-22`) and no log-level key
(`RUST_LOG`, `HST-2`). Timeouts are the grammar `<unsigned integer><s|m|h>` (no sign); `0s` is accepted —
immediate expiry is the fail-closed direction. Startup MUST refuse: a config file that is not a regular
file (a link included), not owned by the running user, or with any group or other permission
bit; a config directory not owned by the running user or writable
by another; a parse error (reported by position and message only — the offending line is
never quoted, so the hash cannot reach a log, `SEC-6`); a missing, empty or malformed PHC
hash; a hash that is not `argon2id`, does not declare `v=19`, has a salt under 16 bytes, has an
output under 32 bytes, or has `m`, `t` or `p` below the minimums above; port 0; a `daemon_url` that is
not `http://` + a loopback IP **literal** + port with at most a bare trailing `/` (`localhost`
is refused because it resolves but can be repointed; an IPv4 literal MUST be a canonical
dotted quad, so `127.1` and `0x7f.0.0.1` are refused as `HST-27` refuses them; `::1` is the
only IPv6 form; the stored
value is the parsed socket re-rendered, so `[0:0::1]` becomes `[::1]` and the trailing `/` is
dropped); a `token_path` that does not resolve to an absolute path (`~/` expands as `walletd`'s
does) or that equals, lies under or contains the config file's path; an idle timeout above 4h or an absolute timeout above 24h, or either unparseable; a
`public_origin` that `HST-27` refuses.

**HST-31** The sidecar's request-time surface, from `ADR-0028`. The complete unauthenticated
surface is exactly `GET /login`, `POST /login` and `GET /healthz` (`ADR-0028`: "There is otherwise no unauthenticated surface — not even
balance"); a request without a valid session to any other route is answered `303` to `/login`
when it is a `GET` for a page and `401` otherwise, with no wallet data either way; `/healthz`
answers `200` with the JSON object `{"sidecar_alive": true,
"daemon_reachable": <bool>}` — exactly those two keys, `daemon_reachable` `true` only when
`GET /v1/health` on `daemon_url` answered `200` with the configured token — and no wallet
data; the daemon check behind `daemon_reachable` is bounded by 5 s in total, and a check
that has not answered by then reports `false`. `POST /login` takes an
`application/x-www-form-urlencoded` body with the one field `password`; a body of any other
type, or without that field, is `400` and is not an attempt. Login verifies the password against
the stored hash in constant time; a wrong password is `401`, re-rendering the login page with no
hint beyond that the login failed, and is one failed attempt; a correct one answers `303` to
`/` with the session cookie `session` (its attributes below). Login MUST be
rate-limited (`ADR-0028`: "Rate limiting is required, not optional"): after 5 consecutive
failed attempts the sidecar MUST answer every login attempt `429` for the next 60 s, counted
across the whole listener, with attempts processed one at a time: each attempt's verification
completes and updates the count before the next is admitted, so a concurrent burst yields at
most 5 failed verifications before the lockout and a success among them resets the count in
its turn — behind the reverse proxy `ADR-0028` contemplates every request
arrives from `127.0.0.1`, so a per-address key would exempt exactly the exposed case. The
lockout's end does not reset the count: each further failure after it re-arms the lockout for
another 60 s, and only a successful login resets the count. A login body above 4 KiB MUST be refused `413`, a check that runs after the `Origin` check
and before the body's type and fields are examined, and does not count as an attempt. A session is an opaque token from a cryptographically secure random
source with at least 256 bits of entropy (the bar `SEC-2` sets for the bearer token), held in
memory only — no signing key at rest,
no session survives a restart, so restarting the sidecar is the one "revoke all sessions" —
carried by the `HttpOnly`, `SameSite=Strict`, host-only, `Path=/` cookie `session`, whose
`Secure` flag is set exactly when `public_origin`'s scheme is `https`. A session expires after the configured idle
timeout without a non-polling request, and unconditionally at the absolute timeout; a
polling request — one the page issues on its own timer rather than on a user action, which
the page marks with the request header `X-Polling: 1`, and which the sidecar classifies by that
header alone — MUST NOT extend the idle timer. Every state-changing request MUST — after the session has been authenticated, so an
unauthenticated one gets the `401` or `303` above, except `POST /login`, whose `Origin` is checked
first of all, before the body is read or the credential verified — be refused unless its `Origin` header equals
`public_origin` (`HST-27`'s form); every one but
`POST /login` — the request that creates the session, so it has no token yet — MUST also carry
the session's CSRF token: a second value minted with the session from the same source and
entropy as the session token, bound to that session for its lifetime, delivered only inside
the HTML the sidecar renders (never in a cookie or a response header), and presented back in
the form field `csrf_token` on the sidecar's own page routes, and the request header
`X-CSRF-Token` alone on a forwarded `/v1/` route, whose body is forwarded unchanged; a request whose token is
missing or is not the presenting session's, or whose `Origin` fails the check, is refused
`403` with no wallet data and no change to the session. A dedicated origin is required for
that reason (`ADR-0028`: "same-origin neighbours can read the CSRF token out of the page"). One login gates the whole UI: there is
no step-up before spending. The surface is every daemon route **except `/v1/recover`**, which
the sidecar MUST NOT reach by any route or page (`ADR-0028`, amendment): each such route MUST
be exposed under the sidecar's own `/v1/` prefix with the daemon's path, query string, method, status
code, request and response bodies unchanged (`04-api-contract.md`), the sidecar swapping the session
for the bearer token, forwarding the request's `Content-Type` (`API-35` requires it), the
response's `Content-Type` and `Allow` (`API-5`'s `405` carries it), and nothing else, and
adding, on its own account rather than by forwarding, `Cache-Control: no-store` to every
response to an authenticated request, page or forwarded route, so a shared cache in front of the sidecar never replays wallet data, and answering `502` with no wallet data when
it has no daemon response to forward (the token unreadable, the daemon unreachable, or its
answer not received within 90 s, `API-25`'s client bound), and the HTML pages, on paths outside `/v1/`, are
views over those forwarded routes and expose no wallet data the routes do not; verbs with no daemon
endpoint (`API-25`'s standalone-only set) are not offered. Every operation it admits is
`actor: User` (`OPS-5`). It holds no in-flight state: outstanding operations are rebuilt from
the daemon's history (`API-10`) on every load and polled through `GET /v1/operations/{key}`
(`API-11`) while on screen; the rebuild MUST use the `status=open` filter (`API-43`), following
`next_before_seq` until it is `null` — paging the filtered query is not the crawl this forbids —
never an unfiltered walk of the whole history, and when a page reports `skipped_unreadable` above zero the UI
MUST say the outstanding set is incomplete and MUST NOT present it as complete, because a
skipped row may be a live money operation with no key to poll.

**HST-27** `public_origin` is stored in the canonical form a browser sends in `Origin` — the
WHATWG URL origin serialisation — so that a request's `Origin` header can be compared with it
byte for byte (`HST-31`). An accepted input is **normalised** by the rules below and only the
listed ambiguous or unsafe forms are refused, so `https://Wallet.EXAMPLE:443` starts and is
stored as `https://wallet.example`.
Refused: any `#`; a scheme other than `http`/`https`; userinfo; a host with any character
outside ASCII letters, digits, `-`, `.`, `[`, `]` and `:` (an internationalised name MUST be
given in the ASCII form a browser sends); a non-`/` path or a query; an
empty host; a port that is not a `u16` or is `0`; an IPv4-mapped IPv6 host (`[::ffff:…]`, which
implementations serialise differently); a host ending in `.`; a host whose last label is all
digits or `0x`+hex that is not already a canonical dotted quad (`127.1`, `0x7f.0.0.1`,
`2130706433`, `127.0.0.0x1`, `wallet.1`). Canonicalised: the host is lowercased; a bracketed
IPv6 host is re-rendered in the canonical compressed text form (`[0:0::1]` → `[::1]`); a port
equal to the scheme's default (80/443) is **elided**, so `https://wallet.example:443` is stored
as `https://wallet.example`, and a bare origin is accepted as-is. Normalisation is idempotent
on its own output.

## What a stranded move leaves for the operator

**HST-32** A `Stranded` move (`DOM-10`; the transition is `OPS-27`) is terminal: nothing
re-drives it (`OPS-35` re-drives `Pending` and `Executing` intents only, and a `Stranded` move
is neither) and the wallet MUST NOT admit a second send
for the same key: a request under it attaches to the existing intent (`OPS-8`) and a retry of
it is refused (`OPS-10`), which is what stands between the operator and a double send. The only recovery is the explicit re-claim `FMI-41` requires,
and the operator's response before it is **evidence preservation**: the preimage is not a
recovery procedure (`DEF-20`). What the wallet MUST guarantee for that response: the move
record with both leg operation ids, the invoice, the gateway and the preimage (`STO-11`) and
the operation record with the receive leg's error detail anchored on "send settled but receive
was not credited" (`OPS-27`) stay in the journal unchanged, once the stranding write of
`OPS-27` has completed them, by every later cycle; standalone `show <key> --json` (`API-30`)
reads the operation record offline — the leg operation ids, the gateway, the error detail, and
the timestamps that date the move's window — while the preimage survives only in the move
record (`STO-11`: the invoice and the leg ids can be rebuilt from the operation log, the
preimage cannot) and no verb is required to display it; and the destination federation's client state — what a re-claim (`FMI-41`) reads to learn
whether the incoming contract is still funded and claimable or already consumed (`FMI-37`:
after some failures its position is unknown) — stays in the client store, where a running
daemon keeps transacting on it, which is why the operator's procedure begins with stopping the
daemon. The data directory is then
the whole of the evidence, and a copy of it run elsewhere is a second spender (`SEC-23`). The
procedure itself — the runbook — is the code repository's.

## Files on disk

**HST-19** How files reach disk. **Secret files** — the bearer token and `wallet-web.toml` —
MUST be written atomically, by whatever primitive the platform offers: at every instant,
crashes included, a reader at the target path finds either the previous complete file or the
new complete one — or, on the file's first creation, nothing — never a partial one, and a
first creation publishes only while the target is still absent, failing rather than replacing
one that appeared in the meantime (so two `wallet-web init`s racing on an absent config cannot both
succeed; two `walletd init`s serialise on the store lock instead, `HST-4`, and the second
rotates the token as any re-run does, `API-3`); the new file has mode `0600` from the first instant it
is visible at that path, whatever the umask; once the write returns the contents are on
stable storage; and a temporary an interrupted earlier write had not yet published MUST NOT
block the next (a target it had published is the file, and `HST-26`'s refuse-if-exists applies). **Non-secret files** — `walletd.toml`, `client.toml` — carry the same old-or-new
guarantee and the same durability once the write returns, so an interrupted `init` never
leaves a truncated config for the next `init` to refuse and a power loss after `init` reports
success never reverts the pointer or config behind a rotated token, and are published with no group or other write bit whatever the umask is — their read bits MAY
follow the umask (`SEC-5`) — and MUST, at every read, be regular files, not links, owned by the
running user and not writable by another user, else the read fails: a writable `client.toml` lets that user point every
frontend's token at an address of their choosing. **Directories**: the daemon MUST create the data
directory if missing, refuse one not owned by the running user (`HST-29`; a mode can be
re-asserted, an owner cannot), and re-assert `0700` on it at the start of `serve`, `init` and
`restore-mnemonic` — not `mnemonic`, a read-only export, which MUST instead refuse a data
directory writable by another user (`HST-29`) rather than trust a lock taken inside it — so a
directory whose mode drifted is re-tightened by the next start (the directory's own existence and mode hold no wallet content
and are not a write in `SEC-11`'s "MUST write nothing on any failure"); the standalone process asserts it likewise (`HST-9`); the daemon's config directories — the actual parent of `walletd.toml`, checked at the start
of every subcommand and by a standalone invocation that consults the file (`HST-9`), and the actual parent of `client.toml`, checked at the start of `init`
and serve (the commands that write or read the pointer, `HST-4`, `HST-33`) and at every
client-mode CLI invocation that reads it; one directory or two when `--config` points
elsewhere — are created `0700` by `init` when missing and MUST each be owned by the running
user and writable by no other, else the command fails (`HST-29`) — a
writable directory lets another user replace the pointer whatever the file's own mode;
`wallet-web init` creates a missing config directory `0700` and leaves an existing one's mode
alone (`HST-26`). Nothing changes the mode of the stores' own files. **Lock files**: `client.db.lock` and
`client.toml.lock` MUST each be a regular file, not a link, owned by the running user, checked
before any lock on it is relied on, else the command fails (`HST-29`) — a lock on a linked
inode excludes nobody who can retarget the link. **Store directories**: `client.db` and
`journal.db` MUST each be a directory, not a link, owned by the running user and writable by
no other, checked before it is opened, else the command fails (`HST-29`). A process MUST reach the
lock file, both stores and the token file through one handle to the data directory, obtained
once before the checks, so that a swap of the directory entry by whoever can write its parent
cannot separate the lock a process holds from the stores it guards or from the token it reads
or rotates; and likewise the pointer, its lock and the host config through one handle to each
checked config directory, so the pointer a daemon holds locked is the one a frontend reads.

**HST-21** Data directory layout:

```
<data_dir>/              0700, re-asserted on every start, init and restore
  client.db/             the client store: the federation clients' partitions and the seed slot (encrypted, SEC-25)
  client.db.lock         the exclusivity anchor (STO-2)
  journal.db/            the app journal: intents, moves, ledger, registry, candidates, policy, watch state
  token                  0600, 64 hex characters
~/.config/walletd/walletd.toml    host config, no secrets
~/.config/walletd/client.toml     {url, token_path} for the CLI
~/.config/wallet-web/wallet-web.toml   0600, the Argon2id hash
```

## Readiness

**HST-30** The wallet is not required to ship or schedule a readiness probe; whether one runs
is the deployment's. A probe an implementation does ship MUST read `GET /v1/health`
(`API-16`) with the token and MUST distinguish three outcomes, the unknown one decided first:
ready; not ready — a body carrying both fields, with `scheduler_alive` `false` or
`automation_ready` `false`; and unknown — the
daemon unreachable, no token configured, an answer that is not `200` with a decodable body (a
`401` on a stale token included), or a body without `automation_ready` (`API-16`: a caller
"MUST treat readiness as unknown, not healthy"). A command-line probe exits `0`, `1` and `2`
for those in turn; a platform-native probe maps them to its ready, failing and unknown states. Its
report carries `automation_blocked`'s `reason` and `detail` when that field is non-null, and
names the cause of an unknown outcome. A probe that reads only the status code is not a
readiness probe (`ALC-45`: "Liveness is not readiness").
