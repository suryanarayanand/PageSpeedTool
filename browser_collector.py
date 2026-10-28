"""Collect visible measurements from the public PageSpeed Insights website."""
from pathlib import Path
import re
import sys
import urllib.parse

from engine import FetchError, METRICS, extract_psi, now, save_json

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))


def visible_number(text, label, before=False, unit=None):
    text = text.replace('\xa0', ' ').replace('\u202f', ' ')
    numeric = r'([\d,]+(?:\.\d+)?)'
    pattern = numeric + r'\s*\n' + re.escape(label) + r'(?:\n|$)' if before else re.escape(label) + r'\s*\n' + numeric + r'\s*(ms|s)?(?:\n|$)'
    match = re.search(pattern, text)
    if not match:
        return None
    value = float(match.group(1).replace(',', ''))
    displayed_unit = None if before else match.group(2)
    if unit == 's' and displayed_unit == 'ms':
        value /= 1000
    elif unit == 'ms' and displayed_unit == 's':
        value *= 1000
    return value


def parse_visible(text, url, device, scope, report_url):
    """Use separate field/lab sections so repeated metric names cannot be mixed."""
    row = extract_psi({})
    row.update({"Error": "", "Status": "OK", "Collection method": "PageSpeed website",
                "Measured UTC": now(), "Final URL": "", "PageSpeed link": report_url,
                "Warnings": "Values match the displayed PageSpeed precision. CWV assessment is taken from the website."})
    parts = text.split('Diagnose performance issues', 1)
    field, lab = parts if len(parts) == 2 else (text, '')
    for label in METRICS[5:9]:
        row[label] = visible_number(lab, label, before=True)
    for label, report_name in [('First Contentful Paint', 'Lab FCP (s)'), ('Largest Contentful Paint', 'Lab LCP (s)'),
                               ('Total Blocking Time', 'Lab TBT (ms)'), ('Cumulative Layout Shift', 'Lab CLS'), ('Speed Index', 'Lab Speed Index (s)')]:
        row[report_name] = visible_number(lab, label, unit='ms' if '(ms)' in report_name else 's' if '(s)' in report_name else None)
    for label, name in [('Largest Contentful Paint (LCP)', 'LCP (s)'), ('Interaction to Next Paint (INP)', 'INP (ms)'),
                        ('Cumulative Layout Shift (CLS)', 'CLS'), ('First Contentful Paint (FCP)', 'FCP (s)'), ('Time to First Byte (TTFB)', 'TTFB (s)')]:
        row[name] = visible_number(field, label, unit='ms' if '(ms)' in name else 's' if '(s)' in name else None)
    if any(row[k] is not None for k in METRICS[:5]):
        if scope not in {'URL', 'Origin'}:
            raise FetchError('Cannot identify whether the displayed field data describes the URL or origin.')
        row['Field source'] = 'PageSpeed website / ' + scope
        p = urllib.parse.urlsplit(url)
        row['Field URL'] = url if scope == 'URL' else f'{p.scheme}://{p.netloc}'
        row['Field period'] = 'Latest 28-day period (as displayed)'
        match = re.search(r'Core Web Vitals Assessment:\s*(Passed|Failed)', field)
        row['CWV assessment'] = match.group(1) if match else 'Unavailable'
    if not any(row[name] is not None for name in METRICS):
        raise FetchError('PageSpeed returned no measurements. The visible page was saved for review.')
    if any(row[name] is None for name in METRICS[5:]):
        row['Status'] = 'Partial'
        row['Error'] = ('Google Lighthouse is overloaded. Available field values are retained; retry the missing lab measurements later.'
                        if re.search('overloaded|THROTTLED_TASK_LIMIT|Too many render requests', lab, re.I) else
                        'PageSpeed did not finish all Lighthouse measurements. Available values are retained; missing values are N/A.')
    match = re.search(r'Lighthouse\s+([\d.]+)', lab)
    row['Lighthouse version'] = match.group(1) if match else ''
    captured = re.search(r'Captured at ([^\n]+)', lab)
    row['PageSpeed captured time'] = captured.group(1) if captured else ''
    return row


def collect(url, device, raw_dir, stem, analysis_url=None):
    partial = None
    for attempt in range(2):
        try:
            row = collect_once(url, device, raw_dir, stem + (f'_retry{attempt}' if attempt else ''), analysis_url if not attempt else None)
            if row['Status'] == 'OK':
                return row
            if 'overloaded' in row['Error']:
                return row
            if partial is None or sum(row[k] is not None for k in METRICS) > sum(partial[k] is not None for k in METRICS):
                partial = row
        except FetchError:
            if attempt:
                if partial:
                    return partial
                raise
    return partial


def collect_once(url, device, raw_dir, stem, analysis_url=None):
    from playwright.sync_api import sync_playwright, Error as BrowserError, TimeoutError as BrowserTimeout
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(locale='en-US', viewport={'width': 1440, 'height': 1000})
            if analysis_url:
                parsed = urllib.parse.urlsplit(analysis_url)
                target = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode({'form_factor': device})))
                page.goto(target, wait_until='domcontentloaded', timeout=60000)
            else:
                page.goto('https://pagespeed.web.dev/', wait_until='domcontentloaded', timeout=60000)
                page.get_by_role('textbox').fill(url)
                page.get_by_role('button', name='Analyze', exact=True).click()
            tab = page.locator(f'#{device}_tab')
            tab.wait_for(state='visible', timeout=60000)
            tab.click()
            panel = page.locator(f'[role="tabpanel"][aria-labelledby="{device}_tab"]')
            panel.wait_for(state='visible', timeout=60000)
            page.wait_for_function("device => document.getElementById(device + '_tab')?.getAttribute('aria-selected') === 'true'",
                                   arg=device, timeout=60000)
            # Wait for the server-side Lighthouse job, not merely the first field metrics.
            try:
                page.wait_for_function(r"""device => {
                const tab = document.getElementById(device + '_tab');
                const panel = document.querySelector('[role="tabpanel"][aria-labelledby="' + device + '_tab"]');
                return tab?.getAttribute('aria-selected') === 'true' && panel && (
                    ([...panel.querySelectorAll('.lh-metric__value')].filter(e => e.getClientRects().length && /[0-9]/.test(e.innerText)).length >= 5 &&
                    ['Performance', 'Accessibility', 'Best Practices', 'SEO'].every(label =>
                        new RegExp('(?:^|\\n)\\s*\\d{1,3}\\s*\\n' + label + '(?:\\n|$)').test(panel.innerText))) ||
                    /Oops! Something went wrong|failed to retrieve the LHR|Unable to resolve|CAPTCHA/i.test(panel.innerText));
                }""", arg=device, timeout=300000 if device == 'desktop' else 180000)
            except BrowserTimeout:
                # The field section can be valid even when Lighthouse times out.
                # Parse what is visible, and never promote an incomplete result to OK.
                pass
            if tab.get_attribute('aria-selected') != 'true' or not panel.is_visible():
                raise FetchError(f'The {device} results panel is not selected; no readings were copied.')
            scope = None
            url_button = panel.get_by_role('button', name='This URL', exact=True)
            origin_button = panel.get_by_role('button', name='Origin', exact=True)
            if url_button.count() and url_button.is_enabled():
                url_button.click()
                scope = 'URL'
            elif origin_button.count() and origin_button.is_enabled():
                origin_button.click()
                scope = 'Origin'
            text = page.locator('body').inner_text()
            (raw_dir / f'{stem}_page.txt').write_text(text, encoding='utf-8')
            (raw_dir / f'{stem}_page.html').write_text(page.content(), encoding='utf-8')
            page.screenshot(path=str(raw_dir / f'{stem}_page.png'), full_page=True)
            # Read only this device's panel, never values belonging to the other tab.
            row = parse_visible(panel.inner_text(), url, device, scope, page.url)
            save_json(raw_dir / f'{stem}_browser.json', row)
            return row
        except BrowserError as exc:
            if browser and 'page' in locals():
                try:
                    (raw_dir / f'{stem}_failure.txt').write_text(page.locator('body').inner_text(timeout=5000), encoding='utf-8')
                except BrowserError:
                    pass
            raise FetchError('Browser analysis could not finish. Check Chrome and your internet connection, then retry. ' + type(exc).__name__) from None
        finally:
            if browser:
                browser.close()
