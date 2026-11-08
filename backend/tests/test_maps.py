"""Map integration: key stays on the server, and rotating it needs no rebuild (§13).

Every network call is monkeypatched — the suite must pass offline in CI.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import map_service
from tests.helpers import register

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001"

    "0d0a2db40000000049454e44ae426082"
)


class _FakeResponse:
    def __init__(self, *, content: bytes = b"", payload: dict | None = None, status: int = 200, ctype: str = "image/png"):
        self.content = content
        self._payload = payload or {}
        self.status_code = status
        self.headers = {"content-type": ctype}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=httpx.Request("GET", "http://x"), response=self)  # type: ignore[arg-type]


@pytest.fixture
def fake_net(monkeypatch):
    """Record every outbound URL and answer with a 1px PNG."""
    calls: list[str] = []

    def _get(url, **kwargs):
        calls.append(url)
        kwargs.get("params")
        return _FakeResponse(content=PNG_1PX)

    monkeypatch.setattr(map_service.httpx, "get", _get)
    map_service._TILE_CACHE.clear()
    return calls


# --------------------------------------------------------------------- public config
def test_client_config_defaults_to_keyless_osm(client):
    body = client.get("/api/v1/maps/config").json()
    assert body["provider"] == "osm"
    assert body["needs_key"] is False
    assert body["enabled"] is True
    assert body["tile_url_template"] == "/api/v1/maps/tiles/{z}/{x}/{y}.png"
    assert "OpenStreetMap" in body["attribution"]
    assert "api_key" not in body and "key" not in body


def test_client_config_needs_no_token(client):
    """The app must be able to learn the provider before the user signs in."""
    assert client.get("/api/v1/maps/config").status_code == 200


# --------------------------------------------------------------------- admin rotation
def test_admin_can_rotate_key_and_config_never_leaks_it(client, admin, fake_net):
    headers = admin["headers"]

    current = client.get("/api/v1/admin/integrations/maps", headers=headers)
    assert current.status_code == 200
    assert current.json()["has_key"] is False
    assert {p["value"] for p in current.json()["available_providers"]} == {"osm", "geoapify", "maptiler"}

    rotated = client.put(
        "/api/v1/admin/integrations/maps",
        headers=headers,
        json={"provider": "geoapify", "api_key": "gp-secret-key-123", "style": "osm-bright"},
    )
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["provider"] == "geoapify" and body["has_key"] is True and body["needs_key"] is True
    assert "gp-secret-key-123" not in rotated.text

    # The rotation reaches clients immediately, still without exposing the key.
    public = client.get("/api/v1/maps/config").json()
    assert public["provider"] == "geoapify" and public["has_key"] is True
    assert "gp-secret-key-123" not in str(public)


def test_omitting_api_key_keeps_the_stored_one(client, admin, fake_net):
    headers = admin["headers"]
    client.put("/api/v1/admin/integrations/maps", headers=headers, json={"api_key": "keep-me-please"})
    client.put("/api/v1/admin/integrations/maps", headers=headers, json={"style": "dark"})
    assert client.get("/api/v1/admin/integrations/maps", headers=headers).json()["has_key"] is True


def test_empty_api_key_clears_it(client, admin, fake_net):
    headers = admin["headers"]
    client.put("/api/v1/admin/integrations/maps", headers=headers, json={"provider": "geoapify", "api_key": "temp"})
    cleared = client.put("/api/v1/admin/integrations/maps", headers=headers, json={"api_key": ""})
    assert cleared.json()["has_key"] is False


def test_key_is_encrypted_at_rest(client, admin, db, fake_net):
    from app.models.app_setting import AppSetting

    client.put("/api/v1/admin/integrations/maps", headers=admin["headers"], json={"api_key": "plain-text-key"})
    stored = db.get(AppSetting, "maps.api_key_enc").value
    assert "plain-text-key" not in stored


def test_unknown_provider_is_rejected(client, admin):
    response = client.put("/api/v1/admin/integrations/maps", headers=admin["headers"], json={"provider": "nope"})
    assert response.status_code == 422


def test_non_admin_cannot_read_or_write_map_settings(client):
    user = register(client)
    assert client.get("/api/v1/admin/integrations/maps", headers=user["headers"]).status_code == 403
    assert (
        client.put(
            "/api/v1/admin/integrations/maps", headers=user["headers"], json={"api_key": "stolen"}
        ).status_code
        == 403
    )


def test_anonymous_cannot_read_admin_map_settings(client):
    assert client.get("/api/v1/admin/integrations/maps").status_code == 401


# --------------------------------------------------------------------- tile proxy
def test_tile_proxy_serves_png_and_caches(client, fake_net):
    first = client.get("/api/v1/maps/tiles/12/2345/1367.png")
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert first.headers["cache-control"] == "public, max-age=86400"
    assert len(fake_net) == 1

    second = client.get("/api/v1/maps/tiles/12/2345/1367.png")  # served from memory
    assert second.status_code == 200
    assert len(fake_net) == 1


def test_tile_proxy_injects_key_server_side(client, admin, fake_net):
    client.put(
        "/api/v1/admin/integrations/maps",
        headers=admin["headers"],
        json={"provider": "geoapify", "api_key": "server-side-secret"},
    )
    response = client.get("/api/v1/maps/tiles/10/1/2.png")
    assert response.status_code == 200
    assert fake_net[-1].startswith("https://maps.geoapify.com/v1/tile/osm-bright/10/1/2.png")
    assert "apiKey=server-side-secret" in fake_net[-1]
    assert "server-side-secret" not in response.text


def test_provider_needing_key_without_key_falls_back_to_osm(client, admin, fake_net):
    client.put("/api/v1/admin/integrations/maps", headers=admin["headers"], json={"provider": "maptiler"})
    response = client.get("/api/v1/maps/tiles/5/1/1.png")
    assert response.status_code == 200
    assert response.headers["X-Map-Fallback"] == "1"
    assert response.headers["X-Map-Provider"] == "osm"


def test_disabling_maps_stops_tiles_and_flags_config(client, admin, fake_net):
    client.put("/api/v1/admin/integrations/maps", headers=admin["headers"], json={"enabled": False})
    assert client.get("/api/v1/maps/config").json()["enabled"] is False
    assert client.get("/api/v1/maps/tiles/3/1/1.png").status_code == 503


def test_tile_out_of_range_is_404(client):
    assert client.get("/api/v1/maps/tiles/23/1/1.png").status_code == 404


def test_provider_failure_is_502(client, monkeypatch):
    def _boom(url, **kwargs):
        raise httpx.ConnectTimeout("no route")

    monkeypatch.setattr(map_service.httpx, "get", _boom)
    map_service._TILE_CACHE.clear()
    response = client.get("/api/v1/maps/tiles/4/2/2.png")
    assert response.status_code == 502


# --------------------------------------------------------------------- test button + search
def test_admin_test_button_reports_failure_reason(client, admin, fake_net):
    client.put("/api/v1/admin/integrations/maps", headers=admin["headers"], json={"provider": "geoapify"})
    body = client.post("/api/v1/admin/integrations/maps/test", headers=admin["headers"]).json()
    assert body["ok"] is False and "needs an API key" in body["reason"]

    client.put("/api/v1/admin/integrations/maps", headers=admin["headers"], json={"api_key": "good"})
    body = client.post("/api/v1/admin/integrations/maps/test", headers=admin["headers"]).json()
    assert body["ok"] is True and body["provider"] == "geoapify" and body["latency_ms"] is not None


def test_search_requires_auth(client):
    assert client.get("/api/v1/maps/search?q=Gulshan").status_code == 401


def test_search_via_osm_speaks_the_same_shape(client, monkeypatch):
    def _get(url, **kwargs):
        return _FakeResponse(
            payload=[{"display_name": "Gulshan-e-Iqbal, Karachi, Sindh, Pakistan", "lat": "24.9180", "lon": "67.0822"}]
        )

    monkeypatch.setattr(map_service.httpx, "get", _get)
    user = register(client)
    rows = client.get("/api/v1/maps/search?q=Gulshan", headers=user["headers"]).json()
    assert rows == [
        {"label": "Gulshan-e-Iqbal, Karachi, Sindh, Pakistan", "latitude": 24.918, "longitude": 67.0822}
    ]


def test_reverse_geocode_returns_area_label(client, monkeypatch):
    def _get(url, **kwargs):
        return _FakeResponse(payload={"display_name": "NED University, Karachi, Sindh, Pakistan"})

    monkeypatch.setattr(map_service.httpx, "get", _get)
    user = register(client)
    body = client.get("/api/v1/maps/reverse?lat=24.9&lng=67.1", headers=user["headers"]).json()
    assert body["label"].startswith("NED University")
    assert body["latitude"] == 24.9


def test_search_short_query_is_422(client):
    user = register(client)
    assert client.get("/api/v1/maps/search?q=a", headers=user["headers"]).status_code == 422


# --------------------------------------------------------------------- honest failure reporting
def _provider_rejects(status: int = 401, message: str = "Invalid apiKey"):
    """Real providers answer a dead key with JSON — which must never be treated as a tile."""

    def _get(url, **kwargs):
        return _FakeResponse(payload={"statusCode": status, "error": "Unauthorized", "message": message},
                             status=status, ctype="application/json")

    return _get


def test_dead_key_is_reported_truthfully_by_the_test_button(client, admin, monkeypatch):
    monkeypatch.setattr(map_service.httpx, "get", _provider_rejects())
    map_service._TILE_CACHE.clear()
    client.put(
        "/api/v1/admin/integrations/maps",
        headers=admin["headers"],
        json={"provider": "geoapify", "api_key": "expired-key"},
    )
    body = client.post("/api/v1/admin/integrations/maps/test", headers=admin["headers"]).json()
    assert body["ok"] is False
    assert "401" in body["reason"] and "Invalid apiKey" in body["reason"]
    assert "API key" in body["reason"] or "quota" in body["reason"]


def test_expired_key_produces_a_readable_502_not_a_blank_map(client, admin, monkeypatch):
    monkeypatch.setattr(map_service.httpx, "get", _provider_rejects())
    map_service._TILE_CACHE.clear()
    client.put(
        "/api/v1/admin/integrations/maps",
        headers=admin["headers"],
        json={"provider": "geoapify", "api_key": "expired-key"},
    )
    response = client.get("/api/v1/maps/tiles/12/2811/1755.png")
    assert response.status_code == 502
    assert "401" in response.json()["detail"]


def test_non_image_body_is_rejected(client, admin, monkeypatch):
    def _get(url, **kwargs):
        return _FakeResponse(content=b'{"error":"nope"}', ctype="application/json", status=200)

    monkeypatch.setattr(map_service.httpx, "get", _get)
    map_service._TILE_CACHE.clear()
    client.put(
        "/api/v1/admin/integrations/maps", headers=admin["headers"], json={"provider": "geoapify", "api_key": "k"}
    )
    assert client.get("/api/v1/maps/tiles/9/1/1.png").status_code == 502
