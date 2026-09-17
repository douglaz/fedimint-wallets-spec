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

1. **Does the engine ship ON by default?** `ADR-0014` makes the allocator the user's own
   on-device agent under a **standing instruction** given through an explicit acknowledgement
   before any funds are received; that acknowledgement is decided and not in question. What is
   undecided is whether automated management is the onboarding flow's default posture — the
   acknowledgement presented to every user, declined to opt out — or an option a user turns on.
   It turns on a fee-vs-risk expected-value computation at small balances and a legal opinion on
   the `ADR-0014` posture. Until answered, the set says what the standing instruction's
   parameters are (`OVR-8`) and nothing about which flow presents it.

2. **Is the wallet's total balance capped?** `ADR-0018` caps each federation (`per_fed_cap`,
   enforced by `OPS-7`), so the total a policy permits is that cap times the joined
   federations and rises with every join. The allocator cannot raise the total — it moves
   balance between federations (`ALC-9`) — so a ceiling would bind the inflows the user
   initiates (`receive`, `direct-inflow`) and would be a new `Policy` parameter with a default
   (`STO-13`, `API-20`). `ADR-0026` names a "willing-to-lose" pilot ceiling as an operator
   practice, not a wallet rule. Until answered, the set enforces the per-federation cap and is
   silent on an aggregate one.

3. **What bounds a browser-sidecar login attempt?** `ADR-0028` requires the sidecar's login
   to be rate-limited ("Rate limiting is required, not optional") and decides nothing about the
   bound: how many failed attempts, in what window, keyed by what — the client address, the
   whole listener — and whether the refusal is a delay or a `429`. Behind the reverse proxy the
   ADR contemplates every request arrives from `127.0.0.1`, so keying by address needs a
   forwarded-address rule the ADR also does not give. `HST-31` requires the limit and is silent
   on its parameters until an ADR fixes them.

## Answered

*(none yet)*
