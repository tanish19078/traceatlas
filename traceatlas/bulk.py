"""Stream evaluator-supplied Brreg CSV/JSONL without a live fallback."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from .models import canonical, digest

BULK_URL = 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv'
FORMAT = 'traceatlas_bulk_v1'
csv.field_size_limit(2_000_000)


def decode_record(record, encoding):
    if encoding == 'jsonl':
        return record
    if encoding != 'csv':
        raise ValueError('unknown_bulk_encoding')
    data = {}
    for key, value in record.items():
        if value in ('', None):
            continue
        key = 'registreringsdatoEnhetsregisteret' if key == 'registreringsdatoenhetsregisteret' else key
        if key in ('konkurs', 'underAvvikling', 'harRegistrertAntallAnsatte'):
            if value.casefold() not in ('true', 'false'):
                raise ValueError('invalid_bulk_boolean')
            value = value.casefold() == 'true'
        elif key == 'antallAnsatte':
            if not value.isascii() or not value.isdigit():
                raise ValueError('invalid_bulk_employee_count')
            value = int(value)
        target = data
        parts = key.split('.')
        for part in parts[:-1]:
            target = target.setdefault(part, {})
            if not isinstance(target, dict):
                raise ValueError('conflicting_bulk_columns')
        if parts[-1] in target:
            raise ValueError('conflicting_bulk_columns')
        target[parts[-1]] = value
    return data


def decode_snapshot(value):
    if value.get('_format') != FORMAT:
        return value
    if set(value) != {'_format', 'file_sha256', 'encoding', 'record'}:
        raise ValueError('invalid_bulk_snapshot')
    key = value['file_sha256']
    if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('invalid_bulk_file_hash')
    if not isinstance(value['record'], dict):
        raise ValueError('invalid_bulk_record')
    return decode_record(value['record'], value['encoding'])


class BulkRegistry:
    def __init__(self, path, numbers):
        self.path = Path(path)
        self.rows = {}
        wanted = set(numbers)
        with self.path.open('rb') as stream:
            self.sha256 = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else digest(stream.read())
        with self.path.open('rb') as raw:
            magic = raw.read(2); raw.seek(0)
            binary = gzip.GzipFile(fileobj=raw) if magic == b'\x1f\x8b' else raw
            with io.TextIOWrapper(binary, encoding='utf-8-sig', newline='') as stream:
                sample = stream.readline(); stream.seek(0)
                if sample.lstrip().startswith('{'):
                    encoding = 'jsonl'
                    def records():
                        for line in stream:
                            if len(line) > 2_000_000:
                                raise ValueError('bulk_record_size_limit')
                            if line.strip():
                                value = json.loads(line)
                                if not isinstance(value, dict):
                                    raise ValueError('invalid_bulk_record')
                                yield value
                    rows = records()
                else:
                    encoding = 'csv'
                    delimiter = ';' if sample.count(';') > sample.count(',') else ','
                    reader = csv.DictReader(stream, delimiter=delimiter)
                    if not reader.fieldnames or 'organisasjonsnummer' not in reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                        raise ValueError('invalid_bulk_header')
                    rows = reader
                for record in rows:
                    number = record.get('organisasjonsnummer')
                    if number not in wanted:
                        continue
                    if number in self.rows:
                        raise ValueError('duplicate_bulk_company')
                    if None in record:
                        raise ValueError('invalid_bulk_columns')
                    snapshot = {'_format': FORMAT, 'file_sha256': self.sha256,
                                'encoding': encoding, 'record': record}
                    body = canonical(snapshot).encode()
                    if len(body) > 2_000_000:
                        raise ValueError('bulk_record_size_limit')
                    self.rows[number] = body

    def body(self, number):
        if number not in self.rows:
            raise FileNotFoundError('company_absent_in_frozen_registry')
        return self.rows[number]
