# Configure Google APIs for cloud report collection

The Excel downloaded on 30 October 2026 records HTTP 429 for all six checks in run `20261030_053711_353e461b`. These are failed requests to PageSpeed services, rather than usable measurements. The existing valid historical data is retained.

Google [recommends an API key for automated PageSpeed queries](https://developers.google.com/speed/docs/insights/v5/get-started). The current application already supports collecting through the official APIs, without launching a browser. A key identifies your Google project; that project must have the relevant APIs enabled and available quota.

## Set up the Google project

1. In Google Cloud, select or create the project you want to use.
2. Enable [PageSpeed Insights API](https://console.cloud.google.com/apis/library/pagespeedonline.googleapis.com).
3. Enable [Chrome UX Report API](https://console.cloud.google.com/apis/library/chromeuxreport.googleapis.com) for real-user Core Web Vitals.
4. Open [Credentials](https://console.cloud.google.com/apis/credentials), choose **Create credentials → API key**, and restrict the key to these two APIs. Browser referrer restrictions do not apply to this server-side workflow; GitHub cloud runners also do not have a single fixed outbound IP address for an IP allowlist.
5. Check the APIs' quota pages for available capacity. A project whose quota is exhausted can still return HTTP 429 even with a valid key.

The [CrUX API documentation](https://developer.chrome.com/docs/crux/api/#rate-limits) states that its quota is 150 queries per minute per project, offered without charge. Missing CrUX data for an article or origin remains N/A. Real-user metrics describe a rolling aggregation period; they are not a new individual lab test on each run.

## Add repository secrets

Open [PageSpeedTool Actions secrets](https://github.com/suryanarayanand/PageSpeedTool/settings/secrets/actions). Create these **repository secrets**, using the key from the project above for both when it is enabled and permitted for both APIs:

| Secret name | Purpose |
| --- | --- |
| `PAGESPEED_API_KEY` | Lighthouse lab measurements and scores |
| `CRUX_API_KEY` | Real-user Core Web Vitals, with URL/origin availability handled by the collector |

Enter the key in the GitHub secret value fields. Do not put it in source files, the public portal, or chat. This Google API key is separate from the GitHub personal access token used for Git pushes.

## Run a small verification

1. Open [Daily PageSpeed reports](https://github.com/suryanarayanand/PageSpeedTool/actions/workflows/daily-pages.yml).
2. Choose **Run workflow**, branch `main`, one article per publication, the desired publications and devices, and collector **auto** or **api**. Check **Collect new measurements**.
3. Start a new run. **Auto** selects the API when `PAGESPEED_API_KEY` is set. No workflow file change is needed.
4. Inspect the resulting run's measurement status and error details as well as the workflow deployment status. Successful deployment can publish a report containing failed or partial measurements.
5. After deployment, open the portal again and use **Command + Shift + R** to refresh an already-open progressive report tab.

If API calls still return 429, inspect that project's quota and the saved error before rerunning repeatedly. A valid key does not guarantee that every article has real-user data or that every Lighthouse test will succeed.
