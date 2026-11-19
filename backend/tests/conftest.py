import pytest

from app import create_app
from app.config import Config


def H(role, uid="user-00000001", name="Test Person", des="Tester"):
    return {"X-User-Id": uid, "X-User-Role": role, "X-User-Name": name, "X-User-Designation": des}


OWNER, REV = H("owner", "owner-0000001", "Olive Owner", "Head"), H("reviewer", "review-000001", "Ravi Reviewer", "Editor")
CREATOR = H("creator", "creat-0000001", "Cara Creator", "Writer")


@pytest.fixture()
def client():
    return create_app(Config(sqlite_path=":memory:", gemini_key="", store="sqlite")).test_client()


def mk_brand(c, name="Brand One", **kw):
    d = {"name": name, "terminology": [{"avoid": "cheap", "prefer": "affordable"}], "restrictedClaims": [{"text": "cures colds", "reason": "health"}], **kw}
    r = c.post("/api/brands", headers=OWNER, json=d)
    assert r.status_code == 201, r.json
    return r.json["brand"]


def mk_product(c, bid, name="Kettle", **kw):
    d = {"name": name, "previousNames": ["Hotpot"], "specs": [{"name": "Capacity", "value": "1.7 litres", "source": "spec"}], **kw}
    r = c.post(f"/api/brands/{bid}/products", headers=OWNER, json=d)
    assert r.status_code == 201, r.json
    return r.json["product"]
