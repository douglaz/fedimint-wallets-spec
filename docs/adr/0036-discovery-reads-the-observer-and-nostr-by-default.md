---
status: accepted
---
# Discovery reads the Observer and Nostr by default; both sources are host configuration

`FMI-28` fetches `{base}/federations` from the Fedimint Observer but nothing says where `{base}`
comes from, `STO-15` persists a `Nostr` discovery source that no requirement collects, and
`ADR-0019` left open whether to consume the Observer as a bootstrap prior or run our own
collection (`spec-6w6`). Decided on 2026-09-25.

**Decided.**

- **Both feeds, on by default.** A discovery pass (`ALC-28`) collects from the Observer, from
  Nostr and from `Manual` invites. Both remain untrusted priors (`ADR-0019`, `ADR-0020`):
  they only nominate candidates, every candidate is previewed, structurally checked and
  probe-gated before any funds move, and nothing either feed says is a trust, scoring or
  shutdown input.
- **The Observer base** is host configuration: a `walletd.toml` key and a standalone flag,
  defaulting to `https://observer.fedimint.org/api`; an empty value disables the Observer.
- **Nostr** reads NIP-87 kind-38173 federation announcements — `d` the federation id, `u`
  one or more invite codes, `n` the network — from a relay list that is host configuration
  too, defaulting to `wss://relay.damus.io`, `wss://nos.lol`, `wss://relay.primal.net` and
  `wss://relay.nostr.band`; an empty list disables Nostr. Kind-38000 recommendations are not
  read (the code repository's June 2026 measurement found them content-free and
  non-predictive).
- **Announcements are unauthenticated**, so a Nostr candidate gets `FMI-28`'s identity check
  (the claimed id, the invite's embedded id and the previewed config's computed id agree), as
  `FMI-43` already requires. Relay URLs are operator-named destinations
  for `ADR-0034`'s egress rule; guardian endpoints inside announced invites are feed-chosen.
- `FMI-43` becomes the Nostr collector's owner with the same bounds shape as `FMI-28` (a
  per-source share of the pass deadline, a per-relay time and size bound, a cap on events
  read), and `DOM-12`'s "no requirement produces `Nostr`" sentence goes.

**Rejected.**

- The Observer alone, Nostr left dormant: the Observer is admin-curated (about seventeen
  mainnet federations in June 2026, not a census); Nostr is the one open feed.
- No default source, operator must configure one: discovery then finds nothing out of the
  box, and every operator would type the same URLs.
- Relay discovery (NIP-65 outbox, relay hints in announcements): an open-ended egress
  surface and an algorithm to bound, for coverage a fixed list already gives.
- Reading kind-38000 recommendations as a popularity prior: measured to carry no signal.

**Consequences.** `spec-6w6` carries the edits: `HST-3` gains the Observer base and relay
list keys, and
`HST-10` the standalone flags; `FMI-28`, `FMI-43`, `ALC-28` step 1, `DOM-12` and `STO-15`
align; `FMI-40`'s class list gains Nostr relays, a refused relay being a failure of that relay
within the Nostr source, with its scenario; the chapter-10 environment names its discovery
sources. `ADR-0019`'s open bullet is
answered by this ADR.
