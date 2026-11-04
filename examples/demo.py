"""Create an explicitly synthetic, offline TraceAtlas demonstration."""
import json
from pathlib import Path

import traceatlas


COMPANIES = (
    {
        'number': '900000006',
        'name': 'SYNTHETIC — Northlight Materials AS',
        'activity': 'Manufacture of energy-efficient building materials.',
        'industry': 'Manufacture of other articles of concrete, plaster and cement',
        'employees': 12,
        'address': 'Fictional Harbour Road 12',
        'town': 'BERGEN',
    },
    {
        'number': '900000014',
        'name': 'SYNTHETIC — Fjord Workshop AS',
        'activity': 'Repair of industrial machinery and equipment.',
        'industry': 'Repair of machinery',
        'employees': 5,
        'address': 'Fictional Foundry Lane 4',
        'town': 'TRONDHEIM',
    },
    {
        'number': '900000022',
        'name': 'SYNTHETIC — Brightpath Logistics AS',
        'activity': 'Local freight transport and storage services.',
        'industry': 'Freight transport by road',
        'employees': 34,
        'address': 'Fictional North Quay 8',
        'town': 'TROMSØ',
    },
)


def main():
    root = Path('runs/demo')
    fixtures = root / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    numbers = []
    for company in COMPANIES:
        number = company['number']
        numbers.append(number)
        body = {
            'organisasjonsnummer': number,
            'navn': company['name'],
            'organisasjonsform': {'kode': 'AS', 'beskrivelse': 'Synthetic example'},
            'forretningsadresse': {
                'adresse': [company['address']],
                'poststed': company['town'],
            },
            'naeringskode1': {
                'kode': '00.000',
                'beskrivelse': company['industry'],
            },
            'aktivitet': [company['activity']],
            'harRegistrertAntallAnsatte': True,
            'antallAnsatte': company['employees'],
            'hjemmeside': 'example.invalid',
            'konkurs': False,
        }
        (fixtures / (number + '.json')).write_text(
            json.dumps(body, ensure_ascii=False), encoding='utf-8'
        )
    report = traceatlas.run_batch(numbers, root, fixture_dir=fixtures)
    print(json.dumps(report, indent=2))
    print('Open runs/demo/index.html. All example facts are synthetic.')


if __name__ == '__main__':
    main()
