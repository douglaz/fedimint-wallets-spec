# 11 — Open questions

Decisions nobody has taken. They are not findings against the code: the code is built so that
either answer remains possible, and nothing in this set changes when one is taken except the
sentence that says it is open. Findings against the code — what it does not yet do that a
document, an ADR or a review said it should — live beside the code, in the code repository's
[`docs/open-findings.md`](https://github.com/douglaz/fedimint-wallets/blob/main/docs/open-findings.md),
because each one names the issue that tracks it and closes with the pull request that fixes it.

A question is answered by an ADR, never by editing it away here: when one is decided, the entry
below is kept, marked with the ADR that answered it and the date, so a reader who was told it
was open can see where it landed.

## Open

1. **Is the long-running deployment a test or a pilot?** The daemon has been running the
   2026-07-26 build `b5f46de` on two mainnet federations with a small real-sats balance. The
   code repository's release issues (`br-prod-canary-nab`, `br-recanary-y2j-ujs`) and its
   alerting issue (`br-rky`) still treat it as production; the operator has since said it is a
   test rig, and the code repository's `AGENTS.md` was changed to say so on 2026-09-08. Every P1
   release/ops item in the backlog inherits its priority from the first reading. This set
   records the second: `08-hosts-and-deployment.md` describes the deployment as a test
   (`HST-23`).
2. **Does the engine ship ON by default?** The code repository's `docs/roadmap-to-v1.md` defers
   this to Phase 8: a fee-vs-risk expected-value computation at $50–$500 balances plus a legal
   opinion on the `ADR-0014` posture. Nothing in Phases 4–7 depends on the answer.
3. **Which frontend is next?** The roadmap says the web sidecar (6c) ships before Android (6b).
   6c's issues were cut on 2026-07-30 and have not moved; the work since went into the money
   paths (`F1`–`F9` in the findings file).

## Answered

*(none yet)*
