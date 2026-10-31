import base64
import os
import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.security import require_api_auth, validate_auth_configuration


_TEST_USERNAME = "test-user"
_TEST_PASSWORD = "test-password-1234"


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        auth_environment = patch.dict(
            os.environ,
            {
                "GULLYSCORE_USERNAME": _TEST_USERNAME,
                "GULLYSCORE_PASSWORD": _TEST_PASSWORD,
            },
        )
        auth_environment.start()
        self.addCleanup(auth_environment.stop)
        self.client = TestClient(app)
        self.protected_app = FastAPI()

        @self.protected_app.get(
            "/protected",
            dependencies=[Depends(require_api_auth)],
        )
        def protected_endpoint():
            return {"status": "ok"}

        self.protected_client = TestClient(self.protected_app)

    def tearDown(self) -> None:
        self.client.close()
        self.protected_client.close()

    def test_api_rejects_missing_or_invalid_basic_credentials(self) -> None:
        missing = self.protected_client.get("/protected")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.headers.get("www-authenticate"), "Basic")
        self.assertEqual(self.client.get("/api/teams").status_code, 401)

        invalid_header = "Basic " + base64.b64encode(
            b"wrong-user:wrong-password"
        ).decode("ascii")
        invalid = self.protected_client.get(
            "/protected",
            headers={"Authorization": invalid_header},
        )
        self.assertEqual(invalid.status_code, 401)

    def test_valid_basic_credentials_allow_api_access(self) -> None:
        valid_header = "Basic " + base64.b64encode(
            f"{_TEST_USERNAME}:{_TEST_PASSWORD}".encode("utf-8")
        ).decode("ascii")
        response = self.protected_client.get(
            "/protected",
            headers={"Authorization": valid_header},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_homepage_requires_basic_credentials(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 401)

    def test_auth_configuration_requires_a_long_password(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GULLYSCORE_USERNAME": _TEST_USERNAME,
                "GULLYSCORE_PASSWORD": "short",
            },
        ):
            with self.assertRaises(RuntimeError):
                validate_auth_configuration()

    def test_auth_configuration_requires_both_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GULLYSCORE_USERNAME": "",
                "GULLYSCORE_PASSWORD": "",
            },
        ):
            with self.assertRaises(RuntimeError):
                validate_auth_configuration()


if __name__ == "__main__":
    unittest.main()
