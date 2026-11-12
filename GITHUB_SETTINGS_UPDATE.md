# Publish the cloud settings update

This update keeps GitHub Pages and GitHub Actions. Audits run on GitHub; your
Mac does not need to stay on. The live website will change only after these
source files are committed and the Pages workflow completes.

The update adds:

- Clear links from the report portal to the GitHub run form, daily defaults,
  and saved feed configuration.
- An optional `rss_feeds` input in **Run workflow** to change feeds for a run.
- A `PAGESPEED_RSS_FEEDS` repository variable for daily runs.

## Apply the update

1. Open your current default-branch checkout of
   `suryanarayanand/PageSpeedTool`.
2. Extract `artifacts/PageSpeedTool-cloud-settings-update.zip` over that
   checkout, preserving the `.github` and `templates` directories.
3. Review, commit, and push these updated files to the default branch:

   ```text
   .github/workflows/daily-pages.yml
   cloud_audit.py
   publish_static.py
   templates/public_dashboard.html
   test_static_cloud.py
   DEPLOYMENT.md
   ```

   Alternatively, edit or upload the corresponding files using GitHub's web
   interface, keeping each file in its listed directory.
4. Open **Actions > Daily PageSpeed reports > Run workflow**. To publish the
   updated portal without collecting new data, turn off **Collect new
   measurements**, then run the workflow. Wait for **Publish the report portal**
   to finish.
5. Refresh your Pages website. Use **Change settings in GitHub**, then
   **Run workflow**, to edit inputs for your next audit. Leave **Collect new
   measurements** enabled for an audit that should collect updated values.

You must use a GitHub account with repository write access to start a workflow.
The public reports remain available without signing in.

## Change feed data for a run

In **RSS feeds**, paste a JSON object, for example:

```json
{"BL": ["https://www.thehindubusinessline.com/markets/feeder/default.rss"]}
```

Select `BL` in **Publications**. Other selected publications keep their existing
feeds. You can add a publication by supplying its feed here and including its
name in **Publications**. The article count and devices apply to the selected
publications.

A blank RSS input uses `PAGESPEED_RSS_FEEDS` when that repository variable is
set, otherwise `config.json`. Use `{}` to ignore that variable for a manual run.
For permanent feed changes, edit `config.json` through the portal's
**feed configuration** link and commit the change.

Completed report measurements remain in history; a new audit collects new
values. This update does not replace saved reports, credentials, or browser
profiles.

## Checked locally

All 56 automated tests pass. Workflow YAML and RSS input wiring were checked.
The static portal was rebuilt using existing saved measurements. GitHub could
not be reached from this Codex session, so the source update has not been pushed
or deployed and a live GitHub audit has not been verified.
