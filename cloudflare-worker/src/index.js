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

export default {
	async scheduled(controller, env, ctx) {
		ctx.waitUntil(dispatch(env, controller.scheduledTime));
	},
};

async function dispatch(env, scheduledTime) {
	if (!env.GH_TOKEN) {
		console.error("GH_TOKEN is not set. Add it with: wrangler secret put GH_TOKEN");
		return;
	}

	// Cloudflare cron executes on UTC; Uganda is UTC+3 with no daylight saving.
	// controller.scheduledTime is epoch milliseconds, not a Date object.
	console.log(`BOU dispatch: firing for ${formatEastAfricaTime(scheduledTime)}`);

	const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;

	const response = await fetch(url, {
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

	// 204 is GitHub's documented success response for a dispatch.
	if (response.status === 204) {
		console.log(`Dispatch accepted (204) for ref=${REF}`);
		return;
	}

	// 409 means a run is already queued or in progress, which is harmless.
	if (response.status === 409) {
		console.log("A run is already queued or in progress; nothing to do.");
		return;
	}

	const body = await response.text().catch(() => "");
	console.error(
		`Dispatch failed: HTTP ${response.status} ${response.statusText} ${body.slice(0, 300)}`,
	);
}

function formatEastAfricaTime(epochMs) {
	const eat = new Date(epochMs + 3 * 60 * 60 * 1000);
	return `${eat.toISOString().replace("T", " ").slice(0, 19)} EAT`;
}
