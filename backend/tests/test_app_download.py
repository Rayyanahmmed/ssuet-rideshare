"""APK download link: public read for the web app, admin write with no redeploy (§23)."""

from __future__ import annotations

import pytest

from app.models.app_setting import AppSetting
from app.services import app_download_service as svc


@pytest.fixture(autouse=True)
def _clean_download_settings(db):
    """Each test starts with no published APK."""
    for key in (svc.URL_KEY, svc.VERSION_KEY, svc.UPDATED_KEY):
        row = db.get(AppSetting, key)
        if row:
            row.value = ""
    db.commit()
    yield


def test_public_download_is_unavailable_until_admin_publishes(client):
    body = client.get("/api/v1/app/download").json()
    assert body["available"] is False
    assert body["url"] is None


def test_admin_publishes_link_and_public_endpoint_serves_it(client, admin):
    url = "https://expo.dev/artifacts/eas/example-build.apk"
    put = client.put(
        "/api/v1/admin/integrations/app-download",
        headers=admin["headers"],
        json={"url": url, "version": "1.0.3"},
    )
    assert put.status_code == 200
    assert put.json()["available"] is True

    public = client.get("/api/v1/app/download").json()
    assert public["url"] == url
    assert public["version"] == "1.0.3"
    assert public["updated_at"]


def test_new_build_replaces_the_old_link(client, admin):
    for version in ("1.0.0", "1.0.1"):
        client.put(
            "/api/v1/admin/integrations/app-download",
            headers=admin["headers"],
            json={"url": f"https://example.com/app-{version}.apk", "version": version},
        )
    public = client.get("/api/v1/app/download").json()
    assert public["version"] == "1.0.1"
    assert public["url"].endswith("app-1.0.1.apk")


def test_empty_url_withdraws_the_download(client, admin):
    client.put(
        "/api/v1/admin/integrations/app-download",
        headers=admin["headers"],
        json={"url": "https://example.com/a.apk", "version": "1"},
    )
    client.put("/api/v1/admin/integrations/app-download", headers=admin["headers"], json={"url": ""})
    assert client.get("/api/v1/app/download").json()["available"] is False


@pytest.mark.parametrize(
    "bad_url",
    ["javascript:alert(1)", "ftp://example.com/a.apk", "file:///etc/passwd", "not a url", "https://"],
)
def test_only_http_links_are_accepted(client, admin, bad_url):
    response = client.put(
        "/api/v1/admin/integrations/app-download",
        headers=admin["headers"],
        json={"url": bad_url, "version": "1"},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/app/download").json()["available"] is False


def test_admin_write_requires_admin_role(client):
    response = client.put(
        "/api/v1/admin/integrations/app-download",
        json={"url": "https://example.com/a.apk", "version": "1"},
    )
    assert response.status_code in (401, 403)


def test_overlong_version_is_rejected(client, admin):
    response = client.put(
        "/api/v1/admin/integrations/app-download",
        headers=admin["headers"],
        json={"url": "https://example.com/a.apk", "version": "x" * 41},
    )
    assert response.status_code == 422


def test_admin_read_matches_public_read(client, admin):
    client.put(
        "/api/v1/admin/integrations/app-download",
        headers=admin["headers"],
        json={"url": "https://example.com/b.apk", "version": "2.0"},
    )
    admin_view = client.get("/api/v1/admin/integrations/app-download", headers=admin["headers"]).json()
    assert admin_view["url"] == "https://example.com/b.apk"
    assert admin_view["version"] == "2.0"
