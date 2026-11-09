# BosonJobs

A private feed of remote jobs you can take from India. It pulls public job feeds into one list, removes duplicates, drops roles limited to other countries, ranks the rest against your profile, and tracks your applications. With Claude Code it also prepares a tailored application for each job.

## Run it

Needs Python 3.9 or newer. Nothing to install.

```bash
python3 bosonjobs.py fetch   # refresh the feed
python3 bosonjobs.py serve   # browse at http://127.0.0.1:8765
```

Your data stays in `~/.bosonjobs/`: `profile.json` (what ranks highly), `jobs.json`, `tracker.json`, and `cv.md` (add your CV here as Markdown).

## Use it with Claude Code

```
/plugin marketplace add bosons14/bosonjobs
/plugin install bosonjobs@bosonjobs
```

- `/bosonjobs:find` refreshes the feed and reviews your best matches against your CV.
- `/bosonjobs:apply <job id>` checks one job, drafts a tailored CV and cover note, and submits only when you approve.

## Sources

| Source | Access |
|---|---|
| [Himalayas](https://himalayas.app) | JSON search, country filter |
| [Remotive](https://remotive.com) | JSON feed |
| [Remote OK](https://remoteok.com) | JSON feed |
| [Jobicy](https://jobicy.com) | JSON feed |
| [We Work Remotely](https://weworkremotely.com) | RSS |
| [Working Nomads](https://www.workingnomads.com) | JSON feed |
| Greenhouse, Lever and Ashby company boards | Public job-board APIs; choose companies in `profile.json` |

A failed feed is reported and skipped, and never stops the others. Responses are cached for six hours; use `fetch --force` to bypass that.

LinkedIn, Indeed and Naukri aren't included because they offer no open feed for this. Search those directly.

## How "open to India" works

| Label | Meaning |
|---|---|
| Names India or Asia | The listing includes India or an Asian region |
| Worldwide | Stated as worldwide, with no conflicting text found |
| Check the posting | Says only "remote", or the text hints at a work-authorisation limit |
| (hidden) | Limited to other countries, or a timezone requirement excludes IST |

This is a heuristic on listing text. Confirm eligibility before applying.

## Keep it private

Run this for your own search. Before publishing the feed as a public site, read each board's terms. Remotive asks that its jobs are not resubmitted to other job sites, and Himalayas and Remote OK require credit and links back and forbid passing jobs on to other boards or aggregators. The code in this repo is fine to share; the fetched listings are the part to be careful with.

## Test

```bash
python3 -m unittest discover -s tests
```
