"""Command-line research interface."""
import argparse
import json
import math
from .core import read_inputs, run_batch
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Text or JSONL organisation numbers')
    parser.add_argument('--output', default='runs/latest')
    parser.add_argument('--fixtures', help='Offline JSON response folder; clearly labelled synthetic')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--budget-seconds', type=float, default=300)
    parser.add_argument('--timeout', type=float, default=12)
    parser.add_argument('--allow-domain', action='append', default=[], help='Reviewed public website hostname; enables opt-in website research (repeatable)')
    parser.add_argument('--legal-sources', help='Reviewed JSON map of company numbers to news/filing URLs; also requires --allow-domain')
    parser.add_argument('--resume', action='store_true', help='Reuse evidence-checked terminal results from the same batch; retry failed/blocked inputs')
    args = parser.parse_args()
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
        report = run_batch(numbers, args.output, args.fixtures,
                           args.workers, args.budget_seconds, args.timeout, domains, args.resume, legal_sources)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0 if report['states']['failed'] == 0 else 2


