"""Command-line research interface."""
import argparse
import csv
import json
import math
import sys
import uuid
from .core import read_inputs, run_batch
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Text or JSONL organisation numbers')
    parser.add_argument('--output', default='runs/latest')
    parser.add_argument('--supervised', action='store_true', help='Stop a stalled worker before the time budget and finalize missing results')
    parser.add_argument('--internal-worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--run-id', help='Identifier written to the contract export and run report')
    parser.add_argument('--bulk', help='Evaluator-supplied frozen Brreg CSV or API JSONL; gzip detected automatically')
    parser.add_argument('--fixtures', help='Offline JSON response folder; clearly labelled synthetic')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--budget-seconds', type=float, default=2700)
    parser.add_argument('--max-requests', type=int, help='Lower the shared request cap (at most 20 per input company)')
    parser.add_argument('--timeout', type=float, default=12)
    parser.add_argument('--allow-domain', action='append', default=[], help='Reviewed public website hostname; enables opt-in website research (repeatable)')
    parser.add_argument('--legal-sources', help='Reviewed JSON map of company numbers to news/filing URLs; also requires --allow-domain')
    parser.add_argument('--resume', action='store_true', help='Reuse evidence-checked terminal results from the same batch; retry failed/blocked inputs')
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8 or any(not math.isfinite(value) or value <= 0 for value in (args.budget_seconds, args.timeout)):
        parser.error('workers must be 1..8; budget and timeout must be positive')
    from .web import normalize_url
    from urllib.parse import urlsplit
    domains = []
    for domain in args.allow_domain:
        try:
            if any(c in domain for c in '/:@?#'):
                raise ValueError('hostname only')
            domains.append(urlsplit(normalize_url(domain)).hostname)
        except ValueError:
            parser.error('allow-domain must be a public HTTPS hostname')
    if args.fixtures and args.bulk:
        parser.error('bulk and fixtures are mutually exclusive')
    if args.fixtures and (domains or args.legal_sources):
        parser.error('fixture mode never makes website requests')
    try:
        numbers = read_inputs(args.input)
    except (OSError, UnicodeError):
        parser.error('input file must be readable UTF-8 text')
    if not numbers:
        parser.error('input file must contain at least one organization number')
    try:
        from .legal import load_sources
        legal_sources = load_sources(args.legal_sources) if args.legal_sources else None
        if legal_sources and not domains:
            parser.error('legal sources require reviewed --allow-domain hosts')
        if args.supervised and not args.internal_worker:
            from .supervisor import supervise
            run_id = args.run_id or 'traceatlas-' + uuid.uuid4().hex[:12]
            command = [sys.executable, '-m', 'traceatlas', *(sys.argv[1:] if argv is None else argv), '--internal-worker', '--run-id', run_id]
            return supervise(command, numbers, args.output, args.budget_seconds, run_id, 'fixture' if args.fixtures else 'bulk' if args.bulk else 'live')
        report = run_batch(numbers, args.output, args.fixtures,
                           args.workers, args.budget_seconds, args.timeout, domains, args.resume, legal_sources, args.bulk, args.max_requests, args.run_id)
    except (OSError, ValueError, csv.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0 if report['states']['failed'] == 0 else 2


