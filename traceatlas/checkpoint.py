"""Exclusive output ownership and evidence-checked batch recovery."""
import json
import os
from contextlib import contextmanager
from pathlib import Path
from .models import VERSION, atomic_write, canonical, digest, now, valid_org


@contextmanager
def output_lock(root):
    """OS locks release on process exit, including crashes; no stale lock removal."""
    stream = (Path(root) / '.run.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            if not stream.read(1):
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError('output_directory_in_use') from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError('output_directory_in_use') from exc
        yield
    finally:
        stream.close()


def prepare(root, numbers, fixture_dir, allowed_domains, resume):
    fixtures = {}
    if fixture_dir:
        for number in sorted(set(numbers)):
            if valid_org(number):
                path = Path(fixture_dir) / (number + '.json')
                fixtures[number] = digest(path.read_bytes()) if path.exists() else None
    expected = {'version': VERSION, 'input_sha256': digest(canonical(numbers).encode()),
        'input_count': len(numbers), 'mode': 'fixture' if fixture_dir else 'live',
        'fixture_sha256': fixtures, 'allowed_domains': sorted(set(allowed_domains or []))}
    manifest = Path(root) / 'run.json'
    journal = Path(root) / 'completion.jsonl'
    if not resume:
        atomic_write(manifest, canonical(dict(expected, started_at=now())) + '\n')
        return {}
    if not manifest.exists() or not journal.exists():
        raise ValueError('resume_checkpoint_missing')
    stored = json.loads(manifest.read_text(encoding='utf-8'))
    if any(stored.get(key) != value for key, value in expected.items()):
        raise ValueError('resume_inputs_or_configuration_changed')
    from .audit import validate_result
    recovered = {}
    lines = journal.read_text(encoding='utf-8').splitlines(keepends=True)
    for offset, line in enumerate(lines):
        # Only an incomplete final write may be discarded. A newline-terminated
        # malformed row is corruption, not permission to skip evidence checks.
        if offset == len(lines)-1 and not line.endswith('\n'):
            break
        try:
            row = json.loads(line)
            index = row['input_index']
            if type(index) is not int or not 0 <= index < len(numbers) or row['organisation_number'] != numbers[index] or row['source_mode'] != expected['mode']:
                raise ValueError('checkpoint_input_mismatch')
            validate_result(row, Path(root))
        except (KeyError, ValueError, TypeError, OSError) as exc:
            raise ValueError('resume_checkpoint_invalid') from exc
        if row['state'] not in ('failed', 'blocked'):
            recovered[index] = row
        else:
            recovered.pop(index, None)
    return recovered
