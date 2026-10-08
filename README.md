# TraceAtlas

**Company intelligence, backed by evidence.**

TraceAtlas researches Norwegian companies by organisation number and preserves
the source behind every published fact. The current release retrieves official
registry records, optionally verifies reviewed company websites, saves source
snapshots, tracks changes and generates an HTML evidence explorer.

## Quick start

Python 3.11+ with SQLite and HTTPS support. No third-party dependencies or API
keys are required. Website research is disabled by default.

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

To research a registry-provided website, review its access/reuse terms first,
then enable its exact hostname (repeat the flag for additional reviewed hosts):

```bash
python traceatlas.py --input companies.txt --output runs/web --allow-domain company.example.com --timeout 20
python verify_evidence.py runs/web
```

The hostname above is illustrative. Allowlisting is your explicit declaration
that access was reviewed; robots rules alone do not grant permission. The
connector requires the exact organization number and legal name together on
every accepted page. Multiple labeled organization numbers cause rejection.
It publishes identity passages, not inferred leadership, jobs or finances.
Redirects require a separately reviewed candidate; no redirects are followed.
Fixture mode never requests external websites.

## Results

| File | Contents |
| --- | --- |
| `profiles.jsonl` | Company results in input order, with claims and availability states |
| `snapshots/<sha256>.json` / `.html` | Original registry responses and verified website pages |
| `completion.jsonl` | Flushed terminal results in completion order; diagnostic checkpoint, not automatic resume |
| `history.sqlite3` | Observations and latest supported profiles |
| `report.json` | Run counts, duration and declared limitations |
| `index.html` | Evidence explorer with sources and refresh changes |

Each claim carries a source hash, retrieval timestamp, extraction method and
JSON pointer or exact visible-text span to the supporting value. Reporting periods remain unset when the
source provides none. Missing employee counts are not replaced with zero.
Unsuccessful refreshes expose previous evidence as `last_known`. A registry-only
refresh also retains earlier website evidence as historical, not current.

Exit code `0` means no input ended in `failed`, not that all information was
available. Exit code `2` means at least one input failed. Missing, blocked and
ambiguous results are explicit.

## Verification

```bash
python -m unittest -v
python demo.py
python verify_evidence.py runs/demo
```

The current suite contains 47 regression tests covering identity mismatches,
missing values, source integrity, partial refreshes, batch completion, output
escaping, private-network targets, DNS pinning, robots rules and website evidence.
The auditor uses explicit validation and also works under `python -O`. Empty and
incomplete exports fail verification; use `--expected-count` for an independent
expected row count. The auditor checks saved claims against source snapshots; it does not
independently establish source truth or external recall.

GitHub Actions runs the regression suite, offline demo, optimized audit and
compilation checks on Python 3.11, 3.12 and 3.13 for pushes and pull requests.
Action dependencies are pinned to verified release commit hashes; the workflow
uses read-only repository access and does not retain checkout credentials.

A separate offline scale check processed 1,000 input rows (900 duplicate valid
fixture inputs and 100 deliberately invalid inputs), retained input ordering,
and audited all 2,700 current claims successfully. This checks completion and
storage behavior; it does not measure live throughput, entity diversity or
external recall.

A live operational check on 8 October 2026 returned 100 results from 100 public
registry inputs, with 803 claims verified against their saved responses, zero
failed lookups and a runtime of 149.473 seconds with four workers. Inputs came
from the first page of the registry API, not a random or contest-universe sample.
This check is not an official competition score. The input-file SHA-256 was
`4e2acffa8bd2308ef7ed21e1924fdcb2162342aa1babd7317e1ffdb52cb47b02`.

## Current scope

This release supports official registry facts and opt-in verification of
registry website candidates. Search discovery, external leadership/jobs/news/
financial extraction and adaptive agent planning remain incomplete. Unreviewed
or unverifiable domains stay unverified. There is no official qualification result.

The organizer's exact input/output adapter, hard execution supervisor, automatic
resume and evaluation of external recall remain to be completed. The current
budget is a soft deadline; DNS/network/thread cleanup may exceed it. Individual
worker or record-storage errors produce failed results while other inputs
continue; failure of the output directory/journal can still interrupt the run.

Website retrieval and its integration are tested offline with synthetic pages.
A live website probe in this development environment failed at direct DNS
resolution, so successful live website retrieval has not yet been validated.
The earlier 100-company live check above covers the registry connector only.

## Sources and access

Registry retrieval uses the fixed HTTPS Brønnøysundregistrene entity endpoint,
1–8 workers and a 2 MB response limit. Opt-in website retrieval accepts only
HTTPS public hostnames on the reviewed allowlist, rejects private or mixed DNS
answers and connects to the checked address with TLS hostname verification.
It honors robots rules, serializes requests per host across workers, enforces
at least one second between requests and honors longer observed crawl delays.
Each site session allows five requests including robots, at most three verified
pages and 1 MB per response. Redirects are never followed. No paid APIs or
models are used.

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
