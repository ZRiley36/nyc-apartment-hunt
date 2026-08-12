from apthunt.delivery.email import build_email, send_email, new_match_count
from apthunt.pipeline.report import ReportContext, Card
from apthunt.config.schema import Profile

def _ctx(new=True):
    c = Card(url="https://x/1", address="1 A St", neighborhood="Bushwick", price=3000, beds=1,
             baths=1, grade="Apply now", rationale="r", summary="s", photo=None, is_new=new)
    return ReportContext("zach", "t", apply=[c], consider=[], nope_count=0, new_ids=[])

def _p(): return Profile.model_validate({"name": "zach", "email": "z@e.com", "enabled": True,
    "budget": {"min": 1, "max": 2}, "locations": ["X"], "bedrooms": {}, "bathrooms": {},
    "move_in": {}, "amenities": {}, "run": {}})

def test_new_match_count():
    assert new_match_count(_ctx(new=True)) == 1
    assert new_match_count(_ctx(new=False)) == 0

def test_build_email_fields():
    msg = build_email(_p(), _ctx(), "https://site/r/zach-abc.html")
    assert msg["To"] == "z@e.com"
    assert "1 new" in msg["Subject"]
    assert "https://site/r/zach-abc.html" in msg.as_string()

class _FakeSMTP:
    sent = []
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): pass
    def login(self, u, p): pass
    def send_message(self, m): _FakeSMTP.sent.append(m)

def test_send_uses_smtp(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "h"); monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    monkeypatch.setenv("MAIL_FROM", "from@e.com")
    send_email(build_email(_p(), _ctx(), "url"), smtp=_FakeSMTP)
    assert len(_FakeSMTP.sent) == 1
