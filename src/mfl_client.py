# src/mfl_client.py
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


class MFLClient:
    """
    Thin client for MyFantasyLeague export and login flows.

    Prefers API key if provided. Falls back to username/password session.
    Caches cookies on disk to reduce logins when using user/pass.

    Minimal endpoints implemented:
      - players (DETAILS=1)
      - weeklyResults
      - leagueStandings
      - pool (NFL Confidence)
      - survivorPool
    """

    def __init__(
        self,
        league_id: str,
        year: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        cache_dir: str | Path = "data/cache",
        host: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.league_id = str(league_id)
        self.year = int(year)
        self.username = (username or "").strip() or None
        self.password = (password or "").strip() or None
        self.api_key = (api_key or os.environ.get("MFL_API_KEY") or "").strip() or None
        self.timeout = timeout

        # MFL host pattern: wwwXX.myfantasyleague.com
        # If not specified, infer from league home URL pattern (you gave us www46)
        self.host = host or "www46.myfantasyleague.com"

        self.base = f"https://{self.host}/{self.year}"
        self.sess = requests.Session()
        self.sess.headers.update({"User-Agent": "npffl-newsletter/1.0"})

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_path = self.cache_dir / "mfl_cookies.json"

        # If we have no API key, try to restore cookies and/or login.
        if not self.api_key:
            self._restore_cookies()
            # Only login if we have credentials and no valid cookies
            if self.username and self.password and not self._has_valid_cookies():
                self._login_and_cache()

    # -------------------------
    # Cookie handling
    # -------------------------
    def _restore_cookies(self) -> None:
        try:
            if self.cookie_path.exists():
                data = json.loads(self.cookie_path.read_text(encoding="utf-8"))
                # Optional: respect simple expiry
                exp = data.get("_expires", 0)
                if exp and time.time() > float(exp):
                    return
                cookies = data.get("cookies", {})
                if cookies:
                    self.sess.cookies.update(cookies)
        except Exception:
            pass

    def _save_cookies(self, ttl_seconds: int = 60 * 60 * 24 * 7) -> None:
        try:
            data = {
                "cookies": self.sess.cookies.get_dict(),
                "_saved": time.time(),
                "_expires": time.time() + ttl_seconds,
            }
            self.cookie_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _has_valid_cookies(self) -> bool:
        # Heuristic: presence of 'MFL_USER_ID' or session cookie suggests we’re logged in
        ck = self.sess.cookies.get_dict()
        return any(k.lower().startswith("mfl") or k.lower().startswith("session") for k in ck.keys())

    def _login_and_cache(self) -> None:
        """
        Performs a lightweight login against MFL’s login page so that
        subsequent export pages that require auth will succeed.
        """
        if not (self.username and self.password):
            return
        url = f"{self.base}/login"
        # MFL login typically accepts POST form with username/password; we keep it resilient.
        payload = {"USERNAME": self.username, "PASSWORD": self.password}
        try:
            resp = self.sess.post(url, data=payload, timeout=self.timeout)
            resp.raise_for_status()
            # if login success, cookies should be populated
            if self._has_valid_cookies():
                self._save_cookies()
        except Exception as e:
            # Non-fatal; many export endpoints are public or API-key based.
            print(f"[mfl_client] Login failed or not required: {e}")

    # -------------------------
    # Low-level GET
    # -------------------------
    def _export(self, type_: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Hit /export with TYPE=... and optional JSON=1.
        Adds L, APIKEY automatically when available.
        """
        params = dict(params or {})
        params.setdefault("TYPE", type_)
        params.setdefault("L", self.league_id)
        params.setdefault("JSON", 1)
        if self.api_key:
            params.setdefault("APIKEY", self.api_key)

        url = f"{self.base}/export"
        r = self.sess.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            # fall back to best-effort json parse
            return json.loads(r.text)

    # -------------------------
    # Public helpers
    # -------------------------
    def get_players(self, details: int = 1, since: str = "", ids: str = "") -> Dict[str, Any]:
        params = {
            "DETAILS": details,
            "SINCE": since,
        }
        if ids:
            params["PLAYERS"] = ids
        return self._export("players", params)

    def get_weekly_results(self, week: Optional[int] = None, missing_as_bye: str = "") -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if week is not None:
            params["W"] = int(week)
        if missing_as_bye:
            params["MISSING_AS_BYE"] = missing_as_bye
        return self._export("weeklyResults", params)

    def get_league_standings(self, column_names: str = "", all_: str = "", web: str = "") -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if column_names:
            params["COLUMN_NAMES"] = column_names
        if all_:
            params["ALL"] = all_
        if web:
            params["WEB"] = web
        return self._export("leagueStandings", params)

    def get_pool(self, pooltype: str = "NFL") -> Dict[str, Any]:
        params = {"POOLTYPE": pooltype}
        return self._export("pool", params)

    def get_survivor(self) -> Dict[str, Any]:
        return self._export("survivorPool", {})

    # convenience used by fetchers
    def get(self, type_: str, **params: Any) -> Dict[str, Any]:
        return self._export(type_, params)
