"""Audit TraceAtlas exports against immutable source snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
from traceatlas import BASE, STATES, FIELDS


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root, expected_count=None):
    root = Path(root)
    errors, checked, rows = [], 0, []
    try:
        lines = (root / 'profiles.jsonl').read_text(encoding='utf-8').splitlines()
    except OSError as exc:
        return {'claims_checked': 0, 'results_checked': 0, 'errors': [
            {'row': None, 'error': type(exc).__name__}], 'passed': False}
    require_count = expected_count
    report_path = root / 'report.json'
    if require_count is None and report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
            require_count = report['input_count']
            require(type(require_count) is int and require_count >= 0, 'invalid input count')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({'row': None, 'error': str(exc)})
    if not lines:
        errors.append({'row': None, 'error': 'empty export'})
    if require_count is not None and len(lines) != require_count:
        errors.append({'row': None, 'error': 'input/output count mismatch'})
    for index, line in enumerate(lines, 1):
        try:
            result = json.loads(line)
            require(isinstance(result, dict), 'result must be an object')
            require(result['state'] in STATES, 'invalid availability state')
            require(isinstance(result['organisation_number'], str), 'invalid organisation number type')
            require(isinstance(result['claims'], list) and isinstance(result['evidence'], list), 'invalid evidence containers')
            evidence = {item['id']: item for item in result['evidence']}
            require(len(evidence) == len(result['evidence']), 'duplicate evidence ids')
            ids = [claim['id'] for claim in result['claims']]
            require(len(ids) == len(set(ids)), 'duplicate claim ids')
            if result['state'] != 'available':
                require(not result['claims'], 'non-available result has current claims')
            if result['state'] == 'available':
                require(result['legal_identity']['organisation_number'] == result['organisation_number'], 'identity mismatch')
                require(result['claims'], 'available result without claims')
            for claim in result['claims']:
                item = evidence[claim['evidence_id']]
                key = item['content_sha256']
                require(isinstance(key, str) and len(key) == 64 and all(c in '0123456789abcdef' for c in key), 'invalid snapshot hash')
                require(item['id'] == key, 'evidence id/hash mismatch')
                source_class = item['source_class']
                require(source_class in ('official_registry', 'verified_company_website'), 'unknown source class')
                suffix = '.json' if source_class == 'official_registry' else '.html'
                require(item['snapshot_path'] == 'snapshots/' + key + suffix, 'wrong snapshot path')
                body = (root / 'snapshots' / (key + suffix)).read_bytes()
                require(hashlib.sha256(body).hexdigest() == key, 'snapshot hash mismatch')
                require(item['retrieved_at'], 'missing retrieval date')
                if source_class == 'official_registry':
                    data = json.loads(body)
                    require(data['organisasjonsnummer'] == result['organisation_number'], 'wrong company')
                    require(data['navn'] == result['legal_identity']['name'], 'wrong legal name')
                    require(item['source_url'] == BASE + result['organisation_number'], 'wrong source URL')
                    fields = dict(FIELDS, registered_employees='antallAnsatte')
                    require(claim['field'] in fields, 'unknown registry field')
                    pointer = claim['json_pointer']
                    require(pointer == '/' + fields[claim['field']], 'wrong field pointer')
                    if claim['field'] == 'registered_employees':
                        require(data.get('harRegistrertAntallAnsatte') is True, 'employee count not confirmed')
                    value = data[fields[claim['field']]]
                else:
                    from web_research import Document, normalize_url, verify_identity
                    require(normalize_url(item['source_url']) == item['source_url'], 'unsafe website URL')
                    require(claim['field'] in ('website_identity', 'company_page'), 'unknown website field')
                    require(claim['subject'] == claim['field'] + ':' + item['source_url'], 'wrong website subject')
                    require(item['extractor_version'] == claim['extraction_method'] == 'visible_text_v1', 'unknown website extractor')
                    document = Document(body)
                    proof = verify_identity(document, result['organisation_number'], result['legal_identity']['name'])
                    require(proof is not None and proof == item['identity_span'], 'website entity proof missing')
                    span = claim['text_span']
                    require(isinstance(span, list) and len(span) == 2 and all(type(x) is int for x in span), 'invalid text span')
                    start, end = span
                    require(0 <= start < end <= len(document.text), 'text span out of bounds')
                    require(start <= proof[0] and end >= proof[1], 'identity passage omits proof')
                    value = document.text[start:end]
                require(type(value) is type(claim['value']) and value == claim['value'], 'unsupported claim value')
                checked += 1
            rows.append(result)
        except (KeyError, ValueError, TypeError, OSError, IndexError, AttributeError) as exc:
            errors.append({'row': index, 'error': str(exc)})
    return {'claims_checked': checked, 'results_checked': len(rows), 'errors': errors,
            'passed': not errors,
            'scope': 'Stored claim support and export completeness; not external recall or source truth.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--expected-count', type=int)
    args = parser.parse_args()
    if args.expected_count is not None and args.expected_count < 0:
        parser.error('expected-count must be nonnegative')
    result = verify(args.directory, args.expected_count)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
