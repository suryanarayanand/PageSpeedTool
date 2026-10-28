"""Manual smoke check: python check_ui.py (requires the local server)."""
from pathlib import Path
import sys
import json
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1360, 'height': 1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:5055/')
    page.locator('#history .report').first.wait_for()
    assert not page.get_by_label('PageSpeed API key', exact=True).is_visible()
    assert page.locator('#estimate').inner_text() == '3 articles · 6 checks'
    page.get_by_label('Sportstar', exact=True).uncheck()
    assert page.locator('#estimate').inner_text() == '2 articles · 4 checks'
    page.get_by_label('Sportstar', exact=True).check()
    page.get_by_text('Advanced settings', exact=True).click()
    page.locator('#method').select_option('api')
    assert page.get_by_label('PageSpeed API key', exact=True).is_visible()
    page.locator('#method').select_option('browser')
    page.get_by_text('Advanced settings', exact=True).click()
    page.screenshot(path=str(ROOT / 'reports' / 'ui_desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(ROOT / 'reports' / 'ui_mobile.png'), full_page=True)
    assert not errors, errors
    print('UI passed: defaults, selections, advanced settings, history, mobile layout; no JavaScript errors.')
    runs = json.load(urllib.request.urlopen('http://127.0.0.1:5055/runs'))
    ready = next((r for r in runs if r.get('has_reports') and r['status'] in {'Complete', 'Partial'}), None)
    if ready:
        page.set_viewport_size({'width': 1360, 'height': 1000})
        base = 'http://127.0.0.1:5055/reports/' + ready['id'] + '/'
        page.goto(base + 'report.html')
        assert page.locator('.audit').count() == len(ready['results'])
        page.screenshot(path=str(ROOT / 'reports' / 'report_preview.png'))
        with urllib.request.urlopen(base + 'report.xlsx') as response:
            assert response.status == 200
            assert response.read(2) == b'PK'
        print('HTML report renders all device results; Excel download returns a valid workbook archive.')
    browser.close()
