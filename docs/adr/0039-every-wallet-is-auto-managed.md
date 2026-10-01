---
status: accepted
---
# Every wallet is auto-managed; there is no manual-only wallet

Chapter 11's question 1 asked whether automated management is the onboarding flow's default
posture — the standing instruction presented to every user, declined to opt out — or an option a
user turns on. `ADR-0035` made accepting the standing instruction the condition for creating or
restoring a wallet. Decided on 2026-10-01.

**Decided.** Automated management is part of every wallet. A wallet comes into existence only
through the acceptance `ADR-0035` describes, so every wallet runs the allocator under the
standing instruction from the start, on every host: `walletd`'s scheduler, the standalone mode's
ticks and the Android engine's wakes alike. There is no manual-only wallet and no "automation
off" state; declining the standing instruction means not creating a wallet. What the agent may
do is bounded by the stored `Policy` (`OVR-8`) — its fee caps, its per-federation cap, and
auto-join, which policy can switch off — not by a separate on/off switch.

**Why.** It is what `ADR-0035` already implies, it adds no state, and it keeps one behaviour on
every host: the resident scheduler already runs unconditionally and stopping it is fatal
(`HST-6`, `ALC-42`). A manual-only wallet would need an off state on every host, a later
acceptance (which `ADR-0035` rules out), and a second set of scenarios for a wallet the product
does not intend to offer.

**Rejected.** Default on with a decline that yields a manual wallet; off by default with an
opt-in later. Both need the off state and a later acceptance. Leaving the question open pending
the fee-versus-risk analysis and the legal opinion chapter 11 named: the policy's caps are where
small-balance economics are tuned, and the legal posture is `ADR-0014`'s, which this decision
does not change.

**Consequences.** Chapter 11's question 1 moves to *Answered* with this ADR. `OVR-8` and the
`spec-dn8` requirement say the acceptance at creation is the onboarding flow's presentation of
the standing instruction; `spec-11k`'s Android contract presents it in the app's creation and
restore screens.
