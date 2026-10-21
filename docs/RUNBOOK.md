# Runbook

How Golf Edge runs day to day. Architecture and rules: `CLAUDE.md`. What's
next: `docs/ROADMAP.md`. Anything in `docs/archive/` is history.

## What runs where

| Job | Where | When (America/Chicago unless noted) |
|---|---|---|
| Data refresh slots (`scheduled_refresh.py --schedule …`) | GitHub Actions `data-refresh.yml` | Sun 21:00 settle, Sun 23:00 record, Mon 06:00 + 08:00, Tue 06:00 + 18:00, Wed 06:00 + 18:00; DP World Tour rounds Thu-Sun 12:00 + 20:00 |
| Weekly predictions (`run_pipeline.py --auto-weekly …`) | GitHub Actions `tuesday-predictions.yml` | Tue 07:30, then model-sync once Render serves the new event |
| Model takes its picks | Vercel cron `/api/model-sync` | daily 12:00 UTC |
| Watchdog (re-dispatches dropped runs) | Vercel cron `/api/watchdog` | daily 15:00 UTC |
| Pick reminders | Vercel cron `/api/reminders-cron` | daily 16:00 UTC |
| API | Render (`golf-app-a3yw.onrender.com`), redeploys on every push to `main` | |
| Site | Vercel, deploys on every push to `main` | |

Both publishing workflows share the `publish-main` lock: one publishes at a
time, and each starts from the latest `main`.

## When something looks wrong

- **Did the run happen?** `gh run list -w data-refresh.yml -L 5` (or
  `tuesday-predictions.yml`). GitHub drops scheduled runs; the watchdog
  re-dispatches by outcome (no predictions yet, event not settled), so
  check again after 15:00 UTC before acting.
- **Predictions refused.** A red run whose log ends in Integrity, Freshness
  or Model artifacts failures published nothing on purpose; the last good
  board stays live. Rejected files are in `logs/rejected_outputs/` (local
  runs). Find the wrong input; never loosen a threshold (CLAUDE.md rule 2).
- **Re-run a slot by hand:** `gh workflow run data-refresh.yml -f schedule=tuesday-morning`
  (add `-f dry_run=true` to see what it would do). Weekly predictions:
  `gh workflow run tuesday-predictions.yml`.
- **Is production serving it?** `curl -s https://golf-app-a3yw.onrender.com/api/predictions?limit=1`
  names the event it serves; `/api/weather`, `/api/results/earnings?tournament_id=R…`
  say `saved_at` / `earnings_estimated` honestly.
- **Model files.** `python3 scripts/validation/model_manifest.py` lists what
  this machine has vs `data/models/manifest.json`. After a deliberate retrain:
  `--write`, and run the stats-reviewer before quoting any metric.

## Working locally

- Repo: `~/Developer/golf_data` (never iCloud). Python:
  `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`.
- API: `./restart_api.sh` (port 8000). Site: `cd web && npm run dev`, or the
  `golf-web-prodapi` launch config to run the site against production's API.
- Tests: `cd web && npm test && npm run build`; `python3 api/test_routes.py`;
  the Python gate tests listed in `tuesday-predictions.yml`. The post-edit
  hook runs the fast ones automatically.
- Deploy = `git pull --rebase --autostash && git push`. Never `vercel deploy`.
