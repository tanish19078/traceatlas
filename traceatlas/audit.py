"""Audit TraceAtlas exports against immutable source snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime
from .models import BASE, STATES, FIELDS, canonical, digest, valid_org


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_result(result, root, historical=False):
    root = Path(root)
    checked = 0
    require(isinstance(result, dict), 'result must be an object')
    require(result['state'] in STATES, 'invalid availability state')
    require(isinstance(result['organisation_number'], str), 'invalid organisation number type')
    require(isinstance(result['claims'], list) and isinstance(result['evidence'], list), 'invalid evidence containers')
    evidence = {item['id']: item for item in result['evidence']}
    require(len(evidence) == len(result['evidence']), 'duplicate evidence ids')
    ids = [claim['id'] for claim in result['claims']]
    require(len(ids) == len(set(ids)), 'duplicate claim ids')
    if not historical and result['state'] != 'available':
        require(not result['claims'], 'non-available result has current claims')
    if not historical and result['state'] == 'available':
        require(result['legal_identity']['organisation_number'] == result['organisation_number'], 'identity mismatch')
        require(result['claims'], 'available result without claims')
        require(valid_org(result['organisation_number']), 'invalid available organisation number')
        require(any(claim['field'] == 'legal_name' and evidence[claim['evidence_id']]['source_class'] == 'official_registry' for claim in result['claims']), 'official identity anchor missing')
    for claim in result['claims']:
        item = evidence[claim['evidence_id']]
        key = item['content_sha256']
        require(isinstance(key, str) and len(key) == 64 and all(c in '0123456789abcdef' for c in key), 'invalid snapshot hash')
        require(item['id'] == key, 'evidence id/hash mismatch')
        source_class = item['source_class']
        require(source_class in ('official_registry', 'verified_company_website'), 'unknown source class')
        suffix = '.json' if source_class == 'official_registry' else '.html'
        require(item['snapshot_path'] == 'snapshots/' + key + suffix, 'wrong snapshot path')
        path = root / 'snapshots' / (key + suffix)
        require(not path.is_symlink(), 'snapshot symlink rejected')
        require(path.stat().st_size <= (2_000_000 if suffix == '.json' else 1_000_000), 'snapshot size limit')
        body = path.read_bytes()
        require(hashlib.sha256(body).hexdigest() == key, 'snapshot hash mismatch')
        stamp = datetime.fromisoformat(item['retrieved_at'])
        require(stamp.tzinfo is not None, 'retrieval timezone missing')
        if source_class == 'official_registry':
            data = json.loads(body)
            require(data['organisasjonsnummer'] == result['organisation_number'], 'wrong company')
            if not historical:
                require(data['navn'] == result['legal_identity']['name'], 'wrong legal name')
            require(item['source_url'] == BASE + result['organisation_number'], 'wrong source URL')
            fields = dict(FIELDS, registered_employees='antallAnsatte')
            require(claim['field'] in fields, 'unknown registry field')
            pointer = claim['json_pointer']
            require(pointer == '/' + fields[claim['field']], 'wrong field pointer')
            if claim['field'] == 'registered_employees':
                require(data.get('harRegistrertAntallAnsatte') is True, 'employee count not confirmed')
            value = data[fields[claim['field']]]
            require(claim['extraction_method'] == 'registry_json_pointer', 'wrong registry extraction method')
            require(claim['id'] == digest((result['organisation_number'] + ':' + claim['field'] + ':' + canonical(value)).encode()), 'wrong registry claim id')
            if claim['field'] == 'registered_employees':
                require(type(value) is int and value >= 0, 'invalid employee count')
        else:
            from .web import Document, normalize_url, verify_identity
            require(normalize_url(item['source_url']) == item['source_url'], 'unsafe website URL')
            document = Document(body)
            legal_name = item.get('legal_name', result['legal_identity'].get('name', '')) if historical else result['legal_identity']['name']
            proof = verify_identity(document, result['organisation_number'], legal_name)
            require(proof is not None and proof == item['identity_span'], 'website entity proof missing')
            if claim['extraction_method'] == 'json_ld_job_v1':
                from .jobs import extract_jobs
                supported = extract_jobs(document, result['organisation_number'], legal_name, item['source_url'], key, item['retrieved_at'])
                require(claim in supported, 'unsupported structured job posting')
                value = claim['value']
            else:
                require(claim['field'] in ('website_identity', 'company_page'), 'unknown website field')
                require(claim['subject'] == claim['field'] + ':' + item['source_url'], 'wrong website subject')
                require(item['extractor_version'] == claim['extraction_method'] == 'visible_text_v1', 'unknown website extractor')
                span = claim['text_span']
                require(isinstance(span, list) and len(span) == 2 and all(type(x) is int for x in span), 'invalid text span')
                start, end = span
                require(0 <= start < end <= len(document.text), 'text span out of bounds')
                require(start <= proof[0] and end >= proof[1], 'identity passage omits proof')
                value = document.text[start:end]
                require(claim['id'] == digest((result['organisation_number'] + claim['field'] + item['source_url'] + value).encode()), 'wrong website claim id')
        require(type(value) is type(claim['value']) and value == claim['value'], 'unsupported claim value')
        checked += 1
    if not historical and 'last_known' in result:
        previous = result['last_known']
        require(isinstance(previous, dict), 'invalid historical evidence')
        archived = {'organisation_number': result['organisation_number'], 'state': 'available',
                    'legal_identity': previous.get('legal_identity', result['legal_identity']),
                    'claims': previous['claims'], 'evidence': previous['evidence']}
        checked += validate_result(archived, root, historical=True)
    return checked


def verify(root, expected_count=None, expected_numbers=None):
    root = Path(root)
    errors, checked, rows = [], 0, []
    try:
        lines = (root / 'profiles.jsonl').read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError) as exc:
        return {'claims_checked': 0, 'results_checked': 0, 'errors': [
            {'row': None, 'error': type(exc).__name__}], 'passed': False}
    require_count = expected_count
    if expected_numbers is not None:
        if expected_count is not None and expected_count != len(expected_numbers):
            errors.append({'row': None, 'error': 'conflicting expected input counts'})
        require_count = len(expected_numbers)
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
            checked += validate_result(result, root)
            if 'input_index' in result:
                require(type(result['input_index']) is int and result['input_index'] == index - 1, 'wrong input order or duplicate index')
            if expected_numbers is not None:
                require(index <= len(expected_numbers) and result['organisation_number'] == expected_numbers[index - 1], 'input/output identity mismatch')
            rows.append(result)
        except (KeyError, ValueError, TypeError, OSError, IndexError, AttributeError, RecursionError) as exc:
            errors.append({'row': index, 'error': str(exc)})
    return {'claims_checked': checked, 'results_checked': len(rows), 'errors': errors,
            'passed': not errors,
            'scope': 'Stored claim support and export completeness; not external recall or source truth.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--expected-count', type=int)
    parser.add_argument('--input', help='Independent original input file; verify exact identities and order')
    args = parser.parse_args()
    if args.expected_count is not None and args.expected_count < 0:
        parser.error('expected-count must be nonnegative')
    from .core import read_inputs
    try:
        numbers = read_inputs(args.input) if args.input else None
    except (OSError, UnicodeError):
        parser.error('input file must be readable UTF-8 text')
    result = verify(args.directory, args.expected_count, numbers)
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
