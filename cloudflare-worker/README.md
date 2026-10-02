# Cloudflare Worker: BOU rate dispatch

A tiny Cloudflare Worker that fires the
[`send-rates.yml`](../.github/workflows/send-rates.yml) GitHub Actions
workflow at **07:30 EAT every weekday**.

## Status: trigger registered, but not firing

The Worker is deployed and its cron trigger is registered as `30 4 * * 1-5`,
but **no cron invocation has been observed**. Two weekday slots passed with no
dispatch, and a throwaway control Worker on `* * * * *` also never fired, which
points at this Cloudflare account rather than at this repository.

Until that is resolved, `send-rates.yml` keeps its own `cron:` as the working
scheduler. The email may therefore arrive hours late — but it arrives. Because
both schedulers can be live at once, that workflow now skips the send if a
successful run already happened that day, so the two cannot double-email.

Restore the Worker as the primary once its cron executes.

## Why this exists

GitHub Actions schedules are best-effort. Measured delays on this repo
(free tier) ranged from **2h55m to 6h19m** — a 07:30 EAT schedule
actually executed at 13:49 EAT. That misses an 08:00 deadline.

Cloudflare Workers cron is meant to fire reliably to the minute. The Worker only
*sends the signal*; the scraping and emailing still happen in GitHub
Actions, so the existing repository secrets are used unchanged and no
new secret is introduced into the scrape path.

Measured job duration: the scrape takes ~75s, the full Actions job ~3
minutes. So a 07:30 dispatch puts the email in the inbox around 07:33.

## Setup

**1. Create a fine-grained personal access token**

GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token.

- **Resource owner:** `cityrider503-ux`
- **Repository access:** Only select repositories → `bou-exchange-rates`
- **Permissions:** `Actions` → **Read and write**
- Nothing else. This token can trigger workflows on this one repo and
  do nothing else.

**2. Install Wrangler and authenticate**

```bash
npm install -g wrangler
wrangler login
```

**3. Store the token as a secret**

```bash
wrangler secret put GH_TOKEN
```

Paste the token when prompted. It is stored encrypted and never written
to disk or committed. Confirm it is not in `git status`.

**4. Deploy**

```bash
wrangler deploy
```

## Verify

```bash
# Fires the Worker immediately, without waiting for the schedule
wrangler dev --remote
# then, in another shell:
curl "http://localhost:8787/cdn-cgi/local/scheduled"
```

Or check the real schedule: **Workers & Pages** → your Worker →
**Settings** → **Triggers** → **View events**. The last 100 invocations
are logged there, and a `Dispatch accepted (204)` line means it worked.

Watch for the resulting run under the repository's **Actions** tab.

## Branch targeted

`REF` in `src/index.js` is set to `main`. It was `fix/silent-failures-and-validation`
until that branch was merged (PR #1).

A GitHub workflow can only be dispatched on a branch where the workflow file
itself exists, so `REF` must be a real branch name, not a commit SHA. If you
ever dispatch from a different branch, update `REF` and redeploy.

## Free plan limits

Confirmed against Cloudflare's limits documentation:

| Limit | Free plan | This Worker uses |
| --- | --- | --- |
| Cron triggers per account | 5 | 1 |
| Requests per day | 100,000 | ~5 |
| CPU per cron trigger | 10 ms | ~2 ms (one `fetch`) |
| Wall time per cron trigger | 15 min | <1 s |

The Worker also treats GitHub's `409` (a run already queued) as success,
so a duplicate dispatch is harmless — the `concurrency` group in
`send-rates.yml` prevents a second email.

### Retries

One cron fire is the only thing standing between the bank publishing rates and
the email arriving, so the dispatch retries up to 4 times with exponential
backoff (1s, 2s, 4s) on network errors and on HTTP 408, 429, 500, 502, 503 and
504. That is still well inside the 15-minute cron wall-time limit.

A 4xx response is **not** retried — the request itself is wrong (a bad or
expired `GH_TOKEN`, a missing workflow), and retrying would only burn the
invocation. The final failure throws either way, so it shows up as a failed
Worker log rather than silence.

## Troubleshooting

**No email arrived.** Check in this order:

1. **Cloudflare → Workers & Pages → `bou-rates-trigger` → Observability.**
   A failed dispatch appears there as a failed cron invocation. This is only
   possible while `observability.enabled` is `true` in `wrangler.toml`. With
   it off the Worker keeps no logs at all, and a failure is indistinguishable
   from a weekend — nothing dispatched, nothing to diagnose.
2. **The repository's Actions tab.** No `send-rates` run whatsoever means the
   Worker never dispatched, rather than the job having run and failed.
3. **Settings → Triggers.** Confirm the schedule is still `30 4 * * 1-5`.

### Cron triggers are UTC

Cloudflare cron triggers fire on **UTC** and offer no timezone option. Uganda
is UTC+3 with no daylight saving, so `30 4 * * 1-5` is **07:30 EAT**.

Typing `30 7 * * *` into the dashboard — reading it as 07:30 local time —
schedules **10:30 EAT**, three hours late. The drift is silent: the trigger
looks plausible in the UI and the Worker keeps firing on schedule. Change the
schedule through `wrangler.toml` and redeploy rather than in the dashboard, so
the repository stays the single source of truth and the two cannot drift.

## `rates-watchdog.yml`

Because this Worker fails quietly, a separate GitHub Actions workflow opens an
issue if no successful dispatch ran by 09:00 EAT on a weekday. Issues notify by
email, so the failure reaches you even though the Worker stayed silent. It uses
the automatic `GITHUB_TOKEN` and needs no extra secrets.

## Security note

`GH_TOKEN` is a real credential that can run workflows in this repository.
Scope it to this single repository and to `Actions: write` only, as
described above. If the token leaks, revoke it at
GitHub → Settings → Developer settings → Personal access tokens.
