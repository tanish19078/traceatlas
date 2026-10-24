# TraceAtlas

**Company research you can trace back to the source.**

TraceAtlas turns a Norwegian organisation number into a company profile with
inspectable evidence. It collects official registry facts, checks reviewed
company websites, tracks changes over time, and builds a standalone HTML
explorer for reading the results.

The idea is simple: a useful company profile should explain where its facts
came from, when they were checked, and what is still unknown.

## What it does

- **Registry research:** legal identity, registered address, industry, business
  activity, registered employee counts and status, where the registry reports them.
- **Website verification:** checks the exact legal name and labelled organisation
  number before accepting a reviewed company page.
- **Structured jobs:** extracts attributed JSON-LD postings, checks employer
  identity and dates, and preserves the original record.
- **Dated news:** accepts individual, visible articles about the exact company, with publication dates and source records.
- **Legal reporting:** fetches reviewed news or HTML filing URLs and preserves
  dated passages about legal proceedings, including case references when reported.
- **Change history:** shows supported changes and keeps earlier evidence when a
  refresh fails or a source is no longer checked.
- **Recoverable batches:** resumes interrupted work after validating the inputs,
  configuration and saved evidence.
- **Evidence auditing:** checks published values against archived source snapshots.

Every claim has a source reference and retrieval date, plus a JSON pointer or
text span you can inspect. Missing information stays missing; an unavailable
employee count never becomes zero. Legal reports remain attributed reports,
with no inferred liability or court outcome.

## Try it locally

Requires Python 3.11+ with SQLite and HTTPS support. There are no third-party
runtime dependencies or required API keys.

```bash
git clone https://github.com/tanish19078/traceatlas.git
cd traceatlas
python -m examples.demo
```

Open `runs/demo/index.html` to explore the interface. The demo runs offline and
uses clearly labelled synthetic facts.

For live registry research, create `companies.txt` with one organisation number
per line, then run:

```bash
python -m traceatlas --input companies.txt --output runs/live --workers 4 --budget-seconds 300
python -m traceatlas.audit runs/live --input companies.txt
```

JSONL objects with an `organisation_number` or `organisasjonsnummer` field are
also accepted. Open `runs/live/index.html` to inspect the profiles and evidence.

You can also install the package with `python -m pip install .` to use the
`traceatlas` and `traceatlas-audit` commands.

## Add reviewed sources

Website and legal-source requests are opt-in. Review a source's access and reuse
terms before enabling its exact hostname; robots rules alone do not grant reuse
permission. The example domains below are placeholders.

To check a website supplied by the registry:

```bash
python -m traceatlas --input companies.txt --output runs/web --allow-domain company.example.com --timeout 20
```

Accepted pages must show the exact legal name and labelled organisation number.
Pages with multiple labelled company numbers or conflicting owner/publisher identities are rejected. A subsidiary in a group footer does not establish ownership. Structured job
postings must represent a single ad on its own URL, include a visible description, and match the employer; expired or future postings are skipped
as of retrieval. An absent expiry stays unknown.

For legal news and filings, create a `sources.json` map:

```json
{
  "923609016": [
    {
      "url": "https://news.example.com/report",
      "kind": "news",
      "access_reviewed": true
    }
  ]
}
```

```bash
python -m traceatlas --input companies.txt --output runs/legal --legal-sources sources.json --allow-domain news.example.com
```

Use `news` or `filing` for `kind`, with at most five URLs per company. The
extractor requires company identity, a nearby mention of legal proceedings and
an unambiguous publication date. It saves the HTML, supporting passage, dates
and source kind. The explorer labels these items **source report only**. An empty
or failed lookup does not establish that a company has no legal cases.

All external HTML requests use public HTTPS hostnames, checked DNS addresses,
TLS hostname verification, robots rules, response-size limits and shared
per-host rate controls. Redirects are not followed. Fixture mode stays offline.

## Frozen data and run controls

Use a supplied Brreg snapshot without live registry lookups:

```bash
python -m traceatlas --input companies.txt --bulk registry.csv --output runs/frozen --supervised --budget-seconds 2700
```

CSV and API-shaped JSONL are supported; gzip is detected from the contents,
including compressed files named `.csv`. Only requested companies are retained
in memory. The file hash and original selected rows are preserved in the evidence.
A missing company remains explicitly unavailable; there is no live fallback.
Bulk input is separate from synthetic `--fixtures` mode.

The CLI defaults to 45 minutes and at most 20 request attempts per input company,
shared across workers, including robots requests and failed attempts. Use
`--max-requests` to lower that cap. HTTP 429 starts a shared host cooldown and
honors `Retry-After`. No request is made if the cooldown outlasts the deadline.

`--supervised` runs research in a separate worker process, reserves finalization
time, and stops a stalled worker before the budget. Checked completed results
survive; unfinished inputs receive explicit failed results. If a worker is
terminated, the report labels checkpoint request counts as a lower bound.

## Refresh or resume

Run again with the same output directory for a fresh observation and change
history. To recover interrupted work instead:

```bash
python -m traceatlas --input companies.txt --output runs/live --resume
```

Keep the original input, fixtures, source map and hostname allowlist. Resume
checks their fingerprints and archived evidence, reuses completed results with
their original timestamps, and retries failed or blocked rows. An exclusive lock
prevents concurrent writers from using the same output directory.

## Output

| File | Purpose |
| --- | --- |
| `index.html` | Standalone evidence explorer, availability states and refresh changes |
| `envelopes.jsonl` | Validated interchange output with availability, evidence references and operations |
| `profiles.jsonl` | Company profiles in input order |
| `snapshots/` | Original registry JSON and accepted HTML, named by content hash |
| `history.sqlite3` | Observations and latest supported profiles |
| `completion.jsonl` | Flushed results for recovery |
| `run.json` | Input and configuration fingerprints |
| `report.json` | Counts, duration and run limitations |

Preserve the complete output directory when archiving a run. Previous supported
facts appear as `last_known` when they cannot be treated as current. Source data
retains its original attribution and reuse conditions.

## Development

Application code lives in `traceatlas/`, regressions in `tests/`, and the offline
demo in `examples/`. Generated output under `runs/` is excluded from Git.

```bash
python -m unittest -v
python -m examples.demo
python -O -m traceatlas.audit runs/demo --expected-count 1
```

The 127-test suite covers company matching, source integrity, legal-report dates,
refresh history, recovery, output escaping and network safeguards. CI runs on
Python 3.11, 3.12 and 3.13 and checks installation outside the checkout.

A live registry check on 17 October 2026 returned 100 profiles with 809 audited
claims in 101.6 seconds using eight workers. A separate offline recovery check
processed 1,000 rows and audited 2,700 claims. These checks establish execution
and stored support, not the completeness of information found online.

## Current limits

Automatic source discovery, broad leadership and financial extraction, and PDF
parsing are not implemented. Legal research uses supplied reviewed URLs. Website
and legal-source integration are tested with offline HTML fixtures; successful
live external retrieval has not yet been validated in this environment.

Direct Python API calls use a soft deadline. The supervised CLI can stop a
stalled research worker, but final filesystem writes are not preemptible. The auditor verifies support in saved snapshots; it cannot independently
establish that a source is truthful or that every relevant fact was found.

Registry facts come from [Brønnøysundregistrene's public entity API](https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html).
