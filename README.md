# SPX Put Spread Workbench

A single-page tool with two tabs:

- **This week's trade** — strike analysis, probabilities measured against ten years of SPX history, and a P&L matrix across price and time
- **Market brief** — what's moving SPX, regenerated automatically every weekday morning

## Files

| File | What it does |
|---|---|
| `index.html` | The whole site. Self-contained — no build step, no dependencies |
| `update_brief.py` | Calls the Anthropic API with web search, rewrites the brief section |
| `.github/workflows/daily-brief.yml` | Runs the script on a weekday cron |

The brief lives between `<!-- BRIEF:START -->` and `<!-- BRIEF:END -->` in
`index.html`. The script replaces everything between those markers and leaves the
rest of the page alone. **Don't delete those comments.**

## Setup

Follow these in order. About twenty minutes, most of it clicking.

### 1. Create the repo

On GitHub, click **New repository**. Name it `spx-workbench`. Set it **Public**
(GitHub Pages is free on public repos; private needs a paid plan). Don't add a
README — you already have one. Click **Create**.

### 2. Upload these files

On the empty repo page, click **uploading an existing file**. Drag in
`index.html`, `update_brief.py` and `README.md`.

The workflow file needs its folder structure, so add it separately:
**Add file → Create new file**, and type this as the filename:

```
.github/workflows/daily-brief.yml
```

Typing the slashes creates the folders. Paste the file contents in, then
**Commit changes**.

### 3. Add your API key

Get a key at <https://console.anthropic.com> → **API Keys**. This is separate
from a Claude subscription and is billed by usage.

In your repo: **Settings → Secrets and variables → Actions →
New repository secret**

- Name: `ANTHROPIC_API_KEY`
- Secret: paste the key

Click **Add secret**. GitHub encrypts it; it never appears in logs or in the repo.

### 4. Turn on Pages

**Settings → Pages**. Under *Source* choose **Deploy from a branch**, set the
branch to `main` and the folder to `/ (root)`. Click **Save**.

After a minute or two your site is live at:

```
https://YOUR-USERNAME.github.io/spx-workbench/
```

That URL is permanent. Share it once and it stays current.

### 5. Test the workflow before trusting it

**Actions** tab → **Daily market brief** → **Run workflow**. It takes two or
three minutes.

Green check: open the site and confirm the brief tab shows today's date.
Red X: click the run to read the error. See troubleshooting below.

## Schedule

The cron is `15 11 * * 1-5` — 11:15 UTC on weekdays, which is **7:15am ET** in
summer and **6:15am ET** in winter. GitHub cron runs on UTC and does not follow
daylight saving, so the local time shifts twice a year. Edit the workflow file if
you want it pinned to one or the other.

GitHub's scheduler is best-effort. Runs are commonly 5–15 minutes late and
occasionally longer under load. Fine for a morning brief.

## Cost

Each run does several web searches and generates roughly 2,000 words. Expect
**$0.10–0.30 per run**, so about **$3–7 a month** on weekdays. Hosting is free.

Set a spend limit in the Anthropic console under **Billing** if you want a
hard ceiling.

## Safety rails

`update_brief.py` refuses to publish and exits non-zero if the response is
suspiciously short, is missing any required section, has unbalanced `<div>` tags,
or contains a `<script>` tag. A failed run leaves the previous brief in place
rather than defacing the site.

The prompt forbids forecasting and position advice, and the published banner
states plainly that the brief is auto-generated and unreviewed.

**This is unsupervised output going to people you know.** The rails reduce the
risk of a bad run; they don't eliminate it. Read the brief yourself most days.

## Troubleshooting

**401 from the API** — the secret is missing, misnamed, or the key was revoked.
It must be named exactly `ANTHROPIC_API_KEY`.

**400 mentioning tools or web_search** — the search tool version string in
`update_brief.py` has moved on. Check the current identifier in the Anthropic
docs and update the `"type"` field.

**"Markers not found in index.html"** — the `BRIEF:START` / `BRIEF:END` comments
were removed. Restore them around the brief section.

**"REFUSING TO PUBLISH"** — the model returned something malformed. The log
prints the first 800 characters so you can see what came back. The site is
untouched; rerun it.

**Workflow never fires on schedule** — GitHub disables scheduled workflows in
repos with no activity for 60 days. Push any commit to re-enable.

**Site doesn't update after a successful run** — check the Pages deployment under
the Actions tab. Also try a hard refresh; browsers cache aggressively.

## Editing the brief by hand

Edit `index.html` between the markers and commit. The next scheduled run will
overwrite it. To pause automation, comment out the `schedule:` block in the
workflow and use **Run workflow** manually when you want it.
