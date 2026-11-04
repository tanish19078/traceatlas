"""Build the static gallery page from the offline, synthetic demo run."""
import json
from pathlib import Path

from traceatlas.view import render


def main():
    profiles_path = Path('runs/demo/profiles.jsonl')
    if not profiles_path.is_file():
        raise SystemExit('Run `python -m examples.demo` before publishing the site.')
    profiles = [
        json.loads(line)
        for line in profiles_path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    Path('docs').mkdir(parents=True, exist_ok=True)
    render(profiles, Path('docs/index.html'))
    print(f'Built docs/index.html from {len(profiles)} synthetic profiles.')


if __name__ == '__main__':
    main()
