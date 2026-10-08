# TraceAtlas

**Company intelligence, backed by evidence.**

TraceAtlas researches Norwegian companies by organisation number and preserves
the source behind every published fact. The current release retrieves official
registry records, saves source snapshots, tracks changes and generates an HTML
evidence explorer.

## Quick start

Python 3.11+ with SQLite and HTTPS support. No third-party dependencies or API
keys are required for the current registry connector.

```bash
git clone https://github.com/tanish19078/traceatlas.git
cd traceatlas
python demo.py
```

Open `runs/demo/index.html`. The offline demo uses explicitly labelled synthetic
facts; it is an interface demonstration, not research about a real company.

For live research, put one organisation number per line in `companies.txt`:

```bash
python traceatlas.py --input companies.txt --output runs/live --workers 4 --budget-seconds 300
python verify_evidence.py runs/live
```

JSONL inputs with `organisation_number` or `organisasjonsnummer` are also accepted.
Use the same output directory on subsequent runs to inspect supported changes.
Use a separate directory for independent evaluations; concurrent writers to one
directory are not supported.

## Results

| File | Contents |
| --- | --- |
| `profiles.jsonl` | Company results in input order, with claims and availability states |
| `snapshots/<sha256>.json` | Original registry responses |
| `history.sqlite3` | Observations and latest supported profiles |
| `report.json` | Run counts, duration and declared limitations |
| `index.html` | Evidence explorer with sources and refresh changes |

Each claim carries a source hash, retrieval timestamp, extraction method and
JSON pointer to the supporting value. Reporting periods remain unset when the
source provides none. Missing employee counts are not replaced with zero.
Unsuccessful refreshes expose previous evidence as `last_known`.

Exit code `0` means no input ended in `failed`, not that all information was
available. Exit code `2` means at least one input failed. Missing, blocked and
ambiguous results are explicit.

## Verification

```bash
python -m unittest -v
python demo.py
python verify_evidence.py runs/demo
```

The current suite contains 22 regression tests covering identity mismatches,
missing values, source integrity, refresh behavior, batch completion and output
escaping. The auditor checks saved claims against source snapshots; it does not
independently establish source truth or external recall.

A live operational check on 8 October 2026 returned 100 results from 100 public
registry inputs, with 803 claims verified against their saved responses, zero
failed lookups and a runtime of 149.473 seconds with four workers. Inputs came
from the first page of the registry API, not a random or contest-universe sample.
This check is not an official competition score. The input-file SHA-256 was
`4e2acffa8bd2308ef7ed21e1924fdcb2162342aa1babd7317e1ffdb52cb47b02`.

## Current scope

This release is a registry baseline. Website discovery and exact-domain
verification, external leadership/jobs/news/financial research, and adaptive
agent planning are not implemented. Registry website fields remain unverified
candidates. There is no official qualification result.

The organizer's exact input/output adapter, larger-batch validation and hard
execution deadline still need to be completed. The current budget is a soft
work deadline; network/thread cleanup may exceed it. A storage failure can
interrupt export. Audit checks currently use Python assertions: run the auditor
without `-O` until explicit validation replaces them.

## Sources and access

The connector requests only the fixed HTTPS Brønnøysundregistrene entity endpoint.
It follows no redirects, bounds concurrency to 1–8 workers, limits responses to
2 MB and uses request timeouts. No paid APIs or models are used in this release.

Company URLs are candidates until verified against the exact legal entity.
Search snippets cannot support published facts. Future connectors must use
permitted access, preserve evidence and keep parent/subsidiary facts distinct.

Runtime data and databases are excluded from Git. Preserve the complete output
directory when archiving evidence; do not publish credentials or private data.
Source data retains its original attribution and reuse conditions.

- [Registry API documentation](https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html)
- [Signalpost challenge](https://builderr.ai/challenges/signalpost)
- [Evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md)
- [Permitted source policy](https://builderr.ai/starter-briefs/signalpost-sources.md)
