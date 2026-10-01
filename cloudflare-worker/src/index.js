/**
 * Cloudflare Worker that triggers the BOU exchange-rate workflow on a schedule.
 *
 * Why this exists: GitHub Actions schedules are best-effort. On the free tier
 * the observed delay for this repo was 3-6 hours (a 07:30 EAT schedule
 * actually ran at 13:49 EAT), which is far too late for an 08:00 deadline.
 * This Worker fires a workflow_dispatch on Cloudflare's schedule instead,
 * which has been reliable to the minute.
 *
 * The Worker only dispatches. The real work (scraping, validating, emailing)
 * still happens in GitHub Actions, so the existing repo secrets are used and
 * nothing sensitive lives in this Worker.
 *
  * Failures throw rather than return quietly. A silent failure here is
  * indistinguishable from a weekend: no dispatch, no GitHub run, no email, and
  * nothing in the dashboard to explain it. A rejected cron invocation shows up
  * as a failed Worker log instead. The `observability` block in wrangler.toml
  * must stay enabled for those logs to be retained.
  *
 * Setup:
 *   1. npx wrangler secret put GH_TOKEN     # fine-grained PAT, Actions:write
 *   2. npx wrangler deploy
 *
 * Secrets are set with `wrangler secret put`, never committed.
 */

const REPO = "cityrider503-ux/bou-exchange-rates";
const WORKFLOW = "send-rates.yml";

/**
 * Branch to dispatch. The reliability fixes are merged, so this targets main.
 *
 * workflow_dispatch only works on a branch that actually contains the
 * workflow file, so this must stay a real branch name rather than a SHA.
 */
const REF = "main";

/**
 * A single cron fire is the only thing standing between the bank publishing
 * rates and the email arriving, so one transient 5xx or network blip silently
 * costs a whole day. These statuses are worth retrying; 4xx means the request
 * itself is wrong and retrying just burns the cron invocation.
 */
const MAX_ATTEMPTS = 4;
const RETRY_BASE_MS = 1_000;
const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

export default {
	async scheduled(controller, env, ctx) {
		ctx.waitUntil(dispatch(env, controller.scheduledTime));
	},
};

async function dispatch(env, scheduledTime) {
	if (!env.GH_TOKEN) {
		throw new Error(
			"GH_TOKEN is not set. Add it with: wrangler secret put GH_TOKEN",
		);
	}

	// Cloudflare cron executes on UTC; Uganda is UTC+3 with no daylight saving.
	// controller.scheduledTime is epoch milliseconds, not a Date object.
	console.log(`BOU dispatch: firing for ${formatEastAfricaTime(scheduledTime)}`);

	const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;

	for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
		const outcome = await attemptDispatch(url, env);

		if (outcome.ok) {
			console.log(`Dispatch accepted on attempt ${attempt} (${outcome.detail})`);
			return;
		}

		// 409 means a run is already queued or in progress, which is harmless.
		if (outcome.status === 409) {
			console.log("A run is already queued or in progress; nothing to do.");
			return;
		}

		if (!outcome.retryable || attempt === MAX_ATTEMPTS) {
			throw new Error(
				`Dispatch failed after ${attempt} attempt(s): ${outcome.detail}`,
			);
		}

		// Exponential backoff: 1s, 2s, 4s. Well inside the 15-minute cron
		// wall-time limit even with the scrape waiting on the other side.
		const waitMs = RETRY_BASE_MS * 2 ** (attempt - 1);
		console.warn(
			`Attempt ${attempt} failed (${outcome.detail}); retrying in ${waitMs}ms`,
		);
		await sleep(waitMs);
	}
}

async function attemptDispatch(url, env) {
	let response;
	try {
		response = await fetch(url, {
			method: "POST",
			headers: {
				Authorization: `Bearer ${env.GH_TOKEN}`,
				Accept: "application/vnd.github+json",
				"X-GitHub-Api-Version": "2022-11-28",
				"Content-Type": "application/json",
				"User-Agent": "bou-rates-cron-worker",
			},
			body: JSON.stringify({ ref: REF }),
		});
	} catch (err) {
		// A dropped or refused connection is worth another go.
		return {
			ok: false,
			retryable: true,
			detail: `network error: ${err?.message ?? err}`,
		};
	}

	// 204 is GitHub's documented success response for a dispatch.
	if (response.status === 204) {
		return { ok: true, status: 204, detail: "204" };
	}

	const body = await response.text().catch(() => "");
	return {
		ok: false,
		status: response.status,
		retryable: RETRYABLE_STATUSES.has(response.status),
		detail: `HTTP ${response.status} ${response.statusText} ${body.slice(0, 300)}`,
	};
}

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatEastAfricaTime(epochMs) {
	const eat = new Date(epochMs + 3 * 60 * 60 * 1000);
	return `${eat.toISOString().replace("T", " ").slice(0, 19)} EAT`;
}
