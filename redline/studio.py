"""Minimal Bluebeam Studio API client.

UNVERIFIED: the endpoint paths and token flow below follow Bluebeam's public
developer documentation as remembered, and have NOT been tested against the
live API. Access needs a Bluebeam subscription and Developer Portal approval
(https://developers.bluebeam.com). Check every path against the portal docs
before relying on this, and override the URLs via ``StudioConfig``.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class StudioConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    auth_url: str = "https://api.bluebeam.com/oauth2/authorize"
    token_url: str = "https://api.bluebeam.com/oauth2/token"
    api_base: str = "https://api.bluebeam.com/publicapi/v1"
    scope: str = "full_user"


class StudioError(RuntimeError):
    pass


class StudioClient:
    def __init__(self, config: StudioConfig, client: httpx.Client | None = None):
        self.config = config
        self._http = client or httpx.Client(timeout=30)
        self.access_token: str | None = None

    def authorize_url(self, state: str) -> str:
        c = self.config
        return str(httpx.URL(c.auth_url, params={
            "response_type": "code", "client_id": c.client_id,
            "redirect_uri": c.redirect_uri, "scope": c.scope, "state": state}))

    def exchange_code(self, code: str) -> None:
        c = self.config
        r = self._http.post(c.token_url, data={
            "grant_type": "authorization_code", "code": code,
            "client_id": c.client_id, "client_secret": c.client_secret,
            "redirect_uri": c.redirect_uri})
        if r.status_code != 200:
            raise StudioError(f"token exchange failed: {r.status_code} {r.text}")
        self.access_token = r.json()["access_token"]

    def _request(self, method: str, path: str, **kw) -> dict:
        if not self.access_token:
            raise StudioError("not authorized; call exchange_code first")
        r = self._http.request(
            method, self.config.api_base + path,
            headers={"Authorization": f"Bearer {self.access_token}",
                     "client_id": self.config.client_id}, **kw)
        if r.status_code >= 400:
            raise StudioError(f"{method} {path} failed: {r.status_code} {r.text}")
        return r.json() if r.content else {}

    def list_sessions(self) -> dict:
        return self._request("GET", "/sessions")

    def create_session(self, name: str, notification: bool = False,
                       restricted: bool = False) -> dict:
        return self._request("POST", "/sessions", json={
            "Name": name, "Notification": notification, "Restricted": restricted})
