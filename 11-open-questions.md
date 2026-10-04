# 11 — Open questions

Product decisions nobody has taken, whose answer changes what the wallet MUST do. While one is
open the set is **silent** on the behaviour it governs (`ADR-0032`): a requirement does not
describe what an implementation happens to do today to fill the gap. Findings against an
implementation — what it does not yet do that a requirement says it must — live beside the code,
in the code repository's
[`docs/open-findings.md`](https://github.com/douglaz/fedimint-wallets/blob/main/docs/open-findings.md),
because each one names the issue that tracks it and closes with the pull request that fixes it.
Roadmap order — which frontend or phase comes next — is the code repository's too.

A question is answered by an ADR, never by editing it away here: when one is decided, the entry
below is kept, marked with the ADR that answered it and the date, so a reader who was told it
was open can see where it landed.

## Open

3. **Should the wallet cap how long a send can lock the payer's funds?** *Opened 2026-10-02.*
   An lnv2 send funds an outgoing contract that the payer can refund unilaterally only once its
   expiration passes, unless the gateway cancels; the expiration is the federation's block count
   plus the gateway's expiration delta plus a margin. A gateway that never completes therefore
   holds the payer's funds for up to that delta, which `FMI-17` refuses only above 1 440 blocks
   (about ten days); the reference gateway asks for 1 440 on every send it routes to another
   node. Nothing in the set prices, shows or selects on the delta — `FMI-14` chooses a gateway
   by precedence and price (`FMI-12`) — and `ADR-0030`'s amendment binds the funded fee, not the delta. The
   question is whether a lower ceiling, as a `Policy` parameter with a default or as a factor in
   gateway selection, is worth the routes it would refuse. While it is open, the set says only
   that a delta above 1 440 blocks is refused.

## Answered

1. **Does the engine ship ON by default?** *Answered 2026-10-01 by `ADR-0039`: every wallet is
   auto-managed; accepting the standing instruction is how a wallet is created (`ADR-0035`).* `ADR-0014` makes the allocator the user's own
   on-device agent under a **standing instruction** given through an explicit acknowledgement
   before any funds are received; that acknowledgement is decided and not in question. The
   open question was whether automated management is the onboarding flow's default posture — the
   acknowledgement presented to every user, declined to opt out — or an option a user turns on.
   It turns on a fee-vs-risk expected-value computation at small balances and a legal opinion on
   the `ADR-0014` posture. While it was open, the set said what the standing instruction's
   parameters are (`OVR-8`) and nothing about which flow presents it.

2. **Is the wallet's total balance capped?** *Answered 2026-10-01 by `ADR-0040`: an optional
   `total_cap`, unset by default.* `ADR-0018` caps each federation (`per_fed_cap`,
   enforced by `OPS-7`), so the total a policy permits is that cap times the joined
   federations and rises with every join. The allocator cannot raise the total — it moves
   balance between federations (`ALC-9`) — so a ceiling would bind the inflows the user
   initiates (`receive`, `direct-inflow`) and would be a new `Policy` parameter with a default
   (`STO-13`, `API-20`). `ADR-0026` names a "willing-to-lose" pilot ceiling as an operator
   practice, not a wallet rule. While it was open, the set enforced the per-federation cap and
   was silent on an aggregate one.
