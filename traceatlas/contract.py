"""Adapter for the organizer's OUTPUT_CONTRACT.md, separate from native profiles."""
import copy
import json
import math
from datetime import datetime
from pathlib import Path
from .models import STATES, canonical, atomic_write


def _resolve_pointer(value, pointer):
    if pointer in (None, ''):
        return value
    for token in pointer.lstrip('/').split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _claim_excerpt(claim, evidence, body):
    try:
        if evidence['snapshot_path'].endswith('.json') and isinstance(claim.get('json_pointer'), str):
            return canonical(_resolve_pointer(json.loads(body), claim['json_pointer']))[:2048]
        if 'json_ld_block' in claim:
            from .web import Document
            block = Document(body).json_ld[claim['json_ld_block']]
            return canonical(_resolve_pointer(block, claim.get('json_pointer')))[:2048]
        span = claim.get('text_span')
        if isinstance(span, list) and len(span) == 2 and all(type(item) is int for item in span):
            from .web import Document
            text = Document(body).text
            if 0 <= span[0] < span[1] <= len(text):
                return text[span[0]:span[1]][:2048]
        value = claim.get('value')
        if isinstance(value, str) and value in body.decode('utf-8', errors='replace'):
            return value[:2048]
        return canonical(value)[:2048]
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return canonical(claim.get('value'))[:2048]


def adapt(result, root, run_id, started_at, completed_at, resumed=False):
    source_evidence = (
        result['evidence'] + result.get('evidence_history', [])
        + result.get('last_known', {}).get('evidence', [])
    )
    evidence_by_id = {}
    for item in source_evidence:
        existing = evidence_by_id.get(item['id'])
        if existing is None:
            evidence_by_id[item['id']] = copy.deepcopy(item)
            continue
        identity_keys = (
            'content_sha256', 'snapshot_path', 'source_url', 'source_class',
            'organisation_number', 'synthetic',
        )
        if any(existing.get(key) != item.get(key) for key in identity_keys):
            raise ValueError('conflicting evidence identity')
        observations = set(existing.get('retrieval_times', [existing['retrieved_at']]))
        observations.update(item.get('retrieval_times', [item['retrieved_at']]))
        observations = sorted(observations)
        existing['retrieved_at'] = observations[0]
        existing['last_retrieved_at'] = observations[-1]
        existing['retrieval_times'] = observations
    native_evidence = list(evidence_by_id.values())
    bodies = {
        item['id']: (Path(root) / item['snapshot_path']).read_bytes()
        for item in native_evidence
    }
    claims_by_evidence = {}
    historical_claims = [
        change[side] for change in result['refresh']['changes'] for side in ('before', 'after')
        if change[side] is not None
    ] + result.get('last_known', {}).get('claims', [])
    for claim in result['claims'] + historical_claims:
        claims_by_evidence.setdefault(claim['evidence_id'], {})[claim['id']] = claim

    evidence = copy.deepcopy(native_evidence)
    for item in evidence:
        original_class = item['source_class']
        item['native_source_class'] = original_class
        if original_class == 'verified_company_website':
            item['source_class'] = 'company_owned'
        excerpts = [
            _claim_excerpt(claim, item, bodies[item['id']])
            for claim in claims_by_evidence.get(item['id'], {}).values()
        ]
        item['claim_span'] = '\n'.join(dict.fromkeys(excerpts)) if excerpts else ''
    refs = {item['id']: item for item in evidence}
    claims = []
    for native in result['claims']:
        claim = copy.deepcopy(native)
        claim.update(availability='available', evidence_ids=[claim['evidence_id']],
                     confidence=1.0 if refs[claim['evidence_id']]['native_source_class'] == 'official_registry' else 0.9,
                     confidence_basis='deterministic_source_support_policy_not_calibrated_probability')
        if claim['field'] == 'website_identity':
            claim['field'] = 'official_website'
            claim['supporting_identity_passage'] = claim['value']
            claim['value'] = refs[claim['evidence_id']]['source_url']
        claims.append(claim)
    published = {claim['field'] for claim in claims}
    for field, status in result['availability'].items():
        if status['state'] != 'available' and field not in published:
            claims.append({'field': field, 'value': None, 'availability': status['state'],
                           'confidence': 0.0, 'evidence_ids': [], 'reason': status.get('reason', '')})
    operations = copy.deepcopy(result.get('operations', {'requests': 0, 'runtime_ms': 0, 'third_party_cost_usd': 0}))
    if resumed:
        operations = {'requests': 0, 'runtime_ms': 0, 'third_party_cost_usd': 0}
    run = {'run_id': run_id, 'started_at': started_at, 'completed_at': completed_at,
           'terminal_status': 'failed' if result['state'] == 'failed' else 'completed'}
    if resumed:
        run['reused_evidence_as_of'] = result['refresh']['checked_at']
    row = {'organisation_number': result['organisation_number'], 'run': run,
           'state': result['state'], 'legal_identity': result['legal_identity'],
           'claims': claims, 'evidence': evidence, 'changes': result['refresh']['changes'],
           'errors': result['errors'], 'operations': operations,
           'availability': result['availability'], 'summary': result['summary'],
           'source_mode': result['source_mode'], 'refresh': result['refresh']}
    if 'last_known' in result:
        previous = copy.deepcopy(result['last_known'])
        previous['evidence_ids'] = sorted(item['id'] for item in previous.pop('evidence'))
        row['last_known'] = previous
    return row


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(rows, numbers):
    errors = []
    if len(rows) != len(numbers):
        errors.append('input/output count mismatch')
    for index, row in enumerate(rows):
        try:
            require(index < len(numbers) and row['organisation_number'] == numbers[index], 'wrong input order or identity')
            run = row['run']
            require(isinstance(run['run_id'], str) and run['run_id'], 'missing run id')
            stamps = [datetime.fromisoformat(run[key]) for key in ('started_at', 'completed_at')]
            require(all(stamp.tzinfo is not None for stamp in stamps) and stamps[0] <= stamps[1], 'invalid run timestamps')
            require(run['terminal_status'] in ('completed', 'failed'), 'nonterminal result')
            refs = {item['id'] for item in row['evidence']}
            require(len(refs) == len(row['evidence']), 'duplicate evidence ids')
            for claim in row['claims']:
                require(claim['availability'] in STATES, 'invalid claim availability')
                require(isinstance(claim['evidence_ids'], list) and set(claim['evidence_ids']) <= refs, 'dangling evidence reference')
                require(type(claim['confidence']) in (int, float) and math.isfinite(claim['confidence']) and 0 <= claim['confidence'] <= 1, 'invalid confidence')
                if claim['availability'] == 'available':
                    require(claim['evidence_ids'] and claim['value'] is not None, 'available claim lacks support')
                else:
                    require(claim['value'] is None, 'missing value became a fact')
            for key in ('requests', 'runtime_ms', 'third_party_cost_usd'):
                value = row['operations'][key]
                require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'invalid operations metric')
            require(isinstance(row['changes'], list) and isinstance(row['errors'], list), 'invalid result containers')
            for change in row['changes']:
                require(change['kind'] in ('added', 'changed', 'no_longer_reported'), 'invalid change kind')
                for side in ('before', 'after'):
                    claim = change[side]
                    require(claim is None or claim['evidence_id'] in refs, 'change has dangling evidence reference')
            if 'last_known' in row:
                previous = row['last_known']
                require(isinstance(previous['claims'], list)
                        and isinstance(previous['evidence_ids'], list)
                        and set(previous['evidence_ids']) <= refs,
                        'invalid last-known evidence')
                require(all(claim['evidence_id'] in refs for claim in previous['claims']),
                        'last-known claim has dangling evidence reference')
        except (AssertionError, KeyError, TypeError, ValueError, IndexError) as exc:
            errors.append({'row': index, 'error': str(exc)})
    return {'passed': not errors, 'results_checked': len(rows), 'errors': errors}


def export(results, root, numbers, run_id, started_at, completed_at, resumed_indices=()):
    rows = [adapt(row, root, run_id, started_at, completed_at, index in resumed_indices) for index, row in enumerate(results)]
    validation = validate(rows, numbers)
    if not validation['passed']:
        raise ValueError('invalid_contract_export: ' + canonical(validation))
    atomic_write(Path(root) / 'envelopes.jsonl', ''.join(canonical(row) + '\n' for row in rows))
    return validation
