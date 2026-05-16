"""Integration tests for welcome, about, intake, and error pages."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root_returns_welcome_page():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "OncoTriage" in resp.text


@pytest.mark.asyncio
async def test_intake_route_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/intake")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_about_route_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/about")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_about_in_french():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/about?lang=fr")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_about_in_arabic():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/about?lang=ar")
    assert resp.status_code == 200
    assert 'dir="rtl"' in resp.text


@pytest.mark.asyncio
async def test_404_returns_html_not_json():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/this-page-does-not-exist")
    assert resp.status_code == 404
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_health_endpoint_has_version_and_checks():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "3.1.0"
    assert "checks" in data
    assert "database" in data["checks"]
