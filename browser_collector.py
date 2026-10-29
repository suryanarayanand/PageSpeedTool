"""Collect visible measurements from the public PageSpeed Insights website."""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import sys
import tempfile
import urllib.parse

from engine import FetchError, METRICS, extract_psi, now, save_json
from runtime_config import boolean_setting

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))

LIGHTHOUSE_READY = r"""device => {
    const tab = document.getElementById(device + '_tab');
    const panel = document.querySelector('[role="tabpanel"][aria-labelledby="' + device + '_tab"]');
    if (!panel || tab?.getAttribute('aria-selected') !== 'true') return false;
    const visible = element => element.getClientRects().length > 0;
    const labels = ['Performance', 'Accessibility', 'Best Practices', 'SEO'];
    const scores = {}, errors = [];
    for (const gauge of panel.querySelectorAll('.lh-gauge__wrapper')) {
        if (!visible(gauge)) continue;
        const label = gauge.querySelector('.lh-gauge__label')?.textContent.trim();
        if (!labels.includes(label)) continue;
        const value = gauge.querySelector('.lh-gauge__percentage');
        if (!value) continue;
        if (value.classList.contains('lh-gauge--error')) {
            scores[label] = null;
            if (!errors.includes(label)) errors.push(label);
        } else if (/^\d{1,3}$/.test(value.textContent.trim())) {
            scores[label] = Number(value.textContent.trim());
        }
    }
    // Keep the text fallback for PageSpeed layouts without Lighthouse gauges.
    for (const label of labels) {
        if (label in scores) continue;
        const found = panel.innerText.match(new RegExp('(?:^|\\n)\\s*(\\d{1,3})\\s*\\n' + label + '(?:\\n|$)'));
        if (found) scores[label] = Number(found[1]);
    }
    const allCategories = labels.every(label => label in scores);
    const labCount = [...panel.querySelectorAll('.lh-metric__value')]
        .filter(element => visible(element) && /[0-9]/.test(element.innerText)).length;
    if (allCategories && (errors.length > 0 || labCount >= 5)) {
        const details = [...panel.querySelectorAll('.lh-metric--error .lh-tooltip, .lh-tooltip--error, .lh-runtime-error')]
            .map(element => element.textContent.trim()).filter(Boolean);
        return {scores, terminal_errors: errors, error_details: [...new Set(details)]};
    }
    return /Oops! Something went wrong|failed to retrieve the LHR|Unable to resolve|CAPTCHA|overloaded|THROTTLED_TASK_LIMIT|Too many render requests/i.test(panel.innerText);
}"""


@contextmanager
def chrome_profile():
    if sys.platform == 'darwin':
        # Keep managed extensions and connection setup across Mac audits.
        profile = ROOT / 'browser_profile'
        profile.mkdir(mode=0o700, exist_ok=True)
        yield str(profile)
    else:
        with tempfile.TemporaryDirectory(prefix='pagespeed-chrome-') as profile:
            yield profile


def network_url(url):
    """Keep the endpoint, excluding query strings, credentials, and fragments."""
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.hostname or '', parsed.path, '', ''))


def pagespeed_backend(url):
    host = urllib.parse.urlsplit(url).hostname or ''
    return host == 'pagespeed.web.dev' or host.endswith('.googleapis.com')


def network_problem(events):
    for event in events:
        error = event.get('error', '')
        if 'ERR_BLOCKED_BY_ADMINISTRATOR' in error or 'ERR_BLOCKED_BY_CLIENT' in error:
            return ('Chrome or a managed browser extension blocked a PageSpeed request. '
                    'Ask IT to review access to PageSpeed Insights and its Google API endpoints.', 403)
        if 'ERR_NAME_NOT_RESOLVED' in error:
            return ('Chrome could not resolve a PageSpeed service hostname on this Mac. '
                    'Check the Mac DNS, proxy, or company network configuration.', 503)
        if 'ERR_CERT_' in error or 'ERR_PROXY_' in error or 'ERR_TUNNEL_' in error:
            return ('Chrome could not connect to PageSpeed because of a certificate or proxy error. '
                    'Check the visible Chrome window and the Mac network configuration.', 503)
    for event in events:
        if event.get('status') in {403, 429}:
            status = event['status']
            return (f'A PageSpeed service request returned HTTP {status}. '
                    'Check service access or quota before retrying. Network evidence is saved with the run.', status)
    return None


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


def parse_visible(text, url, device, scope, report_url, category_scores=None, terminal_errors=()):
    """Use separate field/lab sections so repeated metric names cannot be mixed."""
    row = extract_psi({})
    row.update({"Error": "", "Status": "OK", "Collection method": "PageSpeed website",
                "Measured UTC": now(), "Final URL": "", "PageSpeed link": report_url,
                "Warnings": "Values match the displayed PageSpeed precision. CWV assessment is taken from the website."})
    parts = text.split('Diagnose performance issues', 1)
    field, lab = parts if len(parts) == 2 else (text, '')
    for label in METRICS[5:9]:
        row[label] = visible_number(lab, label, before=True)
    if category_scores is not None:
        for label in METRICS[5:9]:
            if label in category_scores:
                row[label] = category_scores[label]
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
        raise FetchError('PageSpeed returned no measurements. The visible page was saved for review.',
                         status=400 if terminal_errors else None)
    if any(row[name] is None for name in METRICS[5:]):
        row['Status'] = 'Partial'
        if terminal_errors:
            row['Lighthouse terminal error'] = True
            names = ', '.join(label for label in METRICS[5:9] if label in terminal_errors)
            row['Error'] = (f'Google Lighthouse finished with an error for {names}. '
                            'Available field metrics and scores are saved; missing values are N/A.')
        else:
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
            if 'overloaded' in row['Error'] or row.get('Lighthouse terminal error'):
                return row
            if partial is None or sum(row[k] is not None for k in METRICS) > sum(partial[k] is not None for k in METRICS):
                partial = row
        except FetchError as exc:
            # A rejected URL will not become valid by immediately resubmitting it.
            if exc.status in {400, 403, 429}:
                raise
            if attempt:
                if partial:
                    return partial
                raise
    return partial


def collect_once(url, device, raw_dir, stem, analysis_url=None):
    from playwright.sync_api import sync_playwright, Error as BrowserError, TimeoutError as BrowserTimeout
    with sync_playwright() as p, chrome_profile() as profile:
        context = None
        network = []
        try:
            # Managed security extensions need an ordinary browser context and
            # background networking. Keep them enabled in a separate profile.
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile,
                channel=os.getenv('PAGESPEED_BROWSER_CHANNEL', 'chrome'),
                headless=boolean_setting('PAGESPEED_CLOUD') or boolean_setting('PAGESPEED_HEADLESS', True),
                chromium_sandbox=True,
                ignore_default_args=[
                    '--disable-extensions',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-background-networking',
                    '--disable-component-update',
                ],
                locale='en-US', viewport={'width': 1440, 'height': 1000},
            )
            page = context.pages[0] if context.pages else context.new_page()
            def request_failed(request):
                if len(network) < 100 and pagespeed_backend(request.url):
                    code = re.search(r'net::[A-Z_]+', request.failure or '')
                    network.append({'url': network_url(request.url), 'error': code.group(0) if code else 'Request failed'})
            def response_received(response):
                if len(network) < 100 and response.status >= 400 and pagespeed_backend(response.url):
                    network.append({'url': network_url(response.url), 'status': response.status})
            page.on('requestfailed', request_failed)
            page.on('response', response_received)
            if analysis_url:
                parsed = urllib.parse.urlsplit(analysis_url)
                target = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode({'form_factor': device})))
                page.goto(target, wait_until='domcontentloaded', timeout=60000)
            else:
                page.goto('https://pagespeed.web.dev/', wait_until='domcontentloaded', timeout=60000)
                page.get_by_role('textbox').fill(url)
                page.get_by_role('button', name='Analyze', exact=True).click()
            tab = page.locator(f'#{device}_tab')
            # URL rejection happens before any results tabs exist. Do not turn
            # Google's explicit error into a tab timeout and then retry it.
            page.wait_for_function(r"""device => {
                const tab = document.getElementById(device + '_tab');
                return (tab && tab.getClientRects().length > 0) ||
                    /Unable to resolve\s+https?:\/\//i.test(document.body?.innerText || '');
            }""", arg=device, timeout=60000)
            if not tab.is_visible():
                text = page.locator('body').inner_text()
                if re.search(r'Unable to resolve\s+https?://', text, re.I):
                    (raw_dir / f'{stem}_failure.txt').write_text(text, encoding='utf-8')
                    problem = network_problem(network)
                    if problem:
                        raise FetchError(problem[0], status=problem[1])
                    raise FetchError(
                        'Google PageSpeed could not resolve this article URL. Open its PageSpeed '
                        'link to verify the address and website availability. '
                        'Google returned no performance measurements.', status=400,
                    )
            tab.wait_for(state='visible', timeout=60000)
            tab.click()
            panel = page.locator(f'[role="tabpanel"][aria-labelledby="{device}_tab"]')
            panel.wait_for(state='visible', timeout=60000)
            page.wait_for_function("device => document.getElementById(device + '_tab')?.getAttribute('aria-selected') === 'true'",
                                   arg=device, timeout=60000)
            # Wait for the server-side Lighthouse job, not merely the first field metrics.
            readiness = None
            try:
                readiness = page.wait_for_function(LIGHTHOUSE_READY, arg=device,
                                                   timeout=300000 if device == 'desktop' else 180000).json_value()
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
            if isinstance(readiness, dict):
                row = parse_visible(panel.inner_text(), url, device, scope, page.url,
                                    category_scores=readiness.get('scores'),
                                    terminal_errors=readiness.get('terminal_errors', ()))
                details = readiness.get('error_details', [])
                if details and row.get('Lighthouse terminal error'):
                    row['Lighthouse error details'] = details
                    row['Error'] += ' Details: ' + '; '.join(details)[:1000]
            else:
                row = parse_visible(panel.inner_text(), url, device, scope, page.url)
            save_json(raw_dir / f'{stem}_browser.json', row)
            return row
        except BrowserError as exc:
            if context and 'page' in locals():
                try:
                    (raw_dir / f'{stem}_failure.txt').write_text(page.locator('body').inner_text(timeout=5000), encoding='utf-8')
                except BrowserError:
                    pass
            problem = network_problem(network)
            if problem:
                raise FetchError(problem[0], status=problem[1]) from None
            if context is None:
                raise FetchError(
                    'Chrome could not start. If ManageEngine or another company security tool '
                    'shows a block, ask IT to review this Chrome automation workflow, or use '
                    'Advanced settings > Google API with an enabled PageSpeed API key. '
                    + type(exc).__name__
                ) from None
            raise FetchError('Browser analysis could not finish. Check Chrome and your internet connection, then retry. ' + type(exc).__name__) from None
        finally:
            try:
                if network:
                    save_json(raw_dir / f'{stem}_network.json', network)
            finally:
                if context:
                    context.close()
