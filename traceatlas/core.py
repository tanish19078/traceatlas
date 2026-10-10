"""Batch orchestration and input parsing."""
from __future__ import annotations
import concurrent.futures
import json
import math
import os
import time
from pathlib import Path
from .models import BASE, VERSION, STATES, canonical, envelope, atomic_write, digest, valid_org
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


def run_batch(numbers, output, fixture_dir=None, workers=4, budget=300, timeout=12, allowed_domains=None, resume=False):
    numbers = list(numbers)
    if not numbers or any(not isinstance(number, str) for number in numbers):
        raise ValueError('inputs must be a nonempty sequence of strings')
    if type(workers) is not int or not 1 <= workers <= 8 or not math.isfinite(budget) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('invalid batch configuration')
    started = time.monotonic()
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    from .checkpoint import output_lock
    with output_lock(root):
        return _run_batch(numbers, root, fixture_dir, workers, budget, timeout, allowed_domains, resume, started)


def _run_batch(numbers, root, fixture_dir, workers, budget, timeout, allowed_domains, resume, started):
    from .checkpoint import prepare
    recovered = prepare(root, numbers, fixture_dir, allowed_domains, resume)
    store = Store(root)
    def task(number):
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            return envelope(number, 'failed', 'time_budget_exhausted'), None
        result, body = research(number, fixture_dir, min(timeout, max(0.1, remaining)))
        if allowed_domains and not fixture_dir and result['state'] == 'available':
            from .web import enrich
            pages = enrich(result, allowed_domains, min(started + budget, time.monotonic() + timeout))
            body = [(body, '.json')] + pages
        return result, body
    results = [recovered.get(index) for index in range(len(numbers))]
    try:
        # Completion journal is independent of SQLite. A worker/store error must
        # not prevent a terminal envelope for every other input.
        atomic_write(root / 'completion.jsonl', ''.join(canonical(recovered[index]) + '\n' for index in sorted(recovered)))
        with (root / 'completion.jsonl').open('a', encoding='utf-8') as journal:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                pending = {pool.submit(task, number): index for index, number in enumerate(numbers) if index not in recovered}
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
                    result['input_index'] = index
                    result['source_mode'] = 'fixture' if fixture_dir else 'live'
                    results[index] = result
                    journal.write(canonical(result) + '\n')
                    journal.flush()
                    os.fsync(journal.fileno())
        atomic_write(root / 'profiles.jsonl', ''.join(canonical(r) + '\n' for r in results))
        counts = {state: sum(r['state'] == state for r in results) for state in sorted(STATES)}
        report = {'version': VERSION, 'mode': 'fixture' if fixture_dir else 'live',
                  'input_count': len(numbers), 'output_count': len(results),
                  'resumed_count': len(recovered),
                  'states': counts, 'duration_seconds': round(time.monotonic()-started, 3),
                  'claim_count': sum(len(r['claims']) for r in results),
                  'website_requests': sum(r.get('website_research', {}).get('requests', 0) for r in results),
                  'website_pages_verified': sum(r.get('website_research', {}).get('pages_verified', 0) for r in results),
                  'external_coverage_measured': False, 'official_score': None,
                  'external_api_cost_usd': 0, 'models': [],
                  'limitations': ['Website research is opt-in and limited to reviewed registry candidate domains.',
                                  'Leadership, financial and news extraction not implemented; jobs require attributed JSON-LD.',
                                  'Soft deadline; network and thread cleanup may exceed the budget.',
                                  'Not an official evaluation or qualification result.']}
        atomic_write(root / 'report.json', json.dumps(report, indent=2) + '\n')
        render(results, root / 'index.html')
        return report
    finally:
        store.close()


