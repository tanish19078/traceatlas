"""Independently audit a TraceAtlas export against saved source snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
from traceatlas import BASE, STATES


def verify(root):
    root = Path(root)
    errors, checked = [], 0
    for index, line in enumerate((root/'profiles.jsonl').read_text().splitlines(), 1):
        try:
            result = json.loads(line)
            assert result['state'] in STATES, 'invalid availability state'
            evidence = {item['id']: item for item in result['evidence']}
            for claim in result['claims']:
                item = evidence[claim['evidence_id']]
                key = item['content_sha256']
                assert len(key) == 64 and all(c in '0123456789abcdef' for c in key), 'invalid snapshot hash'
                assert item['id'] == key, 'evidence id/hash mismatch'
                body = (root/'snapshots'/(key+'.json')).read_bytes()
                assert hashlib.sha256(body).hexdigest() == key, 'snapshot hash mismatch'
                data = json.loads(body)
                assert data['organisasjonsnummer'] == result['organisation_number'], 'wrong company'
                assert item['source_url'] == BASE + result['organisation_number'], 'wrong source URL'
                assert item['retrieved_at'], 'missing retrieval date'
                pointer = claim['json_pointer']
                assert pointer.startswith('/'), 'invalid pointer'
                value = data
                for segment in pointer[1:].split('/'):
                    segment = segment.replace('~1','/').replace('~0','~')
                    value = value[int(segment)] if isinstance(value,list) else value[segment]
                assert type(value) is type(claim['value']) and value == claim['value'], 'unsupported claim value'
                checked += 1
        except (AssertionError, KeyError, ValueError, TypeError, OSError, IndexError) as exc:
            errors.append({'row': index, 'error': str(exc)})
    return {'claims_checked': checked, 'errors': errors, 'passed': not errors,
            'scope': 'Saved registry claim support only; not external recall or source truth.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    result = verify(parser.parse_args().directory)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
