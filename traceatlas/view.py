"""Escaped, standalone evidence explorer."""
import html
import json
from pathlib import Path
from .models import BASE, canonical, atomic_write
def render(results, target):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for r in results:
        rows = []
        refs = {e['id']: e for e in r['evidence']}
        for claim in r['claims']:
            e = refs[claim['evidence_id']]
            url = e['source_url']
            safe_url = url.startswith(BASE)
            if e['source_class'] == 'verified_company_website':
                from .web import normalize_url
                try:
                    safe_url = normalize_url(url) == url
                except ValueError:
                    safe_url = False
            source = '<a href="' + esc(url) + '" rel="noreferrer">Source ↗</a>' if safe_url else esc(url)
            locator = ('JSON pointer: ' + esc(claim['json_pointer'])) if 'json_pointer' in claim else ('Text span: ' + esc(claim.get('text_span', 'missing')))
            if 'json_ld_block' in claim:
                locator = 'JSON-LD block ' + esc(claim['json_ld_block']) + ' · Pointer: ' + esc(claim['json_pointer'] or '(root)')
            display_value = esc(canonical(claim['value']))
            if claim['field'] == 'jobs' and isinstance(claim['value'], dict):
                posting = claim['value']
                display_value = '<strong>' + esc(posting.get('title', 'Job posting')) + '</strong><p>Posted ' + esc(posting.get('datePosted', 'unknown')) + '</p><p>Expiry: ' + esc(posting.get('validThrough', 'not reported')) + '</p><details><summary>Original structured record</summary><pre>' + esc(json.dumps(posting, ensure_ascii=False, indent=2)) + '</pre></details>'
            rows.append('<tr><th>' + esc(claim['field'].replace('_', ' ')) + '</th><td>' +
                        display_value + '</td><td><details><summary>Evidence</summary>' +
                        source + '<p>Retrieved ' + esc(e['retrieved_at']) + '</p><p>' +
                        locator + '</p><code>SHA-256 ' + esc(e['id']) + '</code>' +
                        ('<p>SYNTHETIC FIXTURE — not a real company claim</p>' if e['synthetic'] else '') +
                        '</details></td></tr>')
        unknown = ', '.join(k.replace('_',' ') for k,v in r['availability'].items() if v['state'] != 'available')
        gaps = ''.join('<tr><th>' + esc(k.replace('_', ' ')) + '</th><td>' +
            esc(v['state']) + '</td><td>' + esc(v.get('reason', '')) + '</td></tr>'
            for k, v in r['availability'].items() if v['state'] != 'available')
        website = r.get('website_research')
        website_status = ('<p class="muted">Website research: ' + str(website['pages_verified']) +
            ' verified pages · ' + str(website['requests']) + ' requests</p>' +
            ('<p class="muted">Research notes: ' + esc(', '.join(website['errors'])) + '</p>' if website['errors'] else '')) if website else ''
        changes = r['refresh']['changes']
        cards.append('<article><div class="eyebrow">' + esc(r['organisation_number']) + ' · ' + esc(r['state']) +
                     '</div><h2>' + esc(r['legal_identity'].get('name', 'Unresolved company')) + '</h2><p>' +
                     esc(r['summary']) + '</p><div class="scroll"><table><thead><tr><th>Fact</th><th>Value</th><th>Source</th></tr></thead><tbody>' +
                     ''.join(rows) + '</tbody></table></div><p class="muted">Unknown / unresearched: ' + esc(unknown or 'none') +
                     '</p><details><summary>Refresh changes (' + str(len(changes)) + ')</summary><pre>' +
                     esc(json.dumps(changes, ensure_ascii=False, indent=2)) + '</pre></details>' +
                     ('<details><summary>Availability and gaps</summary><div class="scroll"><table><thead><tr><th>Field</th><th>State</th><th>Reason</th></tr></thead><tbody>' + gaps + '</tbody></table></div></details>' if gaps else '') +
                     website_status +
                     ('<details><summary>Last known evidence</summary><pre>' + esc(json.dumps(r['last_known'],ensure_ascii=False,indent=2)) + '</pre></details>' if 'last_known' in r else '') +
                     ('<p>Errors: ' + esc(', '.join(r['errors'])) + '</p>' if r['errors'] else '') + '</article>')
    atomic_write(target, '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TraceAtlas · Evidence explorer</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#172839;font:16px/1.6 system-ui,sans-serif}header{background:#102d3b;color:white;padding:48px max(24px,calc((100vw - 1100px)/2))}header p{color:#bed9df}h1{font-size:42px;letter-spacing:-2px;margin:0}main{max-width:1150px;margin:30px auto;padding:0 24px}article{background:white;border:1px solid #dae3e7;border-radius:14px;padding:26px;margin:24px 0}.eyebrow{color:#176b72;font:600 13px monospace}h2{margin:8px 0;font-size:25px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:12px;text-align:left;border-bottom:1px solid #e4eaee;vertical-align:top}td{min-width:180px;overflow-wrap:anywhere}th{text-transform:capitalize}a{color:#086d82}summary{cursor:pointer;color:#086d82}code{font-size:11px;word-break:break-all}.muted{color:#536772;font-size:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}footer{padding:24px;text-align:center;color:#536772}@media(max-width:600px){header{padding:30px 20px}h1{font-size:34px}main{padding:0 12px}article{padding:16px}}
</style><header><div class="eyebrow" style="color:#92d7d0">COMPANY INTELLIGENCE / EVIDENCE EXPLORER</div><h1>TraceAtlas</h1><p>Every fact has a source. Every unknown stays visible.</p></header><main><p>Registry baseline · ''' + str(len(results)) +
        ' company results · Verified facts and explicit gaps</p>' + ''.join(cards) + '</main><footer>TraceAtlas · No model-generated facts · No official competition score</footer></html>')


