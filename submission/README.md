# TraceAtlas revision notes

The organizer confirmed the original `a856e2f` entry as version 1. New Git commits
do not update that frozen entry automatically. Send a reviewed revision hash
separately; do not treat repository development as a submitted version.

The current challenge page accepts new entries and revisions through November 7.
The organizer's 23 October clarification specifies 45 minutes and 2,000 requests
per 100 companies, supplied organisation-number inputs, optional frozen registry
input, and the starter kit's `OUTPUT_CONTRACT.md`.

- [Current challenge](https://builderr.ai/challenges/signalpost)
- [Starter kit containing OUTPUT_CONTRACT.md](https://builderr.ai/signalpost-starter-kit.tar.gz)
- [Source policy](https://builderr.ai/starter-briefs/signalpost-sources.md)

## Run command

Python 3.11–3.13; no package install, model key, or paid service is required for
the standard run. It uses the live public registry and deterministic company
website discovery across up to three name/town-derived domains. The optional
Brave integration requires an approved `BRAVE_SEARCH_API_KEY` and makes one
billed query with at most one social-focused follow-up per company.

```bash
python -m traceatlas --input /path/to/companies.jsonl --output runs/evaluation --workers 8 --budget-seconds 2700 --discover-websites --supervised --run-id official-run
```

Replace the paths and run ID with those supplied for the run. Omit `--bulk` only
when live registry lookup is intended. `--output` is a directory. The contract
result is **`runs/evaluation/envelopes.jsonl`**; native profiles, snapshots, history,
HTML explorer and `report.json` are kept alongside it.

Add `--bulk /path/to/frozen-registry.csv` only when the evaluator supplies a
frozen registry file. Add `--search-websites` only when the evaluator supplies
an approved reproducible Brave credential; never use a personal account key.

The input accepts text or JSONL organisation numbers. Frozen data supports Brreg
CSV (comma or semicolon separated) or API-shaped JSONL; gzip is detected by its
magic bytes even if the name ends in `.csv`. CSV dotted fields are normalized
with the original row and file hash preserved. Requested companies missing from
the supplied file return explicit unavailable results; there is no live fallback.
Bulk data is genuine supplied data, distinct from synthetic `--fixtures` mode.

Website research remains opt-in through reviewed `--allow-domain` hostnames,
deterministic `--discover-websites` candidates, or `--search-websites`. Search
discovery requires `BRAVE_SEARCH_API_KEY` and makes up to two Brave Search API
requests per company at its current listed rate of $5 per 1,000 requests. Search
results only nominate pages for direct exact-identity checks. The key stays in
the environment and is not written to run artifacts. Do not use a personal
Brave account for an official run; enable search only if the evaluator supplies
an approved reproducible credential. Additional reviewed legal sources use
`--legal-sources`. No implicit assertion of source access rights is made for
unseen registry domains.

## Audit changes

- Site ownership checks reject conflicting Organization/WebSite publisher
  identities and group headings/footer-only subsidiary matches. Explicit
  `legalName` takes precedence over a brand `name`; full Schema.org type URLs
  and tax identifiers participate in the owner check. Each child page
  is checked independently; no parent social accounts are propagated. The
  crawler prioritizes company news links and follows a news index to its story
  links within a five-page same-host limit. A single consistent homepage
  description is included in the summary only after site ownership verifies.
- A job requires one distinct JobPosting on an individual page, a matching ad
  URL, an exact employer, a dated record and a description present in visible
  HTML. Root, careers and search/listing pages are rejected.
- Company news uses a structured NewsArticle when present, with a matching
  individual URL, visible headline and article, exact company attribution in
  metadata and visible text, and `datePublished`. When article schema is absent,
  one visible article with a headline, exact legal name or labelled organisation
  number, and one consistent past publication date is accepted. Menu labels,
  Product records, collection pages and feed `updated`/`dateModified` timestamps
  are not accepted as news or publication dates.
- External legal news requires identity inside the article, a single dated
  Article/NewsArticle with matching URL and a visible headline. A site footer
  cannot attribute the story. Legal reports remain source reports, not findings
  of liability or court outcomes.
- Every network attempt, including robots and failed attempts, consumes the
  shared request budget. The default ceiling is 20 attempts per input, and
  `--max-requests` can lower it. HTTP 429 establishes a shared host cooldown using
  Retry-After, with a conservative default when the header is absent/invalid.
- `--supervised` stops a stalled research worker before the wall-clock budget,
  then validates completed checkpoints and writes failed rows for unfinished
  inputs. It also finalizes rows after an early worker crash. Final filesystem
  operations are not preemptible. Telemetry after termination is explicitly a
  lower bound; uncompleted attempts are not presented as precisely measured.

## Output compatibility

`envelopes.jsonl` follows the minimal `OUTPUT_CONTRACT.md`: `organisation_number`,
`run` with ID/timestamps/terminal status, claims with availability/confidence and
`evidence_ids`, evidence with source/date/hash/literal excerpt, changes, errors,
and operations with requests/runtime/cost. Native pointers, spans and snapshots
retain full support. `profiles.jsonl` remains the native auditable representation.
The older starter batch script has a different module-state wrapper; this adapter
intentionally targets the named OUTPUT_CONTRACT rather than that legacy wrapper.

Confidence is an explicit deterministic support policy: 1.0 for exact registry
reproduction, 0.9 for accepted external records, and 0 for unavailable fields.
These are not calibrated probabilities of source truth. Original availability
reasons distinguish unresearched fields from searches with no supported result.
Resume keeps original evidence timestamps and reports zero new cached requests.
Latency percentiles measure executed per-company research work, excluding queue
and bulk-loading time; total run duration is reported separately.

## Reproducible development smoke check

```bash
python -m traceatlas --input submission/smoke-input.txt --bulk submission/audit-registry-sample.csv --output runs/audit-smoke --workers 8 --supervised --run-id local-audit-check
python -O -m traceatlas.audit runs/audit-smoke --input submission/smoke-input.txt
```

`audit-registry-sample.csv` is a selected-column development sample derived from
the current public Brreg CSV on 24 October 2026, under the source's NLOD 2.0
conditions. It is **not Builderr's official frozen batch**. A scan of the first
50,001 source rows found 98 of the 100 original smoke input numbers; the sample
contains those 98 records. Two inputs are intentionally retained to exercise
missing-row behavior. No claim is made that those companies are absent from the
complete current register. The report records the sample file hash.

The smoke check emits 100 terminal results, 98 available registry profiles and
two explicit unavailable results, with zero outbound requests. Source support
and contract validation pass. Replaying the same file produces no false changes.
See `audit-smoke-report.json`. The older live `smoke-report.json` is retained as
historical execution evidence, not a score for this revision.

## Models, costs, source rights and remaining limits

No model API or paid feed is used. The default registry-only command has no
third-party API charge; enabling Brave search adds up to $0.01 per company at
the current listed rate, excluding compute, storage and bandwidth. Official
run search requires an evaluator-approved credential; personal service accounts
are not reproducible. Default live identity calls use Brreg's fixed public
entity endpoint; official registry data declares NLOD 2.0. Optional
sites/news/filings retain their own rights and require a documented access/reuse
review before enabling hosts. Robots permission is not a reuse licence.

Python uses the PSF licence and bundled notices. Build-only setuptools 84.0.0
uses MIT; checkout/setup-python are pinned official action releases. TraceAtlas
remains author-owned public code without an asserted general reuse licence.

The 150 offline tests include bulk parsing/provenance, contract integrity,
concurrent request caps, Retry-After, parent attribution, article/job validation,
refresh, resume and worker termination; one Windows symlink test is skipped
when the runner lacks symlink privilege. The documented 100-company offline
smoke run completed with 100 results, 805 audited claims, 98 available registry
profiles and two explicit unavailable results, using zero outbound requests.
Registry and annual-account retrieval were checked on a three-company live
sample, and website retrieval has limited live sample coverage. Search API
discovery was not exercised in that sample because it is billed and requires an
approved credential. Annual-account revenue, registered roles and sub-entities
are extracted from official registry APIs. Open-web source discovery, broad
leadership coverage and PDF extraction remain incomplete. No official score,
recall measurement or qualification is claimed. The organizer must accept and
run the revised exact commit before it changes the entry of record.
