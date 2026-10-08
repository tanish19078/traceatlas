# TraceAtlas build plan

Company intelligence, backed by evidence.

## Product promise
Given a Norwegian organisation number, return an attributable company profile,
inspectable evidence, explicit unknowns and a history of supported changes.
The primary improvement hypothesis is higher external-information coverage
without publishing facts under the wrong legal entity.

## Delivery milestones

1. **Reproducible foundation**: strict input handling, typed evidence records,
   six availability states, one terminal result per input, offline fixtures.
2. **Official identity**: Brønnøysundregistrene connector; immutable response
   snapshots; exact-number check; registered employee-count semantics.
3. **History and inspection**: SQLite observations, idempotent claims, changed
   values and preserved evidence; portable, escaped HTML evidence viewer.
4. **Verified public identity**: website candidates, company-number/legal-page
   proof, parent/subsidiary ambiguity fixtures, source access policy registry.
5. **External coverage**: sitemap/contact/careers/news connectors, structured
   data before model extraction; evidence spans for each published claim.
6. **Adaptive research**: allocate request/time budget to missing field families;
   stop before deadlines; licensed search only for candidate discovery.
7. **Evaluation**: separate development/validation/final companies and hosts;
   hand-labelled identity and facts; precision, coverage, runtime, cost and
   false-change metrics; 100-company smoke report; larger batch stress test.
8. **Submission**: clean clone test, exact commit, documented API/model costs,
   source permissions and evaluator format; demo; submit only with user approval.

## Acceptance gates
- Exactly one output for every input row, including duplicates and bad inputs.
- Every claim resolves to an immutable snapshot and an exact JSON pointer/span.
- Missing is never coerced into zero. An unverified website is a candidate only.
- Identical snapshots do not create duplicate facts or false changes.
- Failed refreshes preserve last supported information and disclose the failure.
- No secrets or collected production data committed to Git.
- Offline tests are deterministic and labelled synthetic; live tests are separate.
- A local smoke test is not an official score or evidence of prize qualification.

## Schedule (target, not a promise)
- Oct 8–9: foundation, official records, history and inspection.
- Oct 10–12: identity verification and permitted external discovery.
- Oct 13–14: blind validation, coverage improvements and budget enforcement.
- Oct 15–16: scale checks, demo and first submission preparation.
- Before Oct 18: use remaining allowed submission revisions deliberately.

## Rules to confirm with organizers
Unstop and Builderr currently conflict. The organizer's evaluation contract
specifies 50 coverage, 30 evidence, 12 synthesis and 8 UX points, 65 overall to
qualify, a local 100-company smoke test, runtime-provided official company batches,
and at most five submitted versions. Exact first-entry cutoff/timezone, evaluator
input/output schema, resource budget and provisioned search/model credentials
must be confirmed before the first submission. Do not assume the old daily
100-company / $10 / 2,000-request listing is the current contract.

Sources reviewed 2026-10-08:
- https://builderr.ai/challenges/signalpost
- https://builderr.ai/docs/signalpost-evaluation-harness.md
- https://builderr.ai/starter-briefs/signalpost-sources.md
- https://builderr.ai/starter-briefs/signalpost-agent-playbook.md

## Commit practice
One coherent, working change per commit: a connector, a bug fix with a regression
test, an evaluation improvement, or a useful documentation/UI change. Preserve
reviewable history. No empty commits, fabricated dates, or splitting trivial
changes to inflate counts. Competition submissions pin selected tested commits;
they do not require submitting every development commit.
