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
  boundary (`SEC-4`). When the file is configured, start unseals from it, and a file that is
  missing, unreadable or wrong fails startup (`HST-29`) — it never falls back to the sealed
  state. When no file is configured the daemon starts **sealed**.
- **Sealed** is a state of the running daemon, not a refusal to run: the listener and token
  auth come up first; `GET /v1/health` answers with a sealed flag; every other route answers
  one fixed `503` in `API-37`'s shape; the stores are not opened and the scheduler and
  watchdog are not started until the unseal call succeeds. A crash-restart of a daemon with
  no passphrase file stays sealed until the next unseal call.
- `walletd init` requires the passphrase (from the file or a TTY prompt) and writes the
  encrypted slot; the one-shot commands (`mnemonic`, `restore-mnemonic`, the standalone
  mode) take it from the configured file, a flag (`HST-10`), or a TTY prompt, and fail
  without one.
- **No plaintext-seed migration.** The set does not assume stores with a plaintext seed slot
  exist: the encrypted slot is the only slot, a store without one is a startup failure, and
  `SEC-25`'s one-time re-encryption clause and `CNF-47`'s migration half are withdrawn. The
  rollback half stays: a build that predates `SEC-25` MUST fail to open the slot.

**Rejected.**

- A KMS/HSM-wrapped data key (`ADR-0026` option 2): an external dependency and a network
  round-trip in every restart, for a pilot with no such infrastructure. It can be added later
  as a second source without changing the slot.
- Interactive unseal only (no file): incompatible with unattended supervisor restarts.
- An lnd-style `create` call that makes the wallet over the API (decided 2026-09-30): `init`
  is what mints the API token (`HST-4`), so a daemon with no store would have to accept the
  call unauthenticated, from whoever reaches the port first. Creation stays `walletd init`, with
  the passphrase from the mounted file or a prompt; a deployment without a shell runs `init` as
  an init step with the file mounted. The API only unseals a wallet that already exists.
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
