# TraceAtlas

**Company intelligence, backed by evidence.**

TraceAtlas is an evidence-preserving research agent for Norwegian companies.
Its first working milestone retrieves official registry facts, validates the
organisation number, saves immutable source snapshots, and explains changes
between runs. A portable evidence explorer lets you inspect each claim.

> **Status: registry baseline, not competition-ready.** Public website discovery,
> exact domain verification, external jobs/news/financial extraction and model
> synthesis are planned. No official score or qualification is claimed.

## Run in under a minute

Requires **Python 3.11 or newer** with SQLite and HTTPS support. There are **no
third-party Python dependencies, paid APIs, or model keys** in this baseline.

```bash
git clone https://github.com/tanish19078/traceatlas.git
cd traceatlas
python demo.py
```

Open `runs/demo/index.html` for the offline demonstration. The example is
conspicuously labelled **synthetic** and must not be used as company research.

Audit saved claims against their original source bodies:

```bash
python verify_evidence.py runs/demo
```

Run tests:

```bash
python -m unittest -v
```

For real research, create `companies.txt` with one Norwegian organisation number
per line (or JSONL objects with `organisation_number`), then run:

```bash
python traceatlas.py --input companies.txt --output runs/live --workers 4 --budget-seconds 300
```

The command writes:

| Artifact | Purpose |
| --- | --- |
| `profiles.jsonl` | Exactly one terminal envelope per input row, in input order |
| `snapshots/<sha256>.json` | Immutable original registry response bodies |
| `history.sqlite3` | Observations and latest supported profiles |
| `report.json` | Counts, elapsed time, mode and limitations |
| `index.html` | Local, responsive evidence explorer |

Re-run against the **same output directory** to preserve history and inspect
changes. Use a new directory for isolated evaluations. Do not run two writers
against the same output directory concurrently. Runtime artifacts are ignored by
Git; preserve the complete directory when archiving evidence.

Exit code `0` means no input ended in `failed`; it does **not** mean every company
was found. Exit code `2` means one or more inputs failed. Missing and blocked
sources have distinct states. Invalid inputs still receive envelopes.

## What makes the facts traceable?

Each claim includes its field, supported value, evidence hash, extraction method
and exact JSON pointer. Evidence records include source URL, retrieval timestamp,
parser version and a snapshot location. Reporting periods remain null when the
source provides none. Registered dates are not substituted for financial periods.

- Identity must match the requested organisation number exactly.
- A website in the registry is an **unverified candidate**, never automatic proof
  that a brand or group site belongs to the requested entity.
- Missing employee counts stay missing. A genuine registered zero stays zero.
- Failed refreshes expose stale values under `last_known`, not as current claims.
- Identical source snapshots cause no false fact changes.
- A disappearing source field is `no_longer_reported`, not a claim that something
  stopped existing in the real world.
- Facts from source text are escaped before they appear in the HTML viewer.

## Competition contract and limits

The current CLI is TraceAtlas's own documented baseline interface. Adaptation to
the organizer's exact supplied input/output schema is still required. The local
smoke test is an operational check, not the hidden evaluation or a measured recall
score. This version intentionally leaves external information unresearched.

There is at most one registry request per valid input, bounded concurrency (1–8),
a per-request timeout, a 2 MB response limit and no redirects. Work that cannot
start before the soft batch deadline emits a failure envelope. Python/OS network
and thread cleanup may exceed the deadline slightly; a hard process deadline and
checkpointed recovery remain on the roadmap. There are no retry storms or paid
fallbacks. No runtime dependency installation is necessary.

## Build plan

See [ROADMAP.md](ROADMAP.md) for milestones, evaluation gates and submission
questions; [SECURITY.md](SECURITY.md) for source and data boundaries.

The project prioritizes exact-company precision, then useful external coverage.
Small, meaningful commits document working improvements and regression fixes.

## Sources

- [Brønnøysundregistrene API documentation](https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html)
- [Signalpost challenge](https://builderr.ai/challenges/signalpost)
- [Evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md)
- [Permitted source policy](https://builderr.ai/starter-briefs/signalpost-sources.md)

Registry data remains subject to its original attribution and reuse conditions.
The code license does not relicense source data or company content.
