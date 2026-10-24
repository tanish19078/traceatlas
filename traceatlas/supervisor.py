"""Stop a stalled research worker, then finalize every input from checked checkpoints."""
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from .models import STATES, VERSION, atomic_write, canonical, envelope, now
from .checkpoint import output_lock
from .audit import validate_result
from .contract import export
from .view import render


def supervise(command, numbers, output, seconds, run_id, source_mode):
    began = time.monotonic()
    started_at = now()
    reserve = min(10.0, seconds * 0.1)
    process = subprocess.Popen(command)
    stopped = False
    try:
        code = process.wait(timeout=max(0.01, seconds - reserve))
        try:
            prior_report = json.loads((Path(output)/'report.json').read_text())
            if prior_report.get('run_id') == run_id and datetime.fromisoformat(prior_report.get('started_at', '')) >= datetime.fromisoformat(started_at) and prior_report.get('output_count') == len(numbers) and prior_report.get('contract_validation',{}).get('passed') and (Path(output)/'envelopes.jsonl').exists():
                return code
        except (OSError, ValueError):
            pass
    except subprocess.TimeoutExpired:
        stopped = True
        process.kill()
        process.wait()
    # The killed process releases its OS output lock. If another run now owns
    # the directory, fail rather than overwrite that run's output.
    root = Path(output);root.mkdir(parents=True, exist_ok=True)
    with output_lock(root):
        completed = {}
        journal = root / 'completion.jsonl'
        if journal.exists():
            with journal.open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.endswith('\n') or time.monotonic() - began >= seconds:
                        break
                    try:
                        row = json.loads(line);index = row['input_index']
                        if type(index) is not int or not 0 <= index < len(numbers) or row['organisation_number'] != numbers[index] or row['source_mode'] != source_mode:
                            continue
                        if row.get('run',{}).get('run_id') != run_id or datetime.fromisoformat(row['run']['started_at']) < datetime.fromisoformat(started_at):
                            continue
                        validate_result(row, root)
                        completed[index] = row
                    except (ValueError, KeyError, TypeError, OSError, IndexError, AttributeError, RecursionError):
                        continue
        results = []
        for index, number in enumerate(numbers):
            row = completed.get(index)
            if row is None:
                row = envelope(number, 'failed', 'supervisor_time_budget_exhausted' if stopped else 'worker_exited_before_complete_export')
                row.update(input_index=index, source_mode=source_mode)
                row['run'] = {'run_id':run_id, 'started_at':started_at, 'completed_at':now(), 'terminal_status':'failed'}
                row['operations'] = {'requests':0, 'runtime_ms':0, 'third_party_cost_usd':0}
            results.append(row)
        atomic_write(root/'profiles.jsonl',''.join(canonical(row)+'\n' for row in results))
        atomic_write(root/'completion.jsonl',''.join(canonical(row)+'\n' for row in results))
        validation = export(results,root,numbers,run_id,started_at,now())
        report = {'version':VERSION,'run_id':run_id,'started_at':started_at,'completed_at':now(),'mode':source_mode,'input_count':len(numbers),'output_count':len(results),
            'states':{state:sum(row['state']==state for row in results) for state in sorted(STATES)},
            'supervisor_stopped_worker':stopped,'completed_checkpoints':len(completed),
            'duration_seconds':round(time.monotonic()-began,3),'contract_validation':validation,
            'requests':sum(row['operations']['requests'] for row in results),
            'request_count_scope':'lower bound from completed checkpoints; in-flight telemetry unavailable after termination',
            'external_api_cost_usd':0,'official_score':None,
            'limitations':['Worker was stopped before the wall-clock budget to reserve finalization time.',
                           'Filesystem operations and final export are not preemptible.',
                           'Incomplete inputs are explicit failed envelopes, not inferred empty results.']}
        atomic_write(root/'report.json',json.dumps(report,indent=2)+'\n')
        render(results,root/'index.html')
        print(json.dumps(report,indent=2))
        return 2
