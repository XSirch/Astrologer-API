"""
This is part of Astrologer API (C) 2023 Giacomo Battaglia
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
import logging


class SecretKeyCheckerMiddleware:
    # Paths excluded from authentication (public endpoints)
    EXCLUDED_PATHS: set[str] = {"/health", "/locations/cities", "/api/v5/locations/cities"}

    def __init__(self, app: ASGIApp, secret_key_names: str | list[str], secret_keys: list = []) -> None:
        self.app = app
        self.secret_key_values = [key for key in secret_keys if key]
        # Normalize to list for backwards compatibility with single strings
        if isinstance(secret_key_names, str):
            self.secret_key_names = [secret_key_names] if secret_key_names else []
        else:
            self.secret_key_names = [name for name in secret_key_names if name]
        self.pass_all = False

        if not self.secret_key_names or not self.secret_key_values:
            logging.critical("Secret key name or secret key values not set. The middleware will let all requests pass through!")
            self.pass_all = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.pass_all:
            await self.app(scope, receive, send)
            return

        # Skip authentication for excluded paths (e.g., /health)
        path = scope.get("path", "")
        if path in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)

        # OR logic: accept if at least one header contains a valid key
        for key_name in self.secret_key_names:
            header_value = headers.get(key_name, "").split(":")[0]
            if header_value in self.secret_key_values:
                await self.app(scope, receive, send)
                return

        response = JSONResponse(
            status_code=403,
            content={
                "status": "KO",
                "message": "Forbidden: Invalid or missing secret key",
            },
        )
        await response(scope, receive, send)
