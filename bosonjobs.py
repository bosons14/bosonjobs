#!/usr/bin/env python3
"""BosonJobs: one private feed of remote jobs you can actually take from India.

Pulls public job feeds, removes duplicates, checks whether each role is open to
someone based in India, ranks it against profile.json, and serves a local page
with an application tracker. Python 3.9+ standard library only.

    python3 bosonjobs.py fetch          # refresh the feed
    python3 bosonjobs.py serve          # browse at http://127.0.0.1:8765
    python3 bosonjobs.py top -n 20      # best matches in the terminal
    python3 bosonjobs.py show <id>      # full posting (used for tailoring)
    python3 bosonjobs.py track <id> applied --note "referred by X"
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import datetime as dt
import email.utils
import hashlib
import html
import http.server
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get("BOSONJOBS_HOME", Path.home() / ".bosonjobs"))
USER_AGENT = "bosonjobs/0.1 (personal job search tool)"
CACHE_SECONDS = 6 * 3600  # Boards refresh daily at most; Remotive asks for few calls.
STATUSES = ("new", "saved", "tailoring", "applied", "interview", "offer", "rejected", "skipped")
BOARD_HOME = {
    "himalayas": "https://himalayas.app",
    "remotive": "https://remotive.com",
    "remoteok": "https://remoteok.com",
    "jobicy": "https://jobicy.com",
    "weworkremotely": "https://weworkremotely.com",
    "workingnomads": "https://www.workingnomads.com",
}
# When the same job appears twice, the first source here supplies the Apply link.
PRIORITY = ("greenhouse", "lever", "ashby", "himalayas", "weworkremotely", "remotive",
            "jobicy", "remoteok", "workingnomads")


# ---------------------------------------------------------------- small helpers
def strip_html(text) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", str(text or ""))
    text = re.sub(r"(?i)<(br|/p|/div|/li|/h\d)\b[^>]*>", "\n", text)
    text = re.sub(r"(?i)<li\b[^>]*>", "- ", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(text)))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()[:12000]


def safe_url(url) -> str:
    url = str(url or "").strip()
    return url if urllib.parse.urlsplit(url).scheme in ("http", "https") else ""


def to_epoch(value) -> int:
    """Accepts epoch seconds/millis, ISO 8601, or RFC 2822. Returns 0 if unknown."""
    if isinstance(value, (int, float)):
        return int(value / 1000 if value > 10**11 else value)
    text = str(value or "").strip()
    if not text:
        return 0
    if text.isdigit():
        return to_epoch(int(text))
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp())


def money(low, high, currency="USD", period="") -> str:
    if not low and not high:
        return ""
    fmt = lambda v: f"{float(v):,.0f}"
    amount = f"{fmt(low)}-{fmt(high)}" if low and high else fmt(low or high)
    suffix = f"/{period}" if period and period != "annual" else ""
    return f"{currency or 'USD'} {amount}{suffix}"


def http_get(url: str) -> bytes:
    """GET with a disk cache, so repeated runs stay polite to free feeds."""
    cache = HOME / "cache" / (hashlib.sha1(url.encode()).hexdigest() + ".raw")
    if not FORCE.is_set() and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_SECONDS:
        return cache.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return body


FORCE = threading.Event()


def get_json(url: str):
    return json.loads(http_get(url).decode("utf-8", "replace"))


def job(source, title, company, location, url, apply_url=None, posted=0, text="", tags=(),
        salary="", kind="", restrictions=None, timezones=None, expires=0):
    return {
        "source": source, "title": strip_html(title), "company": strip_html(company),
        "location": strip_html(location), "url": safe_url(url),
        "apply_url": safe_url(apply_url) or safe_url(url), "posted": to_epoch(posted),
        "text": strip_html(text), "tags": [strip_html(t) for t in (tags or []) if t],
        "salary": salary, "kind": strip_html(kind), "restrictions": restrictions,
        "timezones": timezones, "expires": to_epoch(expires),
    }


# ---------------------------------------------------------------------- sources
def from_himalayas(profile):
    """Uses Himalayas' country search, which keeps jobs open to India or worldwide."""
    out = []
    for query in profile["queries"]:
        for page in (1, 2):
            params = urllib.parse.urlencode(
                {"q": query, "country": "IN", "sort": "recent", "page": page})
            batch = get_json(f"https://himalayas.app/jobs/api/search?{params}").get("jobs") or []
            for r in batch:
                places = [p.get("name", "") if isinstance(p, dict) else str(p)
                          for p in r.get("locationRestrictions") or []]
                out.append(job(
                    "himalayas", r.get("title"), r.get("companyName"), ", ".join(places),
                    r.get("guid") if safe_url(r.get("guid")) else r.get("applicationLink"),
                    r.get("applicationLink"), r.get("pubDate"),
                    r.get("description") or r.get("excerpt"), r.get("categories"),
                    money(r.get("minSalary"), r.get("maxSalary"), r.get("currency"), r.get("salaryPeriod")),
                    r.get("employmentType"), places, r.get("timezoneRestrictions"), r.get("expiryDate")))
            if not batch:
                break
            time.sleep(1)
    return out


def from_remotive(_):
    return [job("remotive", r.get("title"), r.get("company_name"),
                r.get("candidate_required_location"), r.get("url"), None,
                r.get("publication_date"), r.get("description"),
                (r.get("tags") or []) + [r.get("category")], str(r.get("salary") or ""),
                r.get("job_type"))
            for r in get_json("https://remotive.com/api/remote-jobs").get("jobs", [])]


def from_remoteok(_):
    rows = get_json("https://remoteok.com/api")
    return [job("remoteok", r.get("position"), r.get("company"), r.get("location"), r.get("url"),
                r.get("apply_url"), r.get("date") or r.get("epoch"), r.get("description"),
                r.get("tags"), money(r.get("salary_min"), r.get("salary_max")))
            for r in rows if isinstance(r, dict) and r.get("position")]


def from_jobicy(_):
    data = get_json("https://jobicy.com/api/v2/remote-jobs?count=100")
    return [job("jobicy", r.get("jobTitle"), r.get("companyName"), r.get("jobGeo"), r.get("url"),
                None, r.get("pubDate"), r.get("jobDescription") or r.get("jobExcerpt"),
                r.get("jobIndustry"),
                money(r.get("annualSalaryMin"), r.get("annualSalaryMax"), r.get("salaryCurrency")),
                ", ".join(r.get("jobType") or []) if isinstance(r.get("jobType"), list) else r.get("jobType"))
            for r in data.get("jobs", [])]


def from_weworkremotely(_):
    root = ET.fromstring(http_get("https://weworkremotely.com/remote-jobs.rss"))
    out = []
    for item in root.iter("item"):
        company, _, title = (item.findtext("title") or "").partition(":")
        out.append(job("weworkremotely", title or company, company if title else "",
                       item.findtext("region"), item.findtext("link"), None,
                       item.findtext("pubDate"), item.findtext("description"),
                       [item.findtext("category")], "", item.findtext("type")))
    return out


def from_workingnomads(_):
    return [job("workingnomads", r.get("title"), r.get("company_name"), r.get("location"),
                r.get("url"), None, r.get("pub_date"), r.get("description"),
                [r.get("category_name")] + str(r.get("tags") or "").split(","))
            for r in get_json("https://www.workingnomads.com/api/exposed_jobs/")]


def from_greenhouse(slug):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    return [job("greenhouse", r.get("title"), slug.title(), (r.get("location") or {}).get("name"),
                r.get("absolute_url"), None, r.get("updated_at"), r.get("content"))
            for r in data.get("jobs", [])
            if "remote" in str((r.get("location") or {}).get("name", "")).lower()]


def from_lever(slug):
    return [job("lever", r.get("text"), slug.title(), (r.get("categories") or {}).get("location"),
                r.get("hostedUrl"), r.get("applyUrl"), r.get("createdAt"), r.get("descriptionPlain"),
                [(r.get("categories") or {}).get("team")], "",
                (r.get("categories") or {}).get("commitment"))
            for r in get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
            if r.get("workplaceType") == "remote"
            or "remote" in str((r.get("categories") or {}).get("location", "")).lower()]


def from_ashby(slug):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    return [job("ashby", r.get("title"), slug.title(), r.get("location"), r.get("jobUrl"), r.get("applyUrl"),
                r.get("publishedAt"), r.get("descriptionPlain") or r.get("descriptionHtml"),
                [r.get("department")], "", r.get("employmentType"))
            for r in data.get("jobs", []) if r.get("isRemote")]


BOARDS = {"himalayas": from_himalayas, "remotive": from_remotive, "remoteok": from_remoteok,
          "jobicy": from_jobicy, "weworkremotely": from_weworkremotely,
          "workingnomads": from_workingnomads}
COMPANY_SOURCES = {"greenhouse": from_greenhouse, "lever": from_lever, "ashby": from_ashby}


# ------------------------------------------------------------ India eligibility
OPEN_WORDS = re.compile(r"\b(worldwide|global|globally|international)\b", re.I)
ANYWHERE = re.compile(r"\b(anywhere|remote)\b", re.I)
INDIA_WORDS = re.compile(r"\b(india|bharat|apac|asia|asia[- ]pacific|south asia)\b", re.I)
ELSEWHERE = re.compile(
    r"\bUSA?\b|\bU\.S\.|\bUK\b|\bEU\b|\bEMEA\b|\bLATAM\b|\bNA\b|"
    r"\b(united states|america|americas|canada|united kingdom|england|europe|european|germany|"
    r"france|spain|portugal|poland|netherlands|ireland|italy|sweden|australia|new zealand|"
    r"brazil|mexico|argentina|colombia|philippines|japan|singapore|south africa|nigeria|israel)\b",
    re.I)
AUTH_FLAGS = re.compile(
    r"(authori[sz]ed to work in (the )?(us|u\.s\.|united states|uk|eu|canada)|"
    r"(must|need to) (be|reside|live)\s+(based |located )?in (the )?(us|u\.s\.|united states|uk|europe|eu|canada)|"
    r"\b(us|u\.s\.) citizen|security clearance|green card|"
    r"no visa sponsorship|\bw-?2\b only|\bonly in the (us|united states)\b)", re.I)


def eligibility(j) -> tuple:
    """Returns (status, note); status is india | worldwide | unclear | excluded."""
    restrictions = j.get("restrictions")
    timezones = j.get("timezones") or []
    if restrictions is not None:  # Himalayas gives structured fields; follow its documented rule.
        names = " ".join(restrictions)
        if restrictions and not INDIA_WORDS.search(names) and not (OPEN_WORDS.search(names) or ANYWHERE.search(names)):
            return "excluded", f"Limited to {names}"
        if timezones and 5.5 not in [float(z) for z in timezones if _is_number(z)]:
            return "excluded", "Timezone requirement excludes IST"
        status = "india" if INDIA_WORDS.search(names) else "worldwide"
    else:
        where = j.get("location", "")
        if INDIA_WORDS.search(where):
            status = "india"
        elif OPEN_WORDS.search(where):
            status = "worldwide"
        elif ELSEWHERE.search(where):
            return "excluded", f"Limited to {where}"
        elif not where or ANYWHERE.search(where):
            return "unclear", "Says remote, but names no country"
        else:
            return "unclear", f"Location is '{where}'"
    if status != "india" and AUTH_FLAGS.search(j.get("text", "")):
        return "unclear", "Text suggests a work-authorisation limit"
    return status, ""


def _is_number(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------- scoring + dedupe
def term_regex(term: str):
    flags = 0 if term.isupper() else re.I  # All-caps terms such as EDA stay case-sensitive.
    return re.compile(rf"(?<![\w+#]){re.escape(term)}(?![\w+#])", flags)


def score(j, profile, compiled) -> tuple:
    title = j["title"]
    if compiled["exclude"].search(title):
        return 0, []
    title_hits = sorted(((w, t) for t, (rx, w) in compiled["title"].items() if rx.search(title)), reverse=True)
    points = sum(w for w, _ in title_hits[:2])
    body = title + "\n" + " ".join(j["tags"]) + "\n" + j["text"]
    skills = [(w, t) for t, (rx, w) in compiled["skills"].items() if rx.search(body)]
    points += min(sum(w for w, _ in skills), profile.get("skills_cap", 35))
    if title_hits and compiled["senior"].search(title):
        points += 12
    if not title_hits:
        points = min(points, 25)  # Skills alone can't push an off-target title onto the list.
    return min(points, 100), [t for _, t in title_hits[:2]] + [t for _, t in sorted(skills, reverse=True)[:6]]


def compile_profile(profile):
    return {
        "title": {t: (term_regex(t), w) for t, w in profile["title_terms"].items()},
        "skills": {t: (term_regex(t), w) for t, w in profile["skill_terms"].items()},
        "senior": re.compile("|".join(profile["senior_words"]), re.I),
        "exclude": re.compile("|".join(rf"\b{re.escape(w)}\b" for w in profile["exclude_titles"]), re.I),
    }


def dedupe_key(j) -> str:
    company = re.sub(r"\b(inc|llc|ltd|limited|pvt|private|gmbh|corp|corporation|co)\b\.?", "", j["company"].lower())
    title = re.sub(r"\(.*?\)|\bremote\b|\b100%\b", "", j["title"].lower())
    return re.sub(r"[^a-z0-9]", "", company) + "|" + re.sub(r"[^a-z0-9]", "", title)


def merge(rows):
    """Collapses one job listed on several boards; keeps a link to each so all are credited."""
    rank = {name: i for i, name in enumerate(PRIORITY)}
    merged = {}
    for j in sorted(rows, key=lambda r: rank.get(r["source"], 99)):
        key = dedupe_key(j)
        if key in merged:
            first = merged[key]
            first["listings"].append({"source": j["source"], "url": j["url"]})
            first["salary"] = first["salary"] or j["salary"]
            first["posted"] = max(first["posted"], j["posted"])
            if len(j["text"]) > len(first["text"]):
                first["text"] = j["text"]
        else:
            j["id"] = hashlib.sha1(key.encode()).hexdigest()[:10]
            j["listings"] = [{"source": j["source"], "url": j["url"]}]
            merged[key] = j
    return list(merged.values())


# ------------------------------------------------------------------ persistence
def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def load_profile():
    target = HOME / "profile.json"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "profile.json", target)
    return json.loads(target.read_text(encoding="utf-8"))


# --------------------------------------------------------------------- pipeline
def collect(profile):
    tasks = {name: (fn, profile) for name, fn in BOARDS.items() if name not in profile.get("disabled", [])}
    for kind, fn in COMPANY_SOURCES.items():
        for slug in profile.get("companies", {}).get(kind, []):
            tasks[f"{kind}:{slug}"] = (fn, slug)
    rows, report = [], {}
    with futures.ThreadPoolExecutor(max_workers=8) as pool:
        running = {pool.submit(fn, arg): name for name, (fn, arg) in tasks.items()}
        for done in futures.as_completed(running):
            name = running[done]
            try:
                found = done.result()
                rows += found
                report[name] = {"count": len(found)}
            except (urllib.error.URLError, ValueError, KeyError, TypeError, AttributeError,
                    ET.ParseError, OSError) as err:
                report[name] = {"count": 0, "error": f"{type(err).__name__}: {err}"[:200]}
    return rows, report


def build(rows, report, profile, now=None):
    now = now or int(time.time())
    compiled = compile_profile(profile)
    seen = load(HOME / "seen.json", {})
    max_age = profile.get("max_age_days", 45) * 86400
    kept, dropped = [], {"expired_or_old": 0, "not_open_to_india": 0, "low_match": 0}
    for j in merge([r for r in rows if r["title"] and r["apply_url"]]):
        if (j["expires"] and j["expires"] < now) or (j["posted"] and now - j["posted"] > max_age):
            dropped["expired_or_old"] += 1
            continue
        j["eligibility"], j["eligibility_note"] = eligibility(j)
        if j["eligibility"] == "excluded":
            dropped["not_open_to_india"] += 1
            continue
        j["score"], j["why"] = score(j, profile, compiled)
        if j["score"] < profile.get("min_score", 35):
            dropped["low_match"] += 1
            continue
        seen.setdefault(j["id"], now)
        j["first_seen"] = seen[j["id"]]
        for field in ("restrictions", "timezones", "expires", "source"):
            j.pop(field)
        kept.append(j)
    kept.sort(key=lambda j: (j["score"], j["posted"]), reverse=True)
    save(HOME / "seen.json", seen)
    return {"generated": now, "sources": report, "dropped": dropped, "jobs": kept}


def cmd_fetch(args):
    if args.force:
        FORCE.set()
    profile = load_profile()
    rows, report = collect(profile)
    for name, info in sorted(report.items()):
        print(f"  {name:32} {info.get('error') or str(info['count']) + ' jobs'}")
    if not rows:
        print("Every source failed, so the existing feed was left as it is.", file=sys.stderr)
        return 1
    data = build(rows, report, profile)
    save(HOME / "jobs.json", data)
    print(f"\n{len(data['jobs'])} matching jobs. Dropped: {data['dropped']}")
    return 0


def read_data():
    return load(HOME / "jobs.json", {"generated": 0, "sources": {}, "dropped": {}, "jobs": []})


def status_of(tracker, job_id):
    return tracker.get(job_id, {}).get("status", "new")


def cmd_top(args):
    data, tracker = read_data(), load(HOME / "tracker.json", {})
    rows = [j for j in data["jobs"] if status_of(tracker, j["id"]) in ("new", "saved")]
    if args.only_clear:
        rows = [j for j in rows if j["eligibility"] != "unclear"]
    rows = rows[: args.n]
    if args.json:
        print(json.dumps([{k: v for k, v in j.items() if k != "text"} for j in rows], ensure_ascii=False, indent=1))
        return 0
    for j in rows:
        print(f"{j['id']}  {j['score']:3}  {j['eligibility']:9}  {j['title']} @ {j['company']}")
    if not rows:
        print("Nothing to show. Run: python3 bosonjobs.py fetch")
    return 0


def cmd_show(args):
    for j in read_data()["jobs"]:
        if j["id"] == args.id:
            print(json.dumps(j, ensure_ascii=False, indent=1))
            return 0
    print(f"No job with id {args.id}", file=sys.stderr)
    return 1


TRACK_LOCK = threading.Lock()


def set_status(job_id, status, note=None, job=None):
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    with TRACK_LOCK:
        tracker = load(HOME / "tracker.json", {})
        entry = tracker.setdefault(job_id, {"history": []})
        entry["status"] = status
        entry["history"].append({"status": status, "at": int(time.time())})
        if note is not None:
            entry["note"] = note
        if job:  # Keep the essentials, so the record outlives the listing.
            entry.update({k: job[k] for k in ("title", "company", "apply_url")})
        save(HOME / "tracker.json", tracker)
    return entry


def find_job(job_id):
    return next((j for j in read_data()["jobs"] if j["id"] == job_id), None)


def cmd_track(args):
    entry = set_status(args.id, args.status, args.note, find_job(args.id))
    print(f"{args.id}: {entry['status']}")
    return 0


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "bosonjobs"

    def _send(self, body: bytes, kind="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):  # Blocks DNS-rebinding pages from reading the tracker.
        host = self.headers.get("Host", "").rsplit(":", 1)[0]
        if host in ("127.0.0.1", "localhost"):
            return True
        self._send(b'{"error":"forbidden"}', code=403)
        return False

    def do_GET(self):
        if not self._host_ok():
            return
        path = urllib.parse.urlsplit(self.path).path
        if path == "/":
            self._send((ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/data":
            data = read_data()
            data["tracker"] = load(HOME / "tracker.json", {})
            data["statuses"] = STATUSES
            data["board_home"] = BOARD_HOME
            self._send(json.dumps(data, ensure_ascii=False).encode())
        else:
            self._send(b'{"error":"not found"}', code=404)

    def do_POST(self):
        if not self._host_ok():
            return
        # A JSON content type forces a CORS preflight, which this server never grants.
        if self.path != "/api/track" or "application/json" not in self.headers.get("Content-Type", ""):
            return self._send(b'{"error":"bad request"}', code=400)
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 20000)
            body = json.loads(self.rfile.read(length))
            entry = set_status(str(body["id"]), body["status"], body.get("note"), find_job(str(body["id"])))
        except (ValueError, KeyError, TypeError) as err:
            return self._send(json.dumps({"error": str(err)}).encode(), code=400)
        self._send(json.dumps(entry).encode())

    def log_message(self, *_):
        pass


def cmd_serve(args):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"BosonJobs at http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private remote-job feed, filtered for India.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fetch", help="refresh the feed")
    p.add_argument("--force", action="store_true", help="ignore the 6-hour cache")
    p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("serve", help="browse and track in your browser")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("top", help="best untouched matches")
    p.add_argument("-n", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.add_argument("--only-clear", action="store_true", help="hide roles with unclear eligibility")
    p.set_defaults(fn=cmd_top)
    p = sub.add_parser("show", help="print one full posting as JSON")
    p.add_argument("id")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("track", help="update an application's status")
    p.add_argument("id")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_track)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
