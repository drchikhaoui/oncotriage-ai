"""Tests for HTTP Basic auth on /dashboard."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_dashboard_without_auth_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_wrong_credentials_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard", auth=("wrong", "wrong"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_correct_credentials_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard", auth=("clinician", "change-me-in-production"))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_security_headers_present():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/", follow_redirects=True)
    assert "x-content-type-options" in resp.headers
    assert "x-frame-options" in resp.headers
    assert "referrer-policy" in resp.headers


@pytest.mark.asyncio
async def test_ae_options_does_not_expose_ctcae_term():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage/ae-options")
    assert resp.status_code == 200
    for ae in resp.json():
        assert "ctcae_term" not in ae


@pytest.mark.asyncio
async def test_set_lang_cross_origin_redirect_goes_to_root():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/set-lang/fr",
            headers={"referer": "https://evil.example.com/phishing"},
            follow_redirects=False,
        )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
