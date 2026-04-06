"""Xiaomi Cloud importer — login with username/password, handle captcha + 2FA.

Ported from v1 token_extractor.py. Handles:
- Normal login
- Captcha (downloads image, shows URL, user types code)
- 2FA email verification (sends email, user pastes code)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import requests

try:
    from Crypto.Cipher import ARC4
except ImportError:
    try:
        from Cryptodome.Cipher import ARC4
    except ImportError:
        ARC4 = None

log = logging.getLogger(__name__)

XIAOMI_REGIONS = {
    "de": "Europe (Germany)",
    "sg": "Asia Pacific (Singapore)",
    "us": "United States",
    "cn": "China",
    "ru": "Russia",
    "tw": "Taiwan",
    "i2": "India",
}

SETUP_STEPS = """\
1. Use the same credentials as your [bold]Mi Home[/bold] app
2. If a captcha appears, open the image URL and type the code
3. If 2FA is required, check your email and paste the code
4. Devices with available tokens will be imported automatically"""


@dataclass
class XiaomiCloudDevice:
    """A device returned from the Xiaomi Cloud."""
    name: str
    device_id: str
    model: str
    token: str
    ip: str
    mac: str
    online: bool


# ── Cloud connector ──────────────────────────────────────────────────────────


class XiaomiCloud:
    """Minimal Xiaomi Cloud client — login + device list."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._agent = self._gen_agent()
        self._session = requests.Session()
        self._ssecurity: str | None = None
        self._service_token: str | None = None
        self.user_id: str | None = None
        self._sign: str | None = None
        self._location: str | None = None
        # Callbacks set by caller for interactive prompts
        self.on_captcha: Callable[[str], str] | None = None  # (image_path) -> code
        self.on_2fa: Callable[[], str] | None = None  # () -> code from email

    @property
    def headers(self) -> dict:
        return {
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    # ── Login flow ───────────────────────────────────────────────────────

    def login(self) -> tuple[bool, str]:
        """Full login flow. Returns (success, error_message)."""
        # Step 1: get sign
        r = self._session.get(
            "https://account.xiaomi.com/pass/serviceLogin",
            params={"sid": "xiaomiio", "_json": "true"},
            headers=self.headers,
            cookies={"userId": self.username},
        )
        data = self._parse(r)
        self._sign = data.get("_sign")

        # Already have ssecurity (e.g. cached session)
        if data.get("ssecurity"):
            self._ssecurity = data["ssecurity"]
            self.user_id = str(data.get("userId", ""))
            self._location = data.get("location")
            if self._location:
                return self._step3()
            return True, ""

        if not self._sign:
            return False, "Failed to get login sign from Xiaomi."

        # Step 2: authenticate
        return self._step2()

    def _step2(self, captcha_code: str = "") -> tuple[bool, str]:
        fields: dict[str, str] = {
            "sid": "xiaomiio",
            "hash": hashlib.md5(self.password.encode()).hexdigest().upper(),
            "callback": "https://sts.api.io.mi.com/sts",
            "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
            "user": self.username,
            "_sign": self._sign or "",
            "_json": "true",
        }
        if captcha_code:
            fields["captCode"] = captcha_code

        r = self._session.post(
            "https://account.xiaomi.com/pass/serviceLoginAuth2",
            headers=self.headers,
            params=fields,
            allow_redirects=False,
        )
        data = self._parse(r)

        # Captcha required
        captcha_url = data.get("captchaUrl")
        if captcha_url:
            if not self.on_captcha:
                return False, "Captcha required but no handler set."
            if captcha_url.startswith("/"):
                captcha_url = "https://account.xiaomi.com" + captcha_url
            # Download captcha image
            img_r = self._session.get(captcha_url)
            img_path = os.path.join(tempfile.gettempdir(), "xiaomi_captcha.png")
            with open(img_path, "wb") as f:
                f.write(img_r.content)
            code = self.on_captcha(img_path)
            if not code:
                return False, "Captcha not solved."
            return self._step2(captcha_code=code)

        # 2FA email verification
        notification_url = data.get("notificationUrl")
        if notification_url and not data.get("ssecurity"):
            return self._do_2fa(notification_url)

        # Check for ssecurity (success)
        if data.get("ssecurity") and len(str(data["ssecurity"])) > 4:
            self._ssecurity = data["ssecurity"]
            self.user_id = str(data.get("userId", ""))
            self._location = data.get("location")
            return self._step3()

        # Wrong credentials
        desc = data.get("desc", data.get("description", "Login failed"))
        return False, f"Login failed: {desc}"

    def _step3(self) -> tuple[bool, str]:
        """Follow location redirect to get serviceToken."""
        if not self._location:
            return False, "No redirect URL."
        r = self._session.get(self._location, headers=self.headers)
        self._service_token = r.cookies.get("serviceToken")
        if not self._service_token:
            return False, "Failed to get service token."
        self._install_cookies()
        return True, ""

    def _do_2fa(self, notification_url: str) -> tuple[bool, str]:
        """Handle email-based 2FA — sends code to email, user types it."""
        if not self.on_2fa:
            return False, "2FA required but no handler set."

        # 1. Open authStart (sets cookies)
        self._session.get(notification_url, headers=self.headers, allow_redirects=True)

        # 2. Get context
        context = parse_qs(urlparse(notification_url).query).get("context", [""])[0]

        # 3. Fetch identity list (sets identity_session cookie — required!)
        self._session.get(
            "https://account.xiaomi.com/identity/list",
            params={"sid": "xiaomiio", "context": context, "_locale": "en_US"},
            headers=self.headers,
        )

        # 4. Send email ticket
        r_send = self._session.post(
            "https://account.xiaomi.com/identity/auth/sendEmailTicket",
            params={"_dc": str(int(time.time() * 1000)), "sid": "xiaomiio",
                    "context": context, "mask": "0", "_locale": "en_US"},
            data={"retry": "0", "icode": "", "_json": "true",
                  "ick": self._session.cookies.get("ick", "")},
            headers=self.headers,
        )
        send_data = self._parse(r_send)
        if send_data.get("code") != 0:
            return False, f"Failed to send verification email: {send_data.get('desc', 'unknown error')}"

        # 5. Ask user for the code
        code = self.on_2fa()
        if not code:
            return False, "2FA code not provided."

        # 6. Verify
        r = self._session.post(
            "https://account.xiaomi.com/identity/auth/verifyEmail",
            params={"_flag": "8", "_json": "true", "sid": "xiaomiio",
                    "context": context, "mask": "0", "_locale": "en_US"},
            data={"_flag": "8", "ticket": code, "trust": "false",
                  "_json": "true", "ick": self._session.cookies.get("ick", "")},
            headers=self.headers,
        )

        # 7. Find finish location
        finish_loc = None
        try:
            jr = r.json()
            finish_loc = jr.get("location")
        except Exception:
            pass
        if not finish_loc:
            finish_loc = r.headers.get("Location")
        if not finish_loc:
            m = re.search(r'https://account\.xiaomi\.com/identity/result/check\?[^"\']+', r.text or "")
            if m:
                finish_loc = m.group(0)
        if not finish_loc:
            r0 = self._session.get(
                "https://account.xiaomi.com/identity/result/check",
                params={"sid": "xiaomiio", "context": context, "_locale": "en_US"},
                headers=self.headers, allow_redirects=False,
            )
            if r0.status_code in (301, 302):
                finish_loc = r0.headers.get("Location")

        if not finish_loc:
            return False, "2FA verification failed — could not find redirect."

        # 8. Follow chain to get ssecurity + serviceToken
        if "identity/result/check" in finish_loc:
            r = self._session.get(finish_loc, headers=self.headers, allow_redirects=False)
            end_url = r.headers.get("Location")
        else:
            end_url = finish_loc

        if not end_url:
            return False, "2FA verification failed — no auth endpoint."

        r = self._session.get(end_url, headers=self.headers, allow_redirects=False)
        if r.status_code == 200 and "Tips" in (r.text or ""):
            r = self._session.get(end_url, headers=self.headers, allow_redirects=False)

        # Extract ssecurity
        ext = r.headers.get("extension-pragma")
        if ext:
            try:
                ep = json.loads(ext)
                if ep.get("ssecurity"):
                    self._ssecurity = ep["ssecurity"]
            except Exception:
                pass

        if not self._ssecurity:
            return False, "2FA completed but couldn't get ssecurity."

        # 8. Follow STS redirect
        sts_url = r.headers.get("Location")
        if not sts_url and r.text:
            idx = (r.text or "").find("https://sts.api.io.mi.com/sts")
            if idx != -1:
                end = r.text.find('"', idx)
                sts_url = r.text[idx:end if end != -1 else idx + 300]

        if not sts_url:
            return False, "2FA completed but no STS redirect."

        r = self._session.get(sts_url, headers=self.headers, allow_redirects=True)
        self._service_token = (
            self._session.cookies.get("serviceToken", domain=".sts.api.io.mi.com")
            or self._session.cookies.get("serviceToken")
        )

        if not self._service_token:
            return False, "2FA completed but no service token."

        self.user_id = (
            self.user_id
            or self._session.cookies.get("userId", domain=".xiaomi.com")
            or self._session.cookies.get("userId")
        )
        self._install_cookies()
        return True, ""

    # ── Device list ──────────────────────────────────────────────────────

    def get_devices(self, region: str) -> tuple[list[dict], str | None]:
        """Fetch device list via homes (v2 API, encrypted)."""
        if ARC4 is None or not self._ssecurity:
            return [], "RC4 encryption not available (install pycryptodome)"

        all_devices: list[dict] = []

        # Step 1: Get all homes (owned + shared)
        homes = self._get_homes(region)
        if not homes:
            return [], None

        # Step 2: Get devices from each home
        for home in homes:
            devices = self._get_home_devices(region, home["home_id"], home["home_owner"])
            all_devices.extend(devices)

        return all_devices, None

    def _get_homes(self, region: str) -> list[dict]:
        """Get all homes (owned + shared family) for a region."""
        homes: list[dict] = []

        # Own homes
        url = self._api_url(region) + "/v2/homeroom/gethome"
        params = {"data": '{"fg": true, "fetch_share": true, "fetch_share_dev": true, "limit": 300, "app_ver": 7}'}
        result = self._encrypted_request(url, params)
        if result and "result" in result:
            for h in result["result"].get("homelist", []):
                homes.append({"home_id": h["id"], "home_owner": self.user_id})

        # Shared family homes
        url2 = self._api_url(region) + "/v2/user/get_device_cnt"
        params2 = {"data": '{ "fetch_own": true, "fetch_share": true}'}
        result2 = self._encrypted_request(url2, params2)
        if result2 and "result" in result2:
            share = result2["result"].get("share", {})
            for h in share.get("share_family", []):
                homes.append({"home_id": h["home_id"], "home_owner": h["home_owner"]})

        return homes

    def _get_home_devices(self, region: str, home_id, owner_id) -> list[dict]:
        """Get devices from a specific home."""
        url = self._api_url(region) + "/v2/home/home_device_list"
        params = {
            "data": '{"home_owner": ' + str(owner_id) +
                    ',"home_id": ' + str(home_id) +
                    ',  "limit": 200,  "get_split_device": true, "support_smart_home": true}'
        }
        result = self._encrypted_request(url, params)
        if result and "result" in result:
            return result["result"].get("device_info", []) or []
        return []

    def _encrypted_request(self, url: str, params: dict) -> dict | None:
        headers = {
            "Accept-Encoding": "identity",
            "User-Agent": self._agent,
            "Content-Type": "application/x-www-form-urlencoded",
            "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": str(self.user_id),
            "yetAnotherServiceToken": str(self._service_token),
            "serviceToken": str(self._service_token),
            "locale": "en_GB",
            "timezone": "GMT+02:00",
            "is_daylight": "1",
            "dst_offset": "3600000",
            "channel": "MI_APP_STORE",
        }
        millis = round(time.time() * 1000)
        nonce = self._gen_nonce(millis)
        signed_nonce = self._signed_nonce(nonce)
        fields = self._gen_enc_params(url, "POST", signed_nonce, nonce, params, self._ssecurity)
        r = self._session.post(url, headers=headers, cookies=cookies, params=fields)
        if r.status_code == 200:
            decoded = self._decrypt_rc4(self._signed_nonce(fields["_nonce"]), r.text)
            return json.loads(decoded)
        return None

    # ── Helpers ───────────────────────────────────────────────────────────

    def _install_cookies(self):
        """Set serviceToken on all API domains."""
        if not self._service_token:
            return
        for domain in [".mi.com", ".xiaomi.com", ".sts.api.io.mi.com"]:
            self._session.cookies.set("serviceToken", self._service_token, domain=domain)

    @staticmethod
    def _api_url(region: str) -> str:
        return "https://" + ("" if region == "cn" else f"{region}.") + "api.io.mi.com/app"

    @staticmethod
    def _parse(r: requests.Response) -> dict:
        text = r.text.replace("&&&START&&&", "")
        try:
            return json.loads(text)
        except Exception:
            return {}

    @staticmethod
    def _gen_agent() -> str:
        agent_id = "".join(chr(random.randint(65, 69)) for _ in range(13))
        rand = "".join(chr(random.randint(97, 122)) for _ in range(18))
        return f"{rand}-{agent_id} APP/com.xiaomi.mihome APPV/10.5.201"

    @staticmethod
    def _gen_nonce(millis: int) -> str:
        nonce_bytes = os.urandom(8) + (millis // 60000).to_bytes(4, byteorder="big")
        return base64.b64encode(nonce_bytes).decode()

    def _signed_nonce(self, nonce: str) -> str:
        h = hashlib.sha256(
            base64.b64decode(self._ssecurity or "") + base64.b64decode(nonce)
        )
        return base64.b64encode(h.digest()).decode()

    @staticmethod
    def _gen_enc_params(url, method, signed_nonce, nonce, params, ssecurity):
        params["rc4_hash__"] = XiaomiCloud._gen_enc_signature(url, method, signed_nonce, params)
        for k, v in params.items():
            params[k] = XiaomiCloud._encrypt_rc4(signed_nonce, v)
        params.update({"signature": XiaomiCloud._gen_enc_signature(url, method, signed_nonce, params),
                       "ssecurity": ssecurity or "", "_nonce": nonce})
        return params

    @staticmethod
    def _gen_enc_signature(url, method, signed_nonce, params):
        signature_params = [str(method).upper(), url.split("com")[1].replace("/app/", "/")]
        for k, v in params.items():
            signature_params.append(f"{k}={v}")
        signature_params.append(signed_nonce)
        signature_string = "&".join(signature_params)
        return base64.b64encode(
            hashlib.sha1(signature_string.encode()).digest()
        ).decode()

    @staticmethod
    def _encrypt_rc4(password, payload):
        r = ARC4.new(base64.b64decode(password))
        r.encrypt(bytes(1024))
        return base64.b64encode(r.encrypt(payload.encode())).decode()

    @staticmethod
    def _decrypt_rc4(password, payload):
        r = ARC4.new(base64.b64decode(password))
        r.encrypt(bytes(1024))
        return r.decrypt(base64.b64decode(payload))


# ── Public API ───────────────────────────────────────────────────────────────


def fetch_devices(
    username: str,
    password: str,
    region: str = "de",
    on_captcha: Callable[[str], str] | None = None,
    on_2fa: Callable[[], str] | None = None,
    scan_all_regions: bool = False,
) -> tuple[list[XiaomiCloudDevice], str | None]:
    """Login and fetch all devices.

    Args:
        on_captcha: Called with path to captcha image, must return the code.
        on_2fa: Called when email 2FA is needed, must return the code from email.
        scan_all_regions: If True, scan all regions (not just the selected one).
    """
    cloud = XiaomiCloud(username, password)
    cloud.on_captcha = on_captcha
    cloud.on_2fa = on_2fa

    ok, err = cloud.login()
    if not ok:
        return [], err

    # Determine which regions to scan
    regions = list(XIAOMI_REGIONS.keys()) if scan_all_regions else [region]

    all_raw: list[dict] = []
    last_err: str | None = None
    for r in regions:
        raw, err = cloud.get_devices(r)
        if raw:
            all_raw.extend(raw)
        elif err:
            last_err = err

    if not all_raw:
        return [], last_err

    seen_ids: set[str] = set()
    devices: list[XiaomiCloudDevice] = []
    for d in all_raw:
        did = d.get("did", "")
        if did in seen_ids:
            continue
        seen_ids.add(did)

        token = d.get("token", "")
        if not token or token == "ffffffffffffffffffffffffffffffff" or len(token) < 8:
            continue
        devices.append(XiaomiCloudDevice(
            name=d.get("name", "Unknown"),
            device_id=did,
            model=d.get("model", ""),
            token=token,
            ip=d.get("localip", ""),
            mac=d.get("mac", ""),
            online=d.get("isOnline", False),
        ))

    return devices, None
