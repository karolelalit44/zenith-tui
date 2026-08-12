from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Demo API"


def test_create_and_fetch_item():
    created = client.post("/items", json={"name": "Widget", "price": 9.99})
    assert created.status_code == 201
    item_id = created.json()["id"]

    fetched = client.get(f"/items/{item_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Widget"


def test_update_item():
    created = client.post("/items", json={"name": "Gadget", "price": 5.0})
    item_id = created.json()["id"]

    updated = client.patch(f"/items/{item_id}", json={"price": 7.5})
    assert updated.status_code == 200
    assert updated.json()["price"] == 7.5


def test_delete_item_returns_204():
    created = client.post("/items", json={"name": "Tmp", "price": 1.0})
    item_id = created.json()["id"]

    deleted = client.delete(f"/items/{item_id}")
    assert deleted.status_code == 204


def test_missing_item_returns_404():
    resp = client.get("/items/9999")
    assert resp.status_code == 404
