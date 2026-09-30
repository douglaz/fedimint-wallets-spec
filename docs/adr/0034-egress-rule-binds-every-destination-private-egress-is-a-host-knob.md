---
status: accepted
---
# The egress rule binds every URL-hosted destination; the override meta is never fetched; private egress is one host knob, on by default

`FMI-40` refused private, link-local, loopback and metadata addresses for gateway requests
only, and offered a private-network allowance as a MAY no compliant host could exercise
(`HST-2` and `HST-3` close the configuration surface). Three other outbound classes inherited
nothing: the guardian-supplied `meta_override_url`, which the client SDK's background meta
service fetches every ten minutes whether or not the wallet reads it; the operator-configured
discovery base; and the guardian HTTP/WebSocket endpoints inside invites, whoever supplied
them. Four independent analyses (2026-09-23) agreed on the first
two parts below and split on the third. Decided on 2026-09-24.

**Decided.**

- `FMI-40` binds every URL-hosted destination: gateway URLs on a vetted list, the break-glass
  gateway, the discovery base, and every guardian HTTP or WebSocket endpoint used for preview,
  join, open, recovery and later use — a user-supplied invite, a `Manual` source, vetted-list
  membership and the break-glass grant no exemption, and the exemption is not inferred from
  `SEC-16` (a user's funding decision is not a network authorisation). iroh endpoints have no
  host and are outside the rule. The rule applies to the destination the wallet resolves
  before a proxy `CONNECT`; the proxy is inside `SEC-3`'s trust boundary and `HST-2` states
  the operator's obligation that it connects to that destination.
- The wallet never fetches `meta_override_url`. `FMI-26` has two shutdown inputs (the at-join
  authenticated config expiry and corroborated `/status`), `SEC-14` and `ALC-39` lose the
  override-served value and its wake, and the threat model's malicious-guardian item says so.
  The reference implementation replaces the SDK's meta source to comply.
- Private egress is **one boolean host setting**, `allow_private_egress`, a new
  `walletd.toml` key (`HST-3`) with a standalone flag (`HST-10`), **default on**. While on,
  loopback, RFC 1918 and unique-local (`fc00::/7`) destinations are reachable for every
  class; a **floor** is refused regardless: link-local (`169.254.0.0/16`, `fe80::/10`) and
  the cloud metadata addresses (`169.254.169.254`, `fd00:ec2::254`, `100.100.100.200`).
  Every contact with a private destination is logged with its provenance (vetted list, feed,
  user, operator). Chapter 10's environment runs with the default and needs no setting.

**Why default on.** The residual risk while the knob is on is blind, fixed-shape Fedimint API
requests to private hosts from a guardian- or feed-chosen destination; the metadata floor
closes the credential-stealing case whatever the knob says. Against that, default-off locks
out home-LAN and overlay (Tailscale, WireGuard) federations and the developer's devimint
until the operator finds the key. The cloud operator — the pilot's `walletd` on Kubernetes —
is expected to turn it off, and the setting is one line.

**Rejected.**

- A CIDR or exact-socket allowlist: finer-grained, but the operator
  maintains it as addresses move, and the threat it narrows is the modest one above.
- A provenance rule with no knob (operator-named destinations free, guardian/feed-chosen
  bound): a LAN federation joins but its guardian-listed gateway stays refused, so paying and
  receiving need the break-glass on every operation — the standing use `ADR-0030` removed the
  pin for.
- A user-invite exemption on its own: illusory for the same reason, and social engineering
  becomes network authorisation.
- Default off (the current MAY's posture): see above.
- A `Policy` field: `DOM-15`, `API-20`, `CNF-26` count churn, and any API token holder could
  widen egress.
- Keeping the override fetch address-checked: a permanent guardian-chosen GET for a warning
  and a wake that `SEC-14` already says never trigger anything alone.

**Consequences.** `FMI-40` is rewritten as the single owner with the class list, the floor,
the knob and the refusal outcomes (a rejected gateway is unavailable; a rejected discovery
base is a source failure; a rejected guardian endpoint fails the preview, join, open or
recovery using it); `SEC-16`, `SEC-17`, `FMI-28`, `HST-2`, `HST-10` cite; `FMI-26`, `SEC-14`,
`ALC-39` lose the override input; `HST-3` gains the key; chapter 10 gains one scenario per
class. `spec-22p` carries the edits and its chapter-11 entry is filed as answered by this ADR.
