from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


# Where we persist the session cookie so subsequent steps can reuse it.
CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
COOKIE_FILE = CACHE_DIR / "mfl_cookie.json"

# You can override these via env if MFL migrates hosts/years.
DEFAULT_YEAR = int(os.getenv("MFL_YEAR", "2025"))
DEFAULT_HOST = os.getenv("MFL_HOST", "www46.myfantasyleague.com")

# Respect the registered API Client / unique UA string.
DEFAULT_UA = os.getenv("MFL_USER_AGENT", "NPFFLNewsletter/1.0 (automation)")


class MFLClient:
    """
    Minimal cookie-based client for MFL.
    - Performs login with username/password to obtain a cookie
    - Sends that cookie on subsequent requests
    - Convenience helper for /export JSON endpoints
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
        self.host = host or DEFAULT_HOST
        self.year = int(year or DEFAULT_YEAR)
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent or DEFAULT_UA})

        self.cookie_name: Optional[str] = None
        self.cookie_value: Optional[str] = None
        self._load_cookie()

        # If we don't have a cookie yet, try to login (username/password recommended)
        if not self.cookie_value and self.username and self.password:
            self.login()

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
                # Corrupt cache: ignore
                pass

    def _save_cookie(self, name: str, value: str) -> None:
        self.cookie_name, self.cookie_value = name, value
        self.session.headers["Cookie"] = f"{name}={value}"
        COOKIE_FILE.write_text(json.dumps({"cookie_name": name, "cookie_value": value}))

    # ---------- Auth ----------

    def login(self) -> None:
        """
        Performs the documented MFL login (XML=1 returns <status cookie_name="" cookie_value="">).
        """
        url = f"https://api.myfantasyleague.com/{self.year}/login"
        params = {"USERNAME": self.username, "PASSWORD": self.password, "XML": "1"}
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()

        # Example: <status cookie_name="MFL_USER_ID" cookie_value="..." status="success" />
        m1 = re.search(r'cookie_name="([^"]+)"', r.text)
        m2 = re.search(r'cookie_value="([^"]+)"', r.text)
        if not (m1 and m2):
            raise RuntimeError("MFL login failed; cookie not returned")
        self._save_cookie(m1.group(1), m2.group(1))

    # ---------- Core helpers ----------

    def _url(self, command: str) -> str:
        return f"https://{self.host}/{self.year}/{command}"

    def get_export(self, request_type: str, **params: Any) -> Dict[str, Any]:
        """
        Calls /export?TYPE=<>&L=<league>&JSON=1 plus any extra params.
        Cookie should already be on the session.
        """
        base = {"TYPE": request_type, "JSON": "1"}
        # ensure league id is always present unless explicitly overridden
        if "L" not in params and self.league_id:
            params["L"] = self.league_id

        # light retry on 5xx / network blips
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
        # If still failing, raise the last error
        if last_err:
            raise last_err
        return {}
