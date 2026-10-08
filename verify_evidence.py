"""Audit TraceAtlas exports against immutable source snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
from traceatlas import BASE, STATES


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
                body = (root / 'snapshots' / (key + '.json')).read_bytes()
                require(hashlib.sha256(body).hexdigest() == key, 'snapshot hash mismatch')
                data = json.loads(body)
                require(data['organisasjonsnummer'] == result['organisation_number'], 'wrong company')
                require(item['source_url'] == BASE + result['organisation_number'], 'wrong source URL')
                require(item['retrieved_at'], 'missing retrieval date')
                pointer = claim['json_pointer']
                require(isinstance(pointer, str) and pointer.startswith('/'), 'invalid pointer')
                value = data
                for segment in pointer[1:].split('/'):
                    segment = segment.replace('~1', '/').replace('~0', '~')
                    value = value[int(segment)] if isinstance(value, list) else value[segment]
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
