import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

from biddesk import county_rss, documents, job_walk, leads, planning, review
from biddesk.db import Project
from run_biddesk import select_workspace


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = Project(select_workspace(self.root / "dev"))
        self.addCleanup(self.project.close)

    def lead(self):
        return leads.add_lead(self.project, "fixture", "Fictional Agency", "DEMO-001",
                              "Fictional pump service", "Test Town", "")

    def test_launcher_rejects_unrelated_and_checkout_folders(self):
        old = self.root / "other"
        old.mkdir()
        sentinel = old / "biddesk.db"
        sentinel.write_bytes(b"do not touch")
        with self.assertRaises(ValueError):
            select_workspace(old)
        self.assertEqual(sentinel.read_bytes(), b"do not touch")
        with self.assertRaises(ValueError):
            select_workspace(Path(__file__).resolve().parent)
        self.assertEqual(select_workspace(self.root / "dev"), self.project.root)

    def test_county_fixture_selects_without_automatic_go(self):
        u = county_rss.ORIGIN_DETAIL + "?BidNumber=RFB-MOCK-001"
        xml = f"""<rss><channel><item><title>RFB-MOCK-001 - fictional test</title>
            <link>{escape(u)}</link><bidDepartment>Test department</bidDepartment>
            <closeDate>12/8/2030 12:00 PM</closeDate></item></channel></rss>"""
        notice, = county_rss.parse_open(xml.encode()).notices
        self.assertEqual((notice.key, notice.closing), ("RFB-MOCK-001", "2030-12-08 12:00 PM PT"))
        self.assertEqual(self.project.q("SELECT * FROM leads"), [])
        self.assertEqual(county_rss.import_selected(self.project, [notice]), (1, 0))
        self.assertEqual(county_rss.import_selected(self.project, [notice]), (0, 1))
        row = self.project.one("SELECT decision,stage FROM leads")
        self.assertEqual(tuple(row), ("NEW", "lead"))
        self.assertEqual(planning.calendar_events(self.project), [])

    def test_job_walk_keeps_unknown_cutoff_and_verified_bid_due(self):
        lid = self.lead()
        old = review.add_manual_finding(self.project, lid, "bid_due", "2030-12-08 12:00 PT",
                                        None, None, "Fictional source")
        d = dict(attendance="Mandatory", walk_date="2030-12-02", walk_time="10:00", zone="Pacific (PT)",
                 address="Fictional site, 1 Test Street", rsvp="Required", waiver="Required",
                 cutoff_date="2030-12-01", cutoff_time="", cutoff_zone="Not stated",
                 evidence="Fictional text.", bid_due_date="2030-12-09", bid_due_time="14:00",
                 bid_due_zone="Pacific (PT)")
        item = job_walk.save(self.project, lid, d)
        value = job_walk.read(self.project, item)
        self.assertIn("2030-12-01 (time not stated)", job_walk.summary(value))
        self.assertIn("2030-12-09 14:00 PT", job_walk.summary(value))
        self.assertEqual([(x["id"],x["value"]) for x in review.applicable(self.project, lid, "bid_due", True)],
                         [(old, "2030-12-08 12:00 PT")])

    def test_revised_due_is_not_automatically_verified(self):
        lid = self.lead()
        leads.set_decision(self.project,lid,"GO")
        source = self.root / "Solicitation test.txt"
        source.write_text("BID SUBMISSION DEADLINE\nDecember 18, 2030\n1:00 p.m. Pacific",encoding="utf-8")
        revised = self.root / "Addendum_1_test.txt"
        revised.write_text("BID SUBMISSION DEADLINE\nDecember 21, 2030\n3:00 p.m. Pacific",encoding="utf-8")
        documents.attach(self.project,lid,source)
        base, = review.run_first_review(self.project,lid)["bid_due"]
        review.set_finding_status(self.project,base["id"],"verified")
        self.assertEqual([e["value"] for e in planning.calendar_events(self.project)],["2030-12-18 13:00 PT"])
        documents.attach(self.project,lid,revised)
        new, = review.run_first_review(self.project,lid)["bid_due"]
        self.assertEqual((new["value"],new["status"]),("2030-12-21 15:00 PT","draft"))
        self.assertEqual(planning.calendar_events(self.project),[])
        review.set_finding_status(self.project,new["id"],"verified")
        self.assertEqual([e["value"] for e in planning.calendar_events(self.project)],["2030-12-21 15:00 PT"])
