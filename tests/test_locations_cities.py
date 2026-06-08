from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Address

from app.config.settings import settings
from app.routers import locations


class MockResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


class MockAsyncClient:
    calls = 0
    payload: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "MockAsyncClient":
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def get(self, *args, **kwargs) -> MockResponse:
        MockAsyncClient.calls += 1
        return MockResponse(MockAsyncClient.payload)


@pytest.fixture(autouse=True)
def reset_locations_state(monkeypatch: pytest.MonkeyPatch):
    locations._city_cache.clear()
    locations._rate_limits.clear()
    MockAsyncClient.calls = 0
    MockAsyncClient.payload = {}
    monkeypatch.setattr(settings, "geonames_username", "test-user")
    monkeypatch.setattr(locations.httpx, "AsyncClient", MockAsyncClient)
    yield
    locations._city_cache.clear()
    locations._rate_limits.clear()


def test_normalize_geoname_with_timezone():
    city = locations.normalize_geoname(
        {
            "geonameId": 3461786,
            "name": "Guaratingueta",
            "countryName": "Brazil",
            "countryCode": "BR",
            "adminName1": "Sao Paulo",
            "lat": "-22.8164",
            "lng": "-45.1925",
            "timezone": {"timeZoneId": "America/Sao_Paulo"},
        }
    )

    assert city == {
        "id": "3461786",
        "name": "Guaratingueta",
        "countryName": "Brazil",
        "countryCode": "BR",
        "adminName": "Sao Paulo",
        "latitude": -22.8164,
        "longitude": -45.1925,
        "timezone": "America/Sao_Paulo",
    }


def test_city_search_rejects_short_query(client: TestClient):
    resp = client.get("/locations/cities?q=s")
    assert resp.status_code == 422


def test_city_search_uses_cache(client: TestClient):
    MockAsyncClient.payload = {
        "geonames": [
            {
                "geonameId": 2988507,
                "name": "Paris",
                "countryName": "France",
                "countryCode": "FR",
                "adminName1": "Ile-de-France",
                "lat": "48.8534",
                "lng": "2.3488",
                "timezone": {"timeZoneId": "Europe/Paris"},
            }
        ]
    }

    first = client.get("/locations/cities?q=Paris&lang=en&maxRows=10")
    second = client.get("/locations/cities?q=paris&lang=en&maxRows=10")

    assert first.status_code == 200
    assert second.status_code == 200
    assert MockAsyncClient.calls == 1
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["cities"][0]["timezone"] == "Europe/Paris"


def test_city_search_api_v5_route_matches_app_base_url(client: TestClient):
    MockAsyncClient.payload = {
        "geonames": [
            {
                "geonameId": 3448439,
                "name": "Sao Paulo",
                "countryName": "Brazil",
                "countryCode": "BR",
                "adminName1": "Sao Paulo",
                "lat": "-23.5475",
                "lng": "-46.6361",
                "timezone": {"timeZoneId": "America/Sao_Paulo"},
            }
        ]
    }

    resp = client.get("/api/v5/locations/cities?q=Sao%20Paulo&lang=pt&maxRows=10")

    assert resp.status_code == 200
    assert resp.json()["cities"][0] == {
        "id": "3448439",
        "name": "Sao Paulo",
        "countryName": "Brazil",
        "countryCode": "BR",
        "adminName": "Sao Paulo",
        "latitude": -23.5475,
        "longitude": -46.6361,
        "timezone": "America/Sao_Paulo",
    }


def test_city_search_api_v5_route_is_in_openapi_schema(client: TestClient):
    resp = client.get("/openapi.json")

    assert resp.status_code == 200
    assert "/api/v5/locations/cities" in resp.json()["paths"]


def test_city_search_returns_controlled_geonames_error(client: TestClient):
    MockAsyncClient.payload = {"status": {"message": "user does not exist"}}

    resp = client.get("/locations/cities?q=Tokyo")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "user does not exist"


def test_city_search_rate_limit():
    class Request:
        client = Address("127.0.0.1", 12345)

    for _ in range(locations.RATE_LIMIT_MAX_REQUESTS):
        locations._enforce_rate_limit(Request())  # type: ignore[arg-type]

    with pytest.raises(locations.HTTPException) as exc:
        locations._enforce_rate_limit(Request())  # type: ignore[arg-type]

    assert exc.value.status_code == 429
