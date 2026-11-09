"""Runs the whole pipeline offline, against sample payloads shaped like each feed."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bosonjobs as bj  # noqa: E402

NOW = int(time.time())
ISO = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(NOW - 3 * 86400))
LONG = "Build RAG systems with PyTorch and CUDA on GPU clusters using Python and a vector database. "


def himalayas(job_rows):
    return json.dumps({"jobs": job_rows, "totalCount": len(job_rows)}).encode()


H_ROWS = [
    {"title": "Senior LLM Inference Engineer", "companyName": "Acme AI", "locationRestrictions": ["India"],
     "timezoneRestrictions": [5.5], "categories": ["Engineering"], "minSalary": 90000, "maxSalary": 140000,
     "currency": "USD", "salaryPeriod": "annual", "description": "<p>" + LONG + "</p>", "pubDate": NOW - 86400,
     "expiryDate": NOW + 30 * 86400, "applicationLink": "https://himalayas.app/acme/apply",
     "guid": "https://himalayas.app/companies/acme/jobs/llm", "employmentType": "Full Time"},
    {"title": "Generative AI Architect", "companyName": "Globex", "locationRestrictions": [],
     "timezoneRestrictions": [], "description": LONG, "pubDate": NOW - 86400, "expiryDate": NOW + 86400,
     "applicationLink": "https://himalayas.app/globex/apply", "guid": "g1"},
    {"title": "GPU Engineer", "companyName": "Expired Co", "locationRestrictions": ["India"],
     "description": LONG, "pubDate": NOW - 86400, "expiryDate": NOW - 60,
     "applicationLink": "https://himalayas.app/exp/apply", "guid": "g2"},
    {"title": "LLM Engineer", "companyName": "Timezone Co", "locationRestrictions": ["India"],
     "timezoneRestrictions": [-5, -8], "description": LONG, "pubDate": NOW, "expiryDate": NOW + 86400,
     "applicationLink": "https://himalayas.app/tz/apply", "guid": "g3"},
]
REMOTIVE = {"0-legal": "x", "jobs": [
    {"title": "Generative AI Architect (Remote)", "company_name": "Globex Inc", "candidate_required_location": "Worldwide",
     "url": "https://remotive.com/j/1", "publication_date": ISO, "description": LONG, "tags": ["llm"],
     "category": "AI", "salary": "$120k", "job_type": "full_time"},
    {"title": "Machine Learning Engineer", "company_name": "US Only Co", "candidate_required_location": "USA",
     "url": "https://remotive.com/j/2", "publication_date": ISO, "description": LONG},
    {"title": "AI Engineer", "company_name": "Hidden Limit", "candidate_required_location": "Worldwide",
     "url": "https://remotive.com/j/3", "publication_date": ISO,
     "description": LONG + "You must be authorized to work in the United States."},
    {"title": "LLM Engineer", "company_name": "Evil", "candidate_required_location": "Worldwide",
     "url": "javascript:alert(1)", "publication_date": ISO, "description": LONG},
]}
REMOTEOK = [{"legal": "notice"}, {"position": "EDA Software Engineer", "company": "Silicon Co", "location": "Remote",
            "url": "https://remoteok.com/1", "apply_url": "https://silicon.example/apply", "date": ISO,
            "description": LONG + "verilog", "tags": ["c++"], "salary_min": 100000, "salary_max": 150000}]
JOBICY = {"jobs": [{"jobTitle": "AI Engineer Intern", "companyName": "Skip", "jobGeo": "Anywhere", "url": "https://jobicy.com/1",
                    "pubDate": ISO, "jobDescription": LONG, "jobIndustry": ["Dev"], "jobType": ["full-time"]},
                   {"jobTitle": "Agentic AI Lead", "companyName": "Jobi", "jobGeo": "APAC", "url": "https://jobicy.com/2",
                    "pubDate": ISO, "jobDescription": LONG, "jobIndustry": ["Dev"], "jobType": ["full-time"]}]}
WWR = f"""<?xml version="1.0"?><rss><channel><item><title>Wave: Principal ML Engineer</title>
<region>Anywhere in the World</region><link>https://weworkremotely.com/1</link>
<pubDate>{time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime(NOW - 86400))}</pubDate>
<description>&lt;p&gt;{LONG}&lt;/p&gt;</description><category>Programming</category><type>Full-Time</type></item>
</channel></rss>""".encode()
NOMADS = [{"title": "Barista", "company_name": "Cafe", "location": "Anywhere", "url": "https://workingnomads.com/1",
           "pub_date": ISO, "description": "Coffee", "category_name": "Food", "tags": "coffee"}]
GREENHOUSE = {"jobs": [{"title": "AI Engineer", "absolute_url": "https://gh.example/1", "updated_at": ISO,
                        "location": {"name": "Remote - India"}, "content": "&lt;p&gt;" + LONG + "&lt;/p&gt;"},
                       {"title": "AI Engineer SF", "absolute_url": "https://gh.example/2", "updated_at": ISO,
                        "location": {"name": "San Francisco"}, "content": LONG}]}
LEVER = [{"text": "LLM Engineer", "hostedUrl": "https://lever.example/1", "applyUrl": "https://lever.example/1/apply",
          "createdAt": (NOW - 86400) * 1000, "descriptionPlain": LONG, "workplaceType": "remote",
          "categories": {"location": "Global", "team": "AI", "commitment": "Full-time"}}]
ASHBY = {"jobs": [{"title": "Applied AI Engineer", "location": "Asia", "isRemote": True, "jobUrl": "https://ashby.example/1",
                   "applyUrl": "https://ashby.example/1/apply", "publishedAt": ISO, "descriptionPlain": LONG}]}


def fake_get(url):
    routes = [("himalayas.app/jobs/api/search", None), ("remotive.com", REMOTIVE), ("remoteok.com", REMOTEOK),
              ("jobicy.com", JOBICY), ("weworkremotely", WWR), ("greenhouse.io", GREENHOUSE),
              ("lever.co", LEVER), ("ashbyhq", ASHBY)]
    if "workingnomads" in url:
        raise urllib.error.URLError("feed down")
    for needle, payload in routes:
        if needle in url:
            if payload is None:
                return himalayas(H_ROWS if "page=1" in url else [])
            return payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    raise AssertionError(url)


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = Path(os.environ.get("BOSONJOBS_TEST_HOME") or tempfile.mkdtemp())
        bj.HOME = cls.home
        bj.http_get = fake_get
        bj.time.sleep = lambda _: None
        profile = bj.load_profile()
        profile["companies"] = {"greenhouse": ["acme"], "lever": ["acme"], "ashby": ["acme"]}
        profile["queries"] = ["llm"]
        (cls.home / "profile.json").write_text(json.dumps(profile))
        assert bj.main(["fetch"]) == 0
        cls.data = bj.read_data()
        cls.by_title = {j["title"]: j for j in cls.data["jobs"]}

    def test_every_source_parses(self):
        for name, info in self.data["sources"].items():
            if name != "workingnomads":
                self.assertGreater(info["count"], 0, name)

    def test_failed_feed_is_reported_not_fatal(self):
        self.assertIn("URLError", self.data["sources"]["workingnomads"]["error"])

    def test_duplicates_merge_and_keep_every_credit(self):
        rows = [j for j in self.data["jobs"] if j["company"].startswith("Globex")]
        self.assertEqual(len(rows), 1)
        self.assertEqual({l["source"] for l in rows[0]["listings"]}, {"himalayas", "remotive"})
        self.assertEqual(rows[0]["apply_url"], "https://himalayas.app/globex/apply")

    def test_eligibility(self):
        self.assertEqual(self.by_title["Senior LLM Inference Engineer"]["eligibility"], "india")
        self.assertEqual(self.by_title["Agentic AI Lead"]["eligibility"], "india")
        self.assertEqual(self.by_title["EDA Software Engineer"]["eligibility"], "unclear")
        titles = [j["company"] for j in self.data["jobs"]]
        self.assertNotIn("US Only Co", titles)
        self.assertNotIn("Timezone Co", titles)

    def test_hidden_work_authorisation_limit_is_flagged(self):
        job = next(j for j in self.data["jobs"] if j["company"] == "Hidden Limit")
        self.assertEqual(job["eligibility"], "unclear")

    def test_expired_and_off_target_are_gone(self):
        companies = [j["company"] for j in self.data["jobs"]]
        for bad in ("Expired Co", "Skip", "Cafe"):
            self.assertNotIn(bad, companies)

    def test_only_web_urls_survive(self):
        self.assertNotIn("Evil", [j["company"] for j in self.data["jobs"]])
        for j in self.data["jobs"]:
            self.assertTrue(j["apply_url"].startswith("http"))

    def test_html_is_stripped(self):
        self.assertNotIn("<p>", self.by_title["Principal ML Engineer"]["text"])
        self.assertNotIn("<p>", self.by_title["AI Engineer"]["text"])

    def test_ats_apply_link_preserved(self):
        self.assertEqual(self.by_title["EDA Software Engineer"]["apply_url"], "https://silicon.example/apply")
        self.assertEqual(self.by_title["LLM Engineer"]["apply_url"], "https://lever.example/1/apply")

    def test_short_terms_need_word_boundaries(self):
        self.assertFalse(bj.term_regex("rag").search("drag and storage"))
        self.assertFalse(bj.term_regex("EDA").search("eda notebooks"))
        self.assertTrue(bj.term_regex("c++").search("Modern C++ role"))

    def test_location_rules(self):
        cases = {"Anywhere in the US": "excluded", "Remote - EMEA": "excluded", "Worldwide": "worldwide",
                 "India, Singapore": "india", "Remote": "unclear", "": "unclear", "Atlantis": "unclear"}
        for where, want in cases.items():
            self.assertEqual(bj.eligibility({"location": where, "text": ""})[0], want, where)

    def test_all_feeds_failing_keeps_old_feed(self):
        before = (self.home / "jobs.json").read_bytes()
        def down(url):
            raise urllib.error.URLError("down")
        bj.http_get = down
        try:
            self.assertEqual(bj.main(["fetch"]), 1)
        finally:
            bj.http_get = fake_get
        self.assertEqual((self.home / "jobs.json").read_bytes(), before)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Pipeline.setUpClass()
        cls.srv = bj.http.server.ThreadingHTTPServer(("127.0.0.1", 0), bj.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, path, body=None, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, headers=headers or {})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=5) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def test_page_and_data(self):
        self.assertEqual(self.call("/")[0], 200)
        self.assertGreater(len(json.loads(self.call("/api/data")[1])["jobs"]), 3)

    def test_tracking_persists(self):
        job_id = bj.read_data()["jobs"][0]["id"]
        code, _ = self.call("/api/track", json.dumps({"id": job_id, "status": "applied"}).encode(),
                            {"Content-Type": "application/json"})
        self.assertEqual(code, 200)
        saved = json.loads((bj.HOME / "tracker.json").read_text())[job_id]
        self.assertEqual(saved["status"], "applied")
        self.assertIn("title", saved)

    def test_rejects_cross_site_shapes(self):
        body = json.dumps({"id": "x", "status": "applied"}).encode()
        self.assertEqual(self.call("/api/track", body, {"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.call("/api/data", headers={"Host": "evil.example"})[0], 403)

    def test_rejects_unknown_status(self):
        body = json.dumps({"id": "x", "status": "hacked"}).encode()
        self.assertEqual(self.call("/api/track", body, {"Content-Type": "application/json"})[0], 400)


if __name__ == "__main__":
    unittest.main()
