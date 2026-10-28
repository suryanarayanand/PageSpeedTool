# RSS PageSpeed Reporter

An independent local tool for randomly sampling RSS articles and producing Excel and HTML performance reports. It runs separately from the Maestro portal.

## Start

1. Double-click `Start_PageSpeed_Reporter.bat`.
2. Open **http://127.0.0.1:5055**.
3. Select publications, choose the article count and devices, and click **Generate report**.
4. Keep the server running until the analysis finishes, then use the **HTML** or **Excel** links.

The dependencies are available on this computer (Waitress and Playwright are installed in this tool's `vendor` folder). Chrome must be installed for website collection. On another computer, install Python and Chrome and run `python -m pip install -r requirements.txt` from this folder first.

The six feeds supplied for TH, BL and SS are configured in `config.json`. Each publication's default and section feed are merged; duplicate article URLs (ignoring fragments) are removed. The default is **one article per publication, mobile and desktop: six audits**. Article count is per publication, not per feed. Sampling is without replacement within a run; later runs may select the same article. Edit feed URLs under **Advanced settings**, one URL per line. Add other publications in `config.json` when needed.

## Default collection: PageSpeed website

The default collector opens PageSpeed Insights in a background Chrome browser, enters each article URL, clicks Analyze, and confirms the requested device tab is selected and visible. It waits up to three minutes for mobile and five minutes for desktop, until all five Lighthouse lab metrics and four category scores appear (or Google reports an error). Readings are extracted only from the selected device panel, keeping mobile and desktop separate. **No API key is required for this workflow.** It uses a fresh temporary browser profile, not your personal Chrome session.

Website values use the same rounded precision you see on PageSpeed. The website's CWV assessment is preserved, because an assessment may use more precision than the displayed numbers. URL field data is preferred when available; otherwise origin data is explicitly selected and labelled. The tool saves page text, HTML, screenshots and extracted values as evidence, together with a link to the actual PageSpeed analysis. If field values load but Lighthouse stalls or reports overload, those values are retained and the result is marked **Partial**. Missing lab values remain N/A. Runs with no measurements at all are labelled **No measurements collected**, with a failure-details link instead of normal report download buttons. A clear Google overload response is not retried immediately.

To use the API instead, open Advanced settings and select **Google API**. For CLI configuration use `"collector": "browser"` or `"collector": "api"` in `config.json`.

## Google API setup

These settings apply only to the optional API collector. Create a Google Cloud project/API key and enable **PageSpeed Insights API**. Enter the key under Advanced settings or set `PAGESPEED_API_KEY` in the environment before starting the tool. Google documents keyless access, but shared anonymous quota may be exhausted. HTTP 429 means available quota is required; HTTP 403 may indicate API/key restrictions.

For real-user metrics, enable **Chrome UX Report API** and enter a key in the CrUX field or set `CRUX_API_KEY`. The same key can serve both APIs if both are enabled and its restrictions allow both. Google plans to remove CrUX data from PSI responses, so direct CrUX support is included. Keys entered in the form are held only for that run and are not saved to configuration or reports. Do not paste keys into `config.json`.

Official instructions: [PageSpeed API](https://developers.google.com/speed/docs/insights/v5/get-started), [CrUX API](https://developer.chrome.com/docs/crux/api), [PSI metrics and assessment](https://developers.google.com/speed/docs/insights/v5/about).

## Reports

Every run creates `reports/<UTC timestamp>_<unique ID>/`:

- `report.xlsx`: starts with **BenchMark, TH, BL, FL, SS, URL**, matching the reference's primary tabs. Publication sheets keep Date in A, Mobile in B–O, Desktop in P–AC, the three merged header rows, cyan/yellow device colours, original metric labels and column widths. The BenchMark sheet preserves the original reference guide. FL is labelled not configured when no FL feed is supplied. Summary, Results, URLs, Errors and Notes follow the primary tabs. Numeric measurements remain numeric; benchmark colours highlight field metrics and scores. Core Web Vitals Passed/Failed assessments are excluded from both Excel and HTML reports.
- `report.html`: publication summaries, filterable article results, metric ratings, errors, PageSpeed links, and Excel download. Open it directly or through the tool; keep it beside `report.xlsx` when sharing both.
- `run.json`: configuration (without API keys), actual random seed, sampled URLs, individual results, progress and status.
- `raw/`: feed snapshots and PageSpeed website evidence or successful API response payloads for traceability.

Metric order follows `TH,BL,FL,SS- Core Web Vitals.xlsx`: field LCP (seconds), INP (milliseconds), CLS, FCP (seconds), TTFB (seconds); Performance, Accessibility, Best Practices, SEO (0–100); lab FCP, LCP, TBT, CLS, Speed Index. Each sampled article gets a separate row. Publication row 4 corresponds to URL row 2, row 5 to URL row 3, and so on; Date cells link to the matching URL. Publication dates use India time. Cell comments retain the URL, field source and missing-data reason, without Passed/Failed assessments. A clean presentation template is bundled at `templates/reference_report.xlsx`; the original workbook and its historical measurements are untouched.

Field metrics are p75 real-user measurements over the CrUX rolling collection window, not today's lab measurements. URL-level data is preferred. When unavailable, origin-level data is explicitly labelled and its URL is recorded. Origin figures may repeat across sampled articles and must not be interpreted as article-level measurements. Direct CrUX results take precedence over PSI field data; the collection period is saved when returned. Without CrUX access, any available PSI field data is retained.

The API collector computes CWV from field LCP ≤ 2.5 seconds, INP ≤ 200 ms and CLS ≤ 0.1; when any is missing, assessment is **Unavailable**. The website collector preserves the assessment displayed by PageSpeed. Missing values are **N/A**, never zero. TBT is a Lighthouse lab metric and does not replace INP. Lighthouse measurements can vary between runs and between API and browser analyses made at different times.

Feed failures, quotas, timeouts and Lighthouse errors are retained in reports. **Complete** means all requested audits returned performance results without feed/sampling errors; it does not mean field data exists for every URL. **Partial** means some audits succeeded and errors remain; **Failed** means none succeeded. A partial feed failure still permits sampling from the remaining feed. If fewer unique URLs are available than requested, all available URLs are used and the shortfall is recorded. A stopped server leaves checkpointed results; the UI labels that run Interrupted. Start a fresh run to retry.

## Command line and scheduling

From this folder:

```powershell
python engine.py
python engine.py --sample-size 5
python engine.py --config config.json --seed 42
python -m unittest discover -s . -p test_engine.py -v
python check_connections.py
python resume_run.py reports/<run-folder>
```

`resume_run.py` continues an interrupted website run using the same sampled articles. It keeps existing complete/partial measurements and retries missing results. Do not run two workers on the same report folder; an active recorded worker is rejected.

Use the full Python executable path if the Windows `python` alias does not work. On this computer it is `C:\Users\12503\AppData\Local\Python\pythoncore-3.14-64\python.exe`.

For Windows Task Scheduler, set the program to the full Python path, arguments to `D:\AI_Maestro_Automation_Platform\PageSpeedTool\engine.py`, and Start in to `D:\AI_Maestro_Automation_Platform\PageSpeedTool`. Configure API environment variables for the account running the task. No scheduled task is installed automatically. Exit code 0 means Complete; 2 means Partial or Failed. Reports are kept per run rather than overwriting prior results. A fixed seed reproduces selection only if the feed contents and ordering are also identical.

The web interface binds to localhost and accepts one run at a time. It is intended for this computer, not public hosting. Each request has bounded retries and timeouts; a multi-article run can take several minutes. Use Ctrl+C in the launcher console to stop the server.
