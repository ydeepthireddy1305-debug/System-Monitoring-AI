import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


TEST_USERNAME = os.getenv("TEST_USERNAME")
TEST_PASSWORD = os.getenv("TEST_PASSWORD")


def get_access_token() -> str:
    response = client.post(
        "/auth/token",
        data={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 200, response.text

    token_data = response.json()

    assert "access_token" in token_data
    assert token_data.get("token_type", "").lower() == "bearer"

    return token_data["access_token"]


def test_invalid_login_is_rejected():
    response = client.post(
        "/auth/token",
        data={
            "username": "invalid_test_user",
            "password": "invalid_test_password",
        },
    )

    assert response.status_code in (401, 400)


def test_auth_me_requires_token():
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_dashboard_requires_token():
    response = client.get("/dashboard")

    assert response.status_code == 401


@pytest.mark.skipif(
    not TEST_USERNAME or not TEST_PASSWORD,
    reason="Set TEST_USERNAME and TEST_PASSWORD for authenticated tests.",
)
def test_valid_login():
    token = get_access_token()

    assert token


@pytest.mark.skipif(
    not TEST_USERNAME or not TEST_PASSWORD,
    reason="Set TEST_USERNAME and TEST_PASSWORD for authenticated tests.",
)
def test_auth_me_with_valid_token():
    token = get_access_token()

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200


@pytest.mark.skipif(
    not TEST_USERNAME or not TEST_PASSWORD,
    reason="Set TEST_USERNAME and TEST_PASSWORD for authenticated tests.",
)
def test_dashboard_with_valid_token():
    token = get_access_token()

    response = client.get(
        "/dashboard",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200