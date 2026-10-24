"""Batch orchestration and input parsing."""
from __future__ import annotations
import concurrent.futures
import json
import math
import os
import time
import uuid
from pathlib import Path
from .models import BASE, VERSION, STATES, canonical, envelope, atomic_write, digest, valid_org, now
from .registry import research, NoRedirect
from .store import Store
from .view import render
def read_inputs(path):
    numbers = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        raw = line.strip()
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                value = value.get('organisation_number', value.get('organisasjonsnummer', ''))
            raw = str(value) if value is not None else ''
        except json.JSONDecodeError:
            pass
        numbers.append(raw)
    return numbers


def run_batch(numbers, output, fixture_dir=None, workers=4, budget=300, timeout=12, allowed_domains=None, resume=False, legal_sources=None, bulk_path=None, max_requests=None, run_id=None):
    numbers = list(numbers)
    if not numbers or any(not isinstance(number, str) for number in numbers):
        raise ValueError('inputs must be a nonempty sequence of strings')
    if type(workers) is not int or not 1 <= workers <= 8 or not math.isfinite(budget) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('invalid batch configuration')
    if bulk_path and fixture_dir:
        raise ValueError('bulk and fixtures are mutually exclusive')
    if legal_sources and fixture_dir:
        raise ValueError('fixture mode never requests legal sources')
    if run_id is not None and (not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 128):
        raise ValueError('run_id must be a nonempty string up to 128 characters')
    run_id = run_id or 'traceatlas-' + uuid.uuid4().hex[:12]
    ceiling = 20 * len(numbers)
    if max_requests is not None and (type(max_requests) is not int or not 0 <= max_requests <= ceiling):
        raise ValueError('max_requests must be between 0 and 20 per input company')
    started = time.monotonic()
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    from .bulk import BulkRegistry
    bulk = BulkRegistry(bulk_path, numbers) if bulk_path else None
    from .checkpoint import output_lock
    with output_lock(root):
        return _run_batch(numbers, root, fixture_dir, workers, budget, timeout, allowed_domains, resume, started, legal_sources, bulk, ceiling if max_requests is None else max_requests, run_id)


def _run_batch(numbers, root, fixture_dir, workers, budget, timeout, allowed_domains, resume, started, legal_sources, bulk, max_requests, run_id):
    from .checkpoint import prepare
    recovered = prepare(root, numbers, fixture_dir, allowed_domains, resume, legal_sources, bulk.sha256 if bulk is not None else None)
    from .network import RequestBudget, request_scope
    request_budget = RequestBudget(max_requests, started + budget)
    run_started_at = now()
    store = Store(root)
    def task(number):
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            return envelope(number, 'failed', 'time_budget_exhausted'), None
        arguments = (number, fixture_dir, min(timeout, max(0.1, remaining)))
        result, body = research(*arguments, bulk=bulk) if bulk is not None else research(*arguments)
        if allowed_domains and not fixture_dir and result['state'] == 'available':
            from .web import enrich
            pages = enrich(result, allowed_domains, min(started + budget, time.monotonic() + timeout))
            body = [(body, '.json')] + pages
        if legal_sources and result['state'] == 'available':
            from .legal import enrich_legal
            pages = enrich_legal(result, legal_sources.get(number, []), allowed_domains or [], min(started + budget, time.monotonic() + timeout))
            body = (body if isinstance(body, list) else [(body, '.json')]) + pages
        return result, body
    def measured_task(number, index):
        began = time.monotonic()
        began_at = now()
        with request_scope(request_budget, index):
            try:
                result, body = task(number)
            except Exception as exc:
                result, body = envelope(number, 'failed', 'worker_' + type(exc).__name__), None
        result['run'] = {'run_id': run_id, 'started_at': began_at, 'completed_at': now(),
                         'terminal_status': 'failed' if result['state'] == 'failed' else 'completed'}
        result['operations'] = {'requests': request_budget.by_input.get(index, 0),
                                'runtime_ms': round((time.monotonic() - began) * 1000, 3),
                                'third_party_cost_usd': 0}
        return result, body
    results = [recovered.get(index) for index in range(len(numbers))]
    try:
        # Completion journal is independent of SQLite. A worker/store error must
        # not prevent a terminal envelope for every other input.
        atomic_write(root / 'completion.jsonl', ''.join(canonical(recovered[index]) + '\n' for index in sorted(recovered)))
        with (root / 'completion.jsonl').open('a', encoding='utf-8') as journal:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                pending = {pool.submit(measured_task, number, index): index for index, number in enumerate(numbers) if index not in recovered}
                for future in concurrent.futures.as_completed(pending):
                    index = pending[future]
                    try:
                        result, body = future.result()
                    except Exception as exc:
                        result, body = envelope(numbers[index], 'failed', 'worker_' + type(exc).__name__), None
                    try:
                        result = store.save(result, body)
                    except Exception as exc:
                        result = envelope(numbers[index], 'failed', 'storage_' + type(exc).__name__)
                    if 'run' not in result:
                        result['run'] = {'run_id': run_id, 'started_at': run_started_at, 'completed_at': now(), 'terminal_status': 'failed'}
                        result['operations'] = {'requests': request_budget.by_input.get(index, 0), 'runtime_ms': 0, 'third_party_cost_usd': 0}
                    result['input_index'] = index
                    result['source_mode'] = 'fixture' if fixture_dir else 'bulk' if bulk is not None else 'live'
                    results[index] = result
                    journal.write(canonical(result) + '\n')
                    journal.flush()
                    os.fsync(journal.fileno())
        atomic_write(root / 'profiles.jsonl', ''.join(canonical(r) + '\n' for r in results))
        counts = {state: sum(r['state'] == state for r in results) for state in sorted(STATES)}
        completed_at = now()
        from .contract import export
        validation = export(results, root, numbers, run_id, run_started_at, completed_at, recovered)
        timings = sorted(r['operations']['runtime_ms'] for i, r in enumerate(results) if i not in recovered)
        report = {'run_id': run_id, 'started_at': run_started_at, 'completed_at': completed_at,
                  'contract_validation': validation,
                  'p50_ms': timings[math.ceil(len(timings)*0.5)-1] if timings else None,
                  'p95_ms': timings[math.ceil(len(timings)*0.95)-1] if timings else None,
                  'version': VERSION, 'mode': 'fixture' if fixture_dir else 'bulk' if bulk is not None else 'live',
                  'input_count': len(numbers), 'output_count': len(results),
                  'resumed_count': len(recovered),
                  'requests': request_budget.used, 'request_limit': max_requests,
                  'bulk_file_sha256': bulk.sha256 if bulk is not None else None,
                  'states': counts, 'duration_seconds': round(time.monotonic()-started, 3),
                  'claim_count': sum(len(r['claims']) for r in results),
                  'website_requests': sum(r.get('website_research', {}).get('requests', 0) for i, r in enumerate(results) if i not in recovered),
                  'legal_requests': sum(r.get('legal_research', {}).get('requests', 0) for i, r in enumerate(results) if i not in recovered),
                  'legal_reports': sum(r.get('legal_research', {}).get('reports_found', 0) for r in results),
                  'website_pages_verified': sum(r.get('website_research', {}).get('pages_verified', 0) for r in results),
                  'external_coverage_measured': False, 'official_score': None,
                  'external_api_cost_usd': 0, 'models': [],
                  'limitations': ['Website and legal-source research is opt-in on reviewed allowlisted domains.',
                                  'Leadership and financial extraction not implemented; jobs/news require individual attributed records and legal sources are reviewed URLs.',
                                  'Direct API calls use a soft deadline; the supervised CLI can stop stalled research workers.',
                                  'Not an official evaluation or qualification result.']}
        atomic_write(root / 'report.json', json.dumps(report, indent=2) + '\n')
        render(results, root / 'index.html')
        return report
    finally:
        store.close()


