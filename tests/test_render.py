from apthunt.delivery.slug import report_slug
from apthunt.delivery.render import render_report, report_path
from apthunt.pipeline.report import ReportContext, Card

def test_slug_stable_and_unguessable():
    a = report_slug("zach", "salt1")
    assert a == report_slug("zach", "salt1")
    assert a != report_slug("zach", "salt2")
    assert a != report_slug("natasha", "salt1")

def test_render_contains_card_fields():
    card = Card(url="https://x/1", address="1 A St", neighborhood="Bushwick", price=3200,
               beds=1, baths=1, grade="Apply now", rationale="looks great", summary="Nice.",
               photo="https://cdn/a.jpg", is_new=True, matched_amenities=["gym"])
    ctx = ReportContext("zach", "2026-08-11T08:00", apply=[card], consider=[], nope_count=3, new_ids=[])
    html = render_report(ctx)
    assert "1 A St" in html and "Apply now" in html and "https://x/1" in html
    assert "NEW" in html and "3 listings" in html

def test_render_escapes_hostile_input():
    # scraper/LLM-derived fields are published to a public page — must be escaped
    card = Card(url="https://x/1", address="<script>alert(1)</script>", neighborhood="X",
               price=3000, beds=1, baths=1, grade="Apply now", rationale="r",
               summary="<img src=x onerror=alert(2)>", photo=None, is_new=False)
    ctx = ReportContext("zach", "t", apply=[card], consider=[], nope_count=0, new_ids=[])
    html = render_report(ctx)
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror=alert(2)>" not in html  # raw tag must not survive
    assert "&lt;script&gt;" in html and "&lt;img" in html

def test_report_path():
    p = report_path("zach", "salt1")
    assert p.name.startswith("zach-") and p.suffix == ".html"
    assert p.parent.name == "r"
