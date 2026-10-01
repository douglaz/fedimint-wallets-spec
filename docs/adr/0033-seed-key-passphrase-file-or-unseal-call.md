---
status: accepted
---
# The seed key is a passphrase, delivered by a file or by an unseal call; the daemon starts sealed without one

`SEC-25` requires the seed to be stored under an AEAD keyed from outside the store, and
`ADR-0026` recommended an operator passphrase without deciding where it comes from. The
daemon's restart model (`HST-7`, `ALC-40`: exit and let the supervisor restart) rules out
anything that needs a human at every start, and a headless pilot has no key-management
service to depend on. Decided on 2026-09-23 for the headless hosts — `walletd`, the standalone
mode and the one-shot commands; the Android host keys its store from the hardware-backed
Keystore (`ADR-0011`) and is outside this decision.

**Decided.**

- The key is derived from an **operator passphrase** by a memory-hard KDF and used with an
  AEAD over the stored entropy (`ADR-0026` option 1). The slot's on-disk layout — a version
  discriminator that an older build cannot decode as entropy, the KDF parameters, the nonce,
  the ciphertext and its associated data — is fixed under one `STO` identifier so that two
  implementations write interoperable stores.
- The passphrase reaches `walletd` in one of two ways, as `lnd` does: a **passphrase file**
  named by a new `walletd.toml` key with an environment override (`HST-3`, `HST-2`), read at
  start; or an **unseal call** — `POST /v1/unseal` carrying the passphrase, inside the token
  boundary (`SEC-4`). The set provides no transport security (`SEC-3`), so the daemon accepts
  the unseal call only while it is bound to loopback; an operator who binds beyond loopback
  uses the passphrase file, and a remote operator reaches a loopback bind through the
  authenticated tunnel `SEC-3` already treats as the only safe non-loopback exposure. When the file is configured, start unseals from it, and a file that is
  missing, unreadable or wrong fails startup (`HST-29`) — it never falls back to the sealed
  state. When no file is configured the daemon starts **sealed**.
- **Sealed** is a state of the running daemon, not a refusal to run. Serve takes the store
  lock, reads the token file under it (`HST-33`; the token is a file beside the stores, not
  inside them) and opens both stores far enough to read **whether the seed slot exists**,
  without decrypting it — the slot's presence and its discriminator are not secret, and the
  start path depends on them: a seeded store with no passphrase file binds the listener and
  waits sealed; a seedless store with no passphrase file refuses to start, minting nothing
  (`SEC-11`). While sealed, `GET /v1/health` answers with a sealed flag; every other route
  answers one fixed `503` in `API-37`'s shape; no federation client is opened, no store is
  written, and the scheduler and watchdog are not started until the unseal call
  succeeds. A crash-restart of a daemon with
  no passphrase file stays sealed until the next unseal call.
- `walletd init` writes no seed: it creates the stores, the policy row and the token
  (`HST-4`), and the store stays seedless so that `init → restore-mnemonic → serve` works
  (`SEC-11`). The passphrase is first needed where the encrypted slot is first written —
  by `restore-mnemonic`, or by the first serve, which mints the seed (`SEC-11`). The first
  serve mints only from the configured passphrase file; with no file it refuses to start,
  minting nothing (`SEC-11` already requires that when the key source is unavailable), and
  the unseal call never mints — it only decrypts a slot that exists. The one-shot commands
  (`mnemonic`, `restore-mnemonic`, the standalone mode) take the passphrase from the
  configured file, a flag naming a passphrase file (`HST-10`) — never
  the passphrase itself, which argv and shell history would expose — or a TTY prompt, and
  fail without one.
- **No plaintext-seed migration.** The set does not assume stores with a plaintext seed slot
  exist: the encrypted slot is the only slot form. A store whose seed slot is present but not
  in the encrypted form (a plaintext slot) is a startup failure; a store with no seed slot at
  all is a fresh store from `init` and follows the first-serve rule above; and
  `SEC-25`'s one-time re-encryption clause and `CNF-47`'s migration half are withdrawn. The
  rollback half stays: a build that predates `SEC-25` MUST fail to open the slot. An operator
  holding a store written before this decision retires it by restoring its mnemonic into a
  new, encrypted store (`restore-mnemonic`); the set specifies no in-place conversion.

**Rejected.**

- A KMS/HSM-wrapped data key (`ADR-0026` option 2): an external dependency and a network
  round-trip in every restart, for a pilot with no such infrastructure. It can be added later
  as a second source without changing the slot.
- Interactive unseal only (no file): incompatible with unattended supervisor restarts.
- An lnd-style `create` call that makes the wallet over the API (decided 2026-09-30): every act
  that chooses the passphrase stays on the host — the first serve from the mounted passphrase
  file, or `restore-mnemonic` from a file or a prompt — so a mistyped passphrase sent over the
  wire can never become the key of a new seed, and a daemon reachable before `init` has no
  unauthenticated path to create anything. A deployment without a shell mounts the file for
  the first serve. The API only unseals a wallet that already exists.
- A raw 32-byte key file instead of a passphrase: no KDF to persist, but it moves key
  generation and protection onto the operator; the passphrase path is what operators expect.
- Serving read-only views while sealed: opens the journal and the client store at different
  times and gives every route a sealed/unsealed column; the value is small next to a health
  flag and a supervisor that can unseal.

**Consequences.** `SEC-25` names this ADR as the key-source decision and loses its migration
clause; a new `STO` rule owns the slot bytes; `HST-3` gains a key and `HST-2` its
override; `HST-6`'s serve order gains the unseal step and the sealed branch; `API-8`'s route
table gains `/v1/unseal`; `API-16` gains the sealed flag; `CNF-47` is restated with fixed
vectors and without the migration. `spec-iym` carries the edits.
