# TraceAtlas submission

Requirement review: 17 October 2026. The organizer's current challenge page and
version 2 contract control over older summaries in the Unstop listing.

- [Challenge and submission destination](https://builderr.ai/challenges/signalpost)
- [Evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md)
- [Permitted sources](https://builderr.ai/starter-briefs/signalpost-sources.md)

The current instructions request a 100-company smoke-test result or report, not
1,000 precomputed profiles. Submission is by email to **submit@builderr.ai** with
the repository URL, exact commit hash, run command, models/APIs/licences, expected
cost and contact details. The page lists closing on October 21 and revisions
before October 18 (maximum five submitted versions). No precise cutoff timezone
was found; submit promptly rather than assuming an end-of-day grace period.
Registering on Unstop alone is not a Builderr submission.

## Evaluator execution

Python 3.11–3.13 with HTTPS and SQLite. There are no third-party runtime packages
or required secrets. From the root of the exact checkout:

```bash
python -m traceatlas --input /path/to/official.jsonl --output runs/evaluation --workers 8 --budget-seconds 300 --timeout 12
```

Replace the input path and time budget with those supplied by Builderr. Every
row is read from that file; the smoke list is never substituted. Text (one number
per line) and JSONL objects containing `organisation_number` or
`organisasjonsnummer` are accepted. Output is a directory containing ordered
`profiles.jsonl`, `report.json`, snapshots, history and `index.html`. Each envelope
includes identity, claims, evidence, field states, refresh data and errors.

If an installed command is preferred, the declared install step is
`python -m pip install .`; the build backend is pinned to setuptools 84.0.0.
The direct module command above requires no package install. Optional reviewed
websites/legal sources use explicit CLI flags documented in the project README.
No source domains are implicitly allowed for an official run.

## Evidence of execution

[Smoke report](smoke-report.json) and [100 input numbers](smoke-input.txt) are public.
On 17 October 2026 the first 100 entries of the hash-verified organizer universe
produced 100 available registry results, 809 audited claims, no failed rows, and
101.612 seconds elapsed with eight workers. The optimized auditor also passed.
The complete evidence output is retained separately; this small public report
is the run-report artifact permitted by the challenge. The report records input,
profile and universe hashes. Re-running live sources may produce different facts.

This measures registry execution and stored support. It is neither a competition
score nor a demonstration of external recall, legal coverage or website access.

## Models, APIs, cost and licences

- Models: none. No model key or personal account credential is required.
- Default API: public Brønnøysundregistrene Enhetsregisteret entity API, fixed host.
  Its [official documentation](https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html)
  declares NLOD 2.0. Each registry claim preserves source attribution and date.
- Optional company sites, news and HTML filings: per-source access and reuse terms
  must be reviewed before URLs and exact hostnames are enabled. Robots permission
  alone is not a reuse licence. No paid search or licensed feed is bundled.
- External API/model charges: expected USD 0 per default run; no paid service is
  called. Evaluator compute, storage and bandwidth are excluded from that figure.
- Runtime: Python standard library (PSF licence and its bundled notices); SQLite
  is supplied by the evaluator's Python installation. Build-only setuptools uses
  MIT; GitHub Actions uses pinned official checkout/setup-python releases.
- TraceAtlas code: author-owned public repository; no general reuse licence is
  asserted by this submission. Evaluation access follows the submitted entry and
  organizer rules. Source data keeps its original rights and conditions.
- Caches: default runs make fresh registry requests; no universe facts are used
  as research answers. `--resume` reuses declared, evidence-checked output with
  original timestamps; omit it for an official fresh run unless permitted.

## Alignment and remaining gaps

| Requirement | TraceAtlas status |
| --- | --- |
| Supplied batch, one terminal row per input | Implemented; 100-company live and 1,000-row offline checks |
| Exact entity and inspectable evidence | Registry anchor, website proof, hashes, pointers/spans, dates |
| Missing values and failures | Explicit six-state results; no missing employee count converted to zero |
| Refresh and provenance | Stable claim IDs, changes, retained history, evidence-checked resume |
| Reproducible run and public report | Module command, no runtime dependencies, report and input hashes |
| External discovery and broad recall | Limited: reviewed website candidates/jobs and supplied legal URLs |
| Legal news/filings | Dated, attributed source reports; no legal conclusions, no PDF parsing or source search |
| Hard execution deadline | Not implemented: DNS/network/thread cleanup can exceed the soft budget |
| Official frozen-registry integration | Not implemented; `--fixtures` means synthetic test mode, not official frozen data |
| Official score / qualification | Not measured; do not claim qualification |

Legal reports are not judgments or findings of liability. A failed or empty
legal lookup never establishes absence of cases. Live external retrieval remains
unvalidated because direct DNS retrieval failed in this development environment.
The organizer may require adjustments to its actual evaluator interface or frozen
registry delivery; request those details in the submission rather than claiming
an untested integration. Limited external recall is the principal scoring gap.
