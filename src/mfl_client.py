from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests


CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_FILE = CACHE_DIR / "mfl_cookie.json"

DEFAULT_YEAR = int(os.getenv("MFL_YEAR", "2025"))
DEFAULT_HOST = os.getenv("MFL_HOST", "www46.myfantasyleague.com")
DEFAULT_UA = os.getenv("MFL_USER_AGENT", "NPFFLNewsletter/1.0 (automation)")


class MFLClient:
    """
    Minimal MFL client.
      - If MFL_API_KEY is set, we append APIKEY=... to all /export calls (no cookie needed).
      - Otherwise, we can log in (USERNAME/PASSWORD) to get a cookie for private endpoints.
      - Will attempt host discovery to use the league's canonical host.
    """

    def __init__(
        self,
        league_id: str | int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        year: Optional[int] = None,
        user_agent: Optional[str] = None,
        timeout: float = 25.0,
    ) -> None:
        self.league_id = str(league_id)
        self.username = username or os.getenv("MFL_USERNAME")
        self.password = password or os.getenv("MFL_PASSWORD")
        self.api_key = os.getenv("MFL_API_KEY") or None

        self.host = host or DEFAULT_HOST
        self.year = int(year or DEFAULT_YEAR)
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent or DEFAULT_UA})

        self.cookie_name: Optional[str] = None
        self.cookie_value: Optional[str] = None

        self._load_cookie()

        # If no API key and we don't already have a cookie, try login (fallback)
        if not self.api_key and not self.cookie_value and self.username and self.password:
            try:
                self.login()
            except Exception:
                # Not fatal if league allows public/APIKEY access
                pass

        # Attempt host discovery (non-fatal)
        try:
            self.discover_host()
        except Exception:
            pass

    # ---------- Cookie persistence ----------

    def _load_cookie(self) -> None:
        if COOKIE_FILE.exists():
            try:
                data = json.loads(COOKIE_FILE.read_text())
                cn, cv = data.get("cookie_name"), data.get("cookie_value")
                if cn and cv:
                    self.cookie_name, self.cookie_value = cn, cv
                    self.session.headers["Cookie"] = f"{cn}={cv}"
            except Exception:
                pass

    def _save_cookie(self, name: str, value: str) -> None:
        self.cookie_name, self.cookie_value = name, value
        self.session.headers["Cookie"] = f"{name}={value}"
        COOKIE_FILE.write_text(json.dumps({"cookie_name": name, "cookie_value": value}))

    # ---------- Auth ----------

    def login(self) -> None:
        url = f"https://api.myfantasyleague.com/{self.year}/login"
        params = {"USERNAME": self.username, "PASSWORD": self.password, "XML": "1"}
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        m1 = re.search(r'cookie_name="([^"]+)"', r.text)
        m2 = re.search(r'cookie_value="([^"]+)"', r.text)
        if not (m1 and m2):
            raise RuntimeError("MFL login failed; cookie not returned")
        self._save_cookie(m1.group(1), m2.group(1))

    # ---------- Host Discovery ----------

    def discover_host(self) -> None:
        """
        Ask the shared API host for league info and update self.host if provided.
        """
        url = f"https://api.myfantasyleague.com/{self.year}/export"
        params = {"TYPE": "league", "L": self.league_id, "JSON": "1"}
        if self.api_key:
            params["APIKEY"] = self.api_key
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        info = r.json()
        league_info = info.get("league") if isinstance(info, dict) else None
        new_host = None
        if isinstance(league_info, dict):
            new_host = league_info.get("host") or league_info.get("url") or league_info.get("league_url")
            if isinstance(new_host, str) and new_host.startswith("http"):
                try:
                    new_host = urlparse(new_host).netloc
                except Exception:
                    new_host = None
        if isinstance(new_host, str) and new_host and new_host != self.host:
            self.host = new_host

    # ---------- Core helpers ----------

    def _url(self, command: str) -> str:
        return f"https://{self.host}/{self.year}/{command}"

    def get_export(self, request_type: str, **params: Any) -> Dict[str, Any]:
        """
        Calls /export?TYPE=<>&L=<league>&JSON=1 (+ APIKEY if present).
        """
        base = {"TYPE": request_type, "JSON": "1"}
        if "L" not in params and self.league_id:
            params["L"] = self.league_id
        if self.api_key:
            params["APIKEY"] = self.api_key

        url = self._url("export")
        last_err = None
        for _ in range(3):
            try:
                r = self.session.get(url, params={**base, **params}, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                time.sleep(1.0)
        if last_err:
            raise last_err
        return {}
