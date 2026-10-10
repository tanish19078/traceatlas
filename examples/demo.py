"""Create an explicitly synthetic, offline TraceAtlas demonstration."""
import json
from pathlib import Path
import traceatlas

root = Path('runs/demo')
fixtures = root / 'fixtures'
fixtures.mkdir(parents=True, exist_ok=True)
number = '923609016'
# This valid number is only a fixture key. No values here describe a real entity.
body = {'organisasjonsnummer': number, 'navn': 'SYNTHETIC — Northlight Example AS',
        'organisasjonsform': {'kode': 'AS', 'beskrivelse': 'Synthetic example'},
        'forretningsadresse': {'adresse': ['Fictional demonstration address']},
        'aktivitet': ['Synthetic company used only to demonstrate evidence inspection.'],
        'harRegistrertAntallAnsatte': True, 'antallAnsatte': 12,
        'hjemmeside': 'example.invalid', 'konkurs': False}
(fixtures / (number + '.json')).write_text(json.dumps(body,ensure_ascii=False))
print(json.dumps(traceatlas.run_batch([number], root, fixture_dir=fixtures), indent=2))
print('Open runs/demo/index.html. All example facts are synthetic.')
