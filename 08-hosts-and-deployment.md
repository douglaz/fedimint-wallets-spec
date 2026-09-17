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
in the table is read in a release build. A variable set to a non-empty value the wallet cannot
parse fails startup (`HST-29`), never falls back silently to a default. Two further variables
exist only in debug builds and are compiled out of release: the fault-injection seams
`WALLET_CLI_CRASH_AT` (`OPS-28`) and `WALLET_CLI_FORCE_SHUTDOWN` (`FMI-26`), owned by
`SEC-18`.

| Variable | Read by | Effect | Empty / invalid |
|---|---|---|---|
| `WALLETD_TOKEN_PATH` | `walletd` (all subcommands) | token file, over `walletd.toml` (`HST-4`) | empty = unset; a relative path fails startup |
| `WALLETD_PERFORM_TIMEOUT_SECS` | `walletd` serve | the per-intent perform deadline `OPS-15` bounds (`FMI-22`) | unparseable fails startup (`HST-29`) |
| `WALLETD_SETTLEMENT_STALL_SECS` | `walletd` serve (the standalone mode runs no scheduler) | the settlement-stall deadline `ALC-40` owns, with `ALC-40`'s default; `0` is a zero-second deadline | unparseable fails startup (`HST-29`) |
| `RUST_LOG` | all three binaries | overrides the log level (`HST-8`) | unset → `walletd.toml` `log_level` for the daemon, `warn` for the CLI, `info` for the sidecar; unparseable fails startup (`HST-29`) |
| `XDG_CONFIG_HOME` | all three | config home | empty or relative → ignored, `~/.config` (the XDG base-directory rule) |
| `XDG_DATA_HOME` | `walletd`, standalone `wallet-cli` | default `data_dir` | empty or relative → ignored, `~/.local/share` (the same rule) |
| `HOME` | all three | `~` expansion and the XDG fallbacks | read only when a path actually falls back to it; unset or empty then fails startup, before any file is written (`HST-29`); never read when every path the command touches is absolute (`XDG_CONFIG_HOME` and `XDG_DATA_HOME` absolute, an explicit `--config` whose paths are absolute for every subcommand but `init`, which also writes the pointer under the config home (`HST-4`) and so needs an absolute `XDG_CONFIG_HOME` as well; standalone `--data-dir`; or client-mode `--url` with `--token-path`, `API-25`) |
| `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` (and lowercase), `NO_PROXY` | `walletd`, `wallet-cli` | every outgoing HTTP connection the two make — the CLI's connection to the daemon, gateway `routing_info` (`FMI-11`), the Observer (`FMI-28`) — with the conventional semantics: the proxy for the scheme, `NO_PROXY` the exemptions, and no destination exempt that `NO_PROXY` does not name, loopback included, so an operator who sets a proxy owns the exemption for the daemon's own address (`SEC-3`). The sidecar is the exception and ignores them (`SEC-22`) | a proxy URL that does not parse fails startup (`HST-29`) |

**HST-3** `walletd.toml` has five keys and MUST reject any other — including the retired
`gateway` key (`ADR-0030`), so a file that still carries it fails startup loudly:

| key | default |
|---|---|
| `data_dir` | `$XDG_DATA_HOME/walletd`, else `~/.local/share/walletd` |
| `address` | `127.0.0.1` |
| `port` | `9736` |
| `token_path` | env `WALLETD_TOKEN_PATH`, else the key, else `<data_dir>/token` |
| `log_level` | `info` (`RUST_LOG` overrides) |

Paths MUST be absolute once `~` and `~/…` are expanded; anything else fails startup. `address`
is not validated: a bare IPv6 literal is bracketed wherever it is rendered into a URL or a
bind string, and a hostname is resolved by the bind. Environment knobs are the table in
`HST-2`.

**HST-4** `walletd init` MUST: read the config or take its defaults and write every key back
canonicalised; create the data directory `0700`; open both stores under the lock (`STO-2`:
blocking while a resident host holds it, so the token is never rotated under a running daemon,
`API-3`); seed the default policy row if absent (`STO-13`); mint and write the token `0600`
(`API-3`); and write the CLI's pointer file `client.toml` `{url, token_path}` under the config
home. It does **not** mint a seed (`SEC-11`). A path it cannot resolve fails it with nothing
written (`HST-29`). It prints six stdout lines: `initialized walletd`, then `  host config:`,
`  data dir:`, `  token (0600):`, `  client pointer:`, `  api url:` each followed by the
resolved value.
Token path precedence, for every subcommand, is `WALLETD_TOKEN_PATH` (when set and non-empty)
> `walletd.toml` `token_path` > `<data_dir>/token`. On serve the token file's contents are
whitespace-trimmed and an empty file fails startup (`bearer token file <path> is empty`); the
wallet is not required to check the file's mode when it reads it (`SEC-1`).

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
(`ALC-42`; new requests get `503` `wallet service is shutting down`, `API-37`) → abort every
in-flight drive, leaving its intent re-performable (`OPS-15`) → answer every parked long-poll
(`API-11`) with that error → exit. A fatal exit is non-zero, so a supervisor configured to
restart on failure restarts it; a clean shutdown on a signal exits zero.

**HST-33** The daemon MUST read the token only while it holds the store lock. `init` rotates
the token only under that lock (`API-3`), so a daemon that reads it there serves with the
token the last completed `init` wrote, and an `init` racing a start cannot leave the daemon
holding a token no frontend has.

**HST-8** The daemon MUST log to stderr and to nothing else, at the level `HST-3`'s
`log_level` or `RUST_LOG` selects. Redaction is `SEC-6`'s: no code path logs the token, the
seed or a password. `walletd mnemonic` prints the seed to stdout by design.

**HST-29** A misconfiguration fails loudly and leaves nothing behind. Every host MUST refuse
to start — exit non-zero with an error naming the cause, before any file, store row or
network request — on: an environment variable set to a non-empty value it cannot parse
(`HST-2`); a config key it does not know or cannot parse (`HST-3`, `HST-26`); a path it cannot
resolve to an absolute one (`HST-3`, `HST-4`); and, for the standalone process alone, a store
lock a resident host holds (`HST-9`), whether found at the probe or taken between the probe and
the open — `init` is the one one-shot command that blocks on the lock instead (`HST-4`,
`API-3`). It MUST NOT substitute a default for a value it could not parse, and MUST NOT leave
a partial `init` behind: every path `init` writes is resolved before the first write. The
reason is `HST-3`'s: a stale key fails "loudly", and a knob that falls back silently is a
misconfiguration nobody sees.

## The standalone mode

**HST-9** `wallet-cli --standalone` is a one-shot process that takes the exclusive lock and
opens both stores (`STO-2`). Every verb it runs is admitted through the same admission point as
every other host's (`OPS-12`, `OPS-5`); only its `tick` is the documented exception `ADR-0031`
names (`OPS-12`). The live reads (`balance`, `list-feds`, `status`) perform nothing, so no
perform deadline applies to them (`ALC-44`); every verb that performs, `join` and `recover`
excepted (`OPS-15`: they "MUST NOT be timed out"), runs under `--perform-timeout <secs>`
(default 600; `0` disables), which bounds one perform as `WALLETD_PERFORM_TIMEOUT_SECS` does
for the daemon (`OPS-15` owns what a timeout leaves behind); the environment variable is not
read by the CLI. It resolves `data_dir` from
`--data-dir`, else `walletd.toml` (parsed with the daemon's own closed schema, so a stale
`gateway` key fails here too, `HST-3`), else the default. The lock comes first — after
creating the data directory `0700` if it does not exist, the one write a lock file needs:
open-or-create `<data_dir>/client.db.lock` and attempt a non-blocking exclusive lock;
contention MUST exit 1 with `another process owns the wallet store (walletd?); stop it, or use
client mode (drop --standalone)` before an existing directory's mode or anything else is
touched, and a lock taken
between that probe and the store open is an exit-1 error too, never an indefinite wait
(`HST-29`). Holding the lock, it asserts the directory `0700` (`HST-19`) and opens the stores.

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
MUST NOT open either store. Its posture — loopback bind, fail-closed start, a loopback-literal
`daemon_url` reached directly — is `SEC-22`'s; this rule owns its provisioning and its
configuration, and `HST-31` its request-time surface.

**Provisioning.** `wallet-web init` takes `--port` (default 9737), `--daemon-url` (default
`http://127.0.0.1:9736`), `--token-path` (required), `--public-origin` (required),
`--session-idle-timeout` (default `4h`), `--session-absolute-timeout` (default `24h`), and the
global `--config` (default `$XDG_CONFIG_HOME/wallet-web/wallet-web.toml`, else
`~/.config/wallet-web/wallet-web.toml`). It MUST refuse to run if the config file already
exists (`sidecar config <path> already exists; …`), checked before any prompt: rotating the
password is delete-then-init. It MUST prompt for the password twice on the controlling
terminal with echo disabled, never read it from stdin or an argument (`SEC-6`), and an abort
at the prompt MUST exit non-zero with nothing written. The password MUST be at least 12
characters and at most 1,024 bytes (bytes checked first). It MUST hash with Argon2id v19 with
at least m = 19456 KiB, t = 2, p = 1, a fresh salt of at least 16 bytes and a 32-byte output, validate the whole
config through the same checks startup applies, and write the file `0600` atomically
(`HST-19`) into a directory it creates `0700` or verifies is owned by the running user and
writable by no one else.

**Configuration.** The file has exactly the keys `port, daemon_url, token_path,
password_hash, session_idle_timeout, session_absolute_timeout, public_origin`, every one
required; there is no bind-address key (the bind is `127.0.0.1`, `SEC-22`) and no log-level key
(`RUST_LOG`, `HST-2`). Timeouts are the grammar `<integer><s|m|h>`; `0s` is accepted —
immediate expiry is the fail-closed direction. Startup MUST refuse: a config file with any
group or other permission bit; a config directory not owned by the running user or writable
by another; a parse error (reported by position and message only — the offending line is
never quoted, so the hash cannot reach a log, `SEC-6`); a missing, empty or malformed PHC
hash; a hash that is not `argon2id`, does not declare `v=19`, has a salt under 16 bytes, has an
output under 32 bytes, or has `m`, `t` or `p` below the minimums above; port 0; a `daemon_url` that is
not `http://` + a loopback IP **literal** + port with at most a bare trailing `/` (`localhost`
is refused because it resolves but can be repointed; `::1` is the only IPv6 form; the stored
value is the parsed socket re-rendered, so `[0:0::1]` becomes `[::1]` and the trailing `/` is
dropped); a `token_path` that does not resolve to an absolute path (`~/` expands as `walletd`'s
does); an idle timeout above 4h or an absolute timeout above 24h, or either unparseable; a
`public_origin` that `HST-27` refuses.

**HST-31** The sidecar's request-time surface, from `ADR-0028`. The complete unauthenticated
surface is exactly `GET /login`, `POST /login` and `GET /healthz` (`ADR-0028`: "There is otherwise no unauthenticated surface — not even
balance"); `/healthz` answers `200` with the JSON object `{"sidecar_alive": true,
"daemon_reachable": <bool>}` — exactly those two keys, `daemon_reachable` `true` only when
`GET /v1/health` on `daemon_url` answered `200` with the configured token — and no wallet
data; the daemon check behind `daemon_reachable` is bounded by 5 s in total, and a check
that has not answered by then reports `false`. Login verifies the password against the stored hash in constant time and MUST be
rate-limited (`ADR-0028`: "Rate limiting is required, not optional"); the limit's observable
parameters are an open question (`11-open-questions.md`, question 3) and the set is silent on
them until it is answered. A session is an opaque token from a cryptographically secure random
source with at least 256 bits of entropy (the bar `SEC-2` sets for the bearer token), held in
memory only — no signing key at rest,
no session survives a restart, so restarting the sidecar is the one "revoke all sessions" —
carried by an `HttpOnly`, `SameSite=Strict`, host-only cookie whose `Secure` flag is set
exactly when `public_origin`'s scheme is `https`. A session expires after the configured idle
timeout without a non-polling request, and unconditionally at the absolute timeout; a
polling request MUST NOT extend the idle timer. Every state-changing request MUST be refused
unless its `Origin` header equals `public_origin` (`HST-27`'s form); every one but
`POST /login` — the request that creates the session, so it has no token yet — MUST also carry
the session's CSRF token: a second value minted with the session from the same source and
entropy as the session token, bound to that session for its lifetime, delivered only inside
the HTML the sidecar renders (never in a cookie or a response header), and presented back in
the form field `csrf_token` or the request header `X-CSRF-Token`; a request whose token is
missing or is not the presenting session's is refused. A dedicated origin is required for
that reason (`ADR-0028`: "same-origin neighbours can read the CSRF token out of the page"). One login gates the whole UI: there is
no step-up before spending. The surface is every daemon route **except `/v1/recover`**, which
the sidecar MUST NOT reach by any route or page (`ADR-0028`, amendment); verbs with no daemon
endpoint (`API-25`'s standalone-only set) are not offered. Every operation it admits is
`actor: User` (`OPS-5`). It holds no in-flight state: outstanding operations are rebuilt from
the daemon's history (`API-10`) on every load and polled through `GET /v1/operations/{key}`
(`API-11`) while on screen; the rebuild MUST use `API-10`'s `status=open` filter, never a
crawl of the whole history.

**HST-27** `public_origin` is stored in the canonical form a browser sends in `Origin` — the
WHATWG URL origin serialisation — so that a request's `Origin` header can be compared with it
byte for byte (`HST-31`). An accepted input is **normalised** by the rules below and only the
listed ambiguous or unsafe forms are refused, so `https://Wallet.EXAMPLE:443` starts and is
stored as `https://wallet.example`.
Refused: any `#`; a scheme other than `http`/`https`; userinfo; a non-`/` path or a query; an
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
`OPS-27` has completed them, by every later cycle; standalone `show <key>` (`API-30`) reads the operation record offline — the leg
operation ids, the gateway, the error detail, and the timestamps that date the move's window —
while the invoice and the preimage survive only in the move record (`STO-11`) and no verb is
required to display them; and the destination federation's client state — what a re-claim (`FMI-41`) reads to learn
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
new complete one — or, on the file's first creation, nothing — never a partial one; the new file has mode `0600` from the first instant it
is visible at that path, whatever the umask; once the write returns the contents are on
stable storage; and what an interrupted earlier write left behind MUST NOT block the next. **Non-secret files** — `walletd.toml`, `client.toml` — MAY be written
plainly under the ambient umask (`SEC-5`). **Directories**: the daemon MUST create the data
directory if missing and re-assert `0700` on it at the start of `serve`, `init` and
`restore-mnemonic` — not `mnemonic`, a read-only export — so a directory whose mode drifted is
re-tightened by the next start; the standalone process asserts it likewise (`HST-9`);
`wallet-web init` creates a missing config directory `0700` and leaves an existing one's mode
alone (`HST-26`). Nothing changes the mode of the stores' own files.

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
(`API-16`) with the token and MUST report not-ready — a non-zero exit, or its platform's
failing check — when the daemon is unreachable, when `scheduler_alive` is `false`, and when
`automation_ready` is `false` or absent (`API-16`: a caller "MUST treat readiness as unknown,
not healthy"); its report carries `automation_blocked`'s `reason` and `detail` when the body
has them and says readiness is unknown when it does not. A probe that reads only the status
code is not a readiness probe (`ALC-45`: "Liveness is not readiness").
