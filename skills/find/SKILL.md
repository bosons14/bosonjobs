---
name: find
description: Refresh and review the user's remote job feed. Use for "find remote jobs", "what's new on BosonJobs", "show my best matches", or /bosonjobs:find.
---

# Find remote jobs

Run the tool with `python3 "${CLAUDE_PLUGIN_ROOT}/bosonjobs.py"`.

1. Run `fetch`. Report any feed that failed, by name and with its error. Never present a partial feed as complete.
2. Run `top -n 15 --json`.
3. For the strongest candidates, run `show <id>` and read the posting. The match number is keyword-based, so judge the fit yourself against `~/.bosonjobs/cv.md`.
4. Reply with a short ranked list: role, company, why it fits, what is missing, and the job id.
5. For any role marked `unclear`, say what to confirm. Read the posting for location or work-authorisation limits and treat "remote" alone as unproven.
6. Offer to start an application for the best one with the apply skill. To open the browsing page, run `serve` and give the user http://127.0.0.1:8765.

If `~/.bosonjobs/cv.md` is missing, ask the user for their CV and save it there as Markdown.
To change what ranks highly, edit `~/.bosonjobs/profile.json`.
