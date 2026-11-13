# Free public report portal

Use **GitHub Pages + GitHub Actions in a public repository**. GitHub hosts the report website, and Actions collects measurements headlessly in the cloud. Your Mac can be off. Anyone with the website link can inspect dated results and download Excel without signing in.

GitHub documents [free Pages availability for public repositories](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) and [free standard Actions runners for public repositories](https://docs.github.com/en/billing/concepts/product-billing/github-actions). The workflow uses standard `windows-latest` and `ubuntu-latest` runners and refuses to run in a private repository. It declares no paid server or persistent disk. Source code and report snapshots in this repository will be public.

## One-time activation

1. Copy this updated project, including `.github/workflows/daily-pages.yml` and `cloud_history_seed/`, into a public GitHub repository you can write to. Commit and push the files to its default branch.
2. In **Settings → Pages**, select **GitHub Actions** as the build and deployment source.
3. In **Settings → Actions → General**, allow the workflow token to read and write repository contents. This lets it preserve report snapshots on the separate `report-history` branch. Repository rules must allow that branch to be updated by the workflow.
4. In **Actions → Daily PageSpeed reports → Run workflow**, disable **Collect new measurements** for the first publication if you only want to publish your existing results. Run the workflow.
5. Open the URL shown by the **Publish the report portal** step. It normally follows `https://OWNER.github.io/REPOSITORY/`. This URL becomes active only after a successful deployment.

The included seed contains the existing completed report snapshots, with their original dates and missing-value status. Initial publication does not invent or recalculate historical measurements.

## Article-count runs

Use **Run audits** on the public portal to open the workflow form. GitHub requires repository write access to start a manual workflow; ordinary visitors can only view reports. See [GitHub's manual workflow documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Choose the article count per publication, publications, devices, and collector. **Auto** uses the PageSpeed API when a `PAGESPEED_API_KEY` secret is present; otherwise it uses a headless browser on the GitHub Windows runner. No Chrome window opens on the viewer's computer. **API** requires the repository secret; **Browser** needs no PageSpeed API key.

The portal's **Change settings in GitHub** button opens this form from any device.
Click **Run workflow** above the workflow runs to reveal the editable inputs.
Leave **Collect new measurements** enabled when you want new results; disabling
it republishes existing history without collecting data. Viewing a completed run
shows the settings it already used. To change them, start a new workflow run.

Use the optional **RSS feeds as JSON** input to replace feeds for selected
publications for a run. For example:

```json
{"BL": ["https://www.thehindubusinessline.com/markets/feeder/default.rss"]}
```

Unspecified publications keep their configured feeds. To add a publication such
as `FL`, supply its feed in this JSON and include `FL` in **Publications**. These
inputs do not edit `config.json` or historical report values. To permanently
change feed configuration, use the portal's **feed configuration** link, edit
`config.json` on GitHub, and commit the change.

Runs finish after the selected article/device checks. Each completed run adds dated rows to the progressive report. Google failures remain N/A, alongside earlier valid results. Source snapshots are preserved in `report-history`; rebuilding the same run does not duplicate it. The application source branch is not modified by data updates.

Frontline must have an RSS feed supplied in the RSS input, the
`PAGESPEED_RSS_FEEDS` repository variable, or `config.json` before `FL` can be selected.

## Daily updates

The report website is your viewing page; the Actions page shows execution and
deployment logs. After both **build** and **deploy** finish, use the links under
**Published PageSpeed reports** on the run's Summary page. The portal provides
the progressive HTML report, cumulative Excel, and individual dated reports.
Canonical measurements are stored as JSON under `runs/` on the separate
`report-history` branch. The temporary Pages deployment artifact is deleted
after successful deployment; use the portal downloads for reports.

While **build** is running and **deploy** is waiting, the portal still shows the
previous publication. A green workflow status means deployment succeeded;
review the measurement summary for unavailable metrics or failed audits.

HTTP requests now have a total deadline covering DNS resolution, connection,
response reading, and all retries: 30 seconds for each feed request and 120
seconds for each API request. A stalled request is stopped and recorded as an
error while other checks continue. Browser collection keeps its separate
documented per-device waits. The workflow does not impose a collection-time
budget on the whole article-count run.

The default schedule starts daily at **09:00 India time (03:30 UTC)**. GitHub can delay scheduled jobs; this is not a guaranteed execution time. Each run still uses an article count, with no fixed collection-time window. GitHub's overall job-duration limit also applies.

Set these repository **Settings → Secrets and variables → Actions → Variables** to change daily defaults:

| Variable | Default | Meaning |
| --- | --- | --- |
| `PAGESPEED_DAILY_ENABLED` | Enabled | Set `false` for manual runs only |
| `PAGESPEED_ARTICLES_PER_PUBLICATION` | `1` | Requested articles for each selected publication |
| `PAGESPEED_PUBLICATIONS` | `TH,BL,SS` | Configured publications to sample |
| `PAGESPEED_DEVICES` | `both` | `both`, `mobile`, or `desktop` |
| `PAGESPEED_COLLECTOR` | `auto` | `auto`, `api`, or `browser` |
| `PAGESPEED_RSS_FEEDS` | Empty | Optional publication-to-feed JSON, in the same format as the manual RSS input |

Manual form inputs apply to that run. A blank RSS input uses `PAGESPEED_RSS_FEEDS`
when set; enter `{}` to use only `config.json` for a manual run. Repository
variables control scheduled runs. GitHub may require re-enabling schedules on
forks or inactive repositories.

Optional repository **Secrets** are `PAGESPEED_API_KEY` and `CRUX_API_KEY`. Enable the relevant Google APIs before using those keys. They are never entered into the public website or committed to the history branch. The browser collector can operate without these keys.

## Public report data

The portal offers:

- A date selector in India time and links to individual daily runs.
- A progressive HTML report with the original workbook layout.
- A cumulative Excel download containing all archived runs.
- An Excel download for each individual run.

The website contains generated HTML, Excel, and summarized JSON. Browser profiles, credentials, and raw browser evidence are excluded. All links work under the repository's project URL.

## Free-plan limits

The generated site is limited to **100 MB** by the publisher. GitHub's published Pages-site limit is **1 GB**, with a soft bandwidth limit of **100 GB/month**; see [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits). The workflow keeps its temporary deployment artifact for at most one day and deletes it after a successful deployment. The durable report history is stored in Git, rather than in retained Actions artifacts.

Use a public repository and standard runners, and keep paid spending disabled in the GitHub account. Artifact/storage allowances are shared with other account usage, so GitHub's current free-plan limits still apply. No paid Render service is configured.

## Local preview and tests

```bash
.venv/bin/python publish_static.py _site --repository OWNER/REPOSITORY
.venv/bin/python -m http.server 8080 --directory _site
```

Open `http://127.0.0.1:8080`. This previews existing measurements; it does not run new audits. The free cloud workflow performs the equivalent publication on GitHub.

```bash
.venv/bin/python -m unittest discover -s . -p 'test_*.py' -v
```

The Docker files remain available for an existing server, but are not needed for the free GitHub Pages deployment.
