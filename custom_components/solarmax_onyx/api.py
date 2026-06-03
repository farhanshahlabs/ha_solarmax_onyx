"""CloudInverter.net API client.

Authentication uses AES-CBC signed request bodies (reverse-engineered from the
JS bundle). The sign is computed per-request and included in the POST body.

Self-healing: if the sign keys are ever rotated by the platform, the integration
automatically fetches the current keys from the live JS bundle and retries.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import aiohttp

from .const import AES_KEY, AES_IV, BASE_URL, SIGN_SALT

_LOGGER = logging.getLogger(__name__)

# Module-level key cache — starts with the known-good defaults from const.py.
# Updated automatically if the platform rotates its keys.
_key_cache: dict[str, bytes | str] = {
    "aes_key":   AES_KEY,
    "aes_iv":    AES_IV,
    "sign_salt": SIGN_SALT,
}


# ---------------------------------------------------------------------------
# Key self-healing
# ---------------------------------------------------------------------------

async def _fetch_live_keys(session: aiohttp.ClientSession) -> bool:
    """Fetch current AES keys from the live JS bundle.

    The keys are hardcoded in the minified JS bundle served by
    cloudinverter.net. This function:
      1. Fetches the HTML page to find the current bundle filename (which
         changes with each deployment via a content hash in the filename).
      2. Downloads the bundle (~300 kB).
      3. Extracts the 32-char key and 16-char IV using regex.
      4. Updates _key_cache if values have changed.

    Returns True if the cache was updated with new values.
    """
    _LOGGER.info("Fetching live AES keys from JS bundle")
    try:
        timeout = aiohttp.ClientTimeout(total=20)

        # Step 1: find bundle filename from HTML
        async with session.get(
            "https://www.cloudinverter.net/dist/", timeout=timeout
        ) as resp:
            html = await resp.text()

        match = re.search(r'src="[./]*(umi\.[a-f0-9]+\.js)"', html)
        if not match:
            _LOGGER.warning("Could not locate JS bundle URL in page HTML")
            return False

        bundle_url = f"https://www.cloudinverter.net/dist/{match.group(1)}"
        _LOGGER.debug("Found bundle: %s", bundle_url)

        # Step 2: download bundle
        async with session.get(bundle_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            js = await resp.text()

        # Step 3: extract keys
        # Pattern in bundle: sign:(0,Xe.U$)(e,"<32-digit-key>","<16-digit-iv>")
        key_match = re.search(r'"(\d{32})","(\d{16})"', js)
        if not key_match:
            _LOGGER.warning("AES key pattern not found in JS bundle")
            return False

        new_key  = key_match.group(1).encode()
        new_iv   = key_match.group(2).encode()
        new_salt = key_match.group(1)  # salt = key string (same value)

        if new_key == _key_cache["aes_key"] and new_iv == _key_cache["aes_iv"]:
            _LOGGER.debug("AES keys unchanged")
            return False

        _LOGGER.info(
            "AES keys updated — key: %s... iv: %s...",
            new_key[:8].decode(), new_iv[:4].decode()
        )
        _key_cache["aes_key"]   = new_key
        _key_cache["aes_iv"]    = new_iv
        _key_cache["sign_salt"] = new_salt
        return True

    except Exception as err:
        _LOGGER.warning("Key refresh failed: %s", err)
        return False


# ---------------------------------------------------------------------------
# Sign computation
# ---------------------------------------------------------------------------

def _compute_sign(payload: dict) -> str:
    """AES-CBC sign of the sorted payload — mirrors JS bundle module 56938 / fn C."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as crypto_padding

    filtered = {
        k: v for k, v in payload.items()
        if v is not None and v != "" and not isinstance(v, bool)
    }
    parts = []
    for k in sorted(filtered):
        v = filtered[k]
        parts.append(f"{k}=Array" if isinstance(v, list) else f"{k}={v}")
    plaintext = "&".join(parts) + "&" + _key_cache["sign_salt"]

    key = _key_cache["aes_key"]
    iv  = _key_cache["aes_iv"]

    padder = crypto_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    return base64.b64encode(enc.update(padded) + enc.finalize()).decode()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CloudInverterAuthError(Exception):
    """Raised when login fails due to bad credentials or expired keys."""


class CloudInverterApiError(Exception):
    """Raised on non-auth API errors."""


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class CloudInverterAPI:
    """Async API client for CloudInverter.net."""

    def __init__(self, member_id: str, password: str) -> None:
        self._member_id = member_id
        self._password  = password
        self._token: str  = ""
        self._auto_id: str = ""

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def async_login(self, session: aiohttp.ClientSession, _retry: bool = False) -> None:
        """Login and store the JWT token.

        On first failure, attempts a key refresh from the live JS bundle and
        retries once. This handles the case where the platform rotated its
        AES signing keys. If the retry also fails, raises CloudInverterAuthError
        (most likely wrong credentials).
        """
        payload = {
            "MemberID": self._member_id,
            "Password": self._password,
            "remember": "true",
            "type": "1",
        }
        payload["sign"] = _compute_sign(payload)
        data = await self._post(session, "/Inverterapi/UserLogin_v1", payload, auth=False)

        if data.get("status") != "ok":
            if not _retry:
                _LOGGER.info("Login failed — refreshing keys and retrying")
                await _fetch_live_keys(session)
                return await self.async_login(session, _retry=True)
            raise CloudInverterAuthError(
                "Login failed — check username/password "
                f"(status: {data.get('status', 'unknown')})"
            )

        self._token   = data["token"]
        self._auto_id = str(data["MemberAutoID"])
        _LOGGER.debug("Logged in — MemberAutoID=%s", self._auto_id)

    async def async_get_plants(self, session: aiohttp.ClientSession) -> list[dict]:
        """Return list of plants, each with its primary inverter's GoodsID."""
        groups = await self._post(session, "/Inverterapi/GroupList",
                                  {"MemberAutoID": self._auto_id})
        plants = []
        for group in groups.get("AllGroupList", []):
            group_id   = group["AutoID"]
            plant_name = group.get("GoodsTypeName", group_id)
            detail     = await self._post(
                session, "/Inverterapi/GroupDetailList",
                {"MemberAutoID": self._auto_id, "GroupAutoID": group_id},
            )
            inverters = detail.get("AllInverterList", [])
            if not inverters:
                continue
            inv = inverters[0]
            plants.append({
                "group_id":   group_id,
                "plant_name": plant_name,
                "goods_id":   inv["GoodsID"],
                "model":      inv.get("ModelName", ""),
                "is_hybrid":  inv.get("isHybrid", False),
            })
        return plants

    # ------------------------------------------------------------------
    # Data endpoints
    # ------------------------------------------------------------------

    async def async_fetch_all(
        self, session: aiohttp.ClientSession, goods_id: str, group_id: str = ""
    ) -> dict[str, Any]:
        """Fetch per-plant stats + hybrid flow + device info.

        MemberMonitor is intentionally NOT used for energy/power values —
        it returns account-wide aggregates that are wrong when multiple plants
        exist. Per-plant energy comes from GroupDetailList (specific group_id).
        MemberMonitor is kept only for the AllLight status indicators.
        """
        monitor = await self._post(
            session, "/Inverterapi/MemberMonitor",
            {"MemberAutoID": self._auto_id},
        )
        # Per-plant energy & power — scoped to this plant's group_id
        plant_stats: dict = {}
        if group_id:
            detail = await self._post(
                session, "/Inverterapi/GroupDetailList",
                {"MemberAutoID": self._auto_id, "GroupAutoID": group_id},
            )
            inverters = detail.get("AllInverterList", [])
            if inverters:
                plant_stats = inverters[0]

        flow = await self._post(
            session, "/Inverterapi/getHybridFlowgraph",
            {"MemberAutoID": self._auto_id, "GoodsID": goods_id},
        )
        info = await self._post(
            session, "/Inverterapi/InverterDetailInfoNewone",
            {"MemberAutoID": self._auto_id, "GoodsID": goods_id},
        )
        return {"monitor": monitor, "plant_stats": plant_stats, "flow": flow, "info": info}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post(
        self,
        session: aiohttp.ClientSession,
        path: str,
        payload: dict,
        auth: bool = True,
    ) -> dict:
        if auth and not payload.get("sign"):
            payload = dict(payload)
            payload["sign"] = _compute_sign(payload)

        headers = {}
        if auth and self._token:
            headers["Authorization"] = self._token

        url = BASE_URL + path
        try:
            async with session.post(
                url, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status in (401, 403):
                    raise CloudInverterAuthError(f"HTTP {resp.status} on {path}")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except CloudInverterAuthError:
            raise
        except aiohttp.ClientError as err:
            raise CloudInverterApiError(f"Request failed for {path}: {err}") from err
