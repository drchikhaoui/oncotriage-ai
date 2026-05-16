"""Integration tests for dashboard route auth."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_dashboard_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Basic"


@pytest.mark.asyncio
async def test_dashboard_wrong_credentials_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard", auth=("wrong", "credentials"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_correct_credentials_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/dashboard", auth=("clinician", "change-me-in-production"))
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
