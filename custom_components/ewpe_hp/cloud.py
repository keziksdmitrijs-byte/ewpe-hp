"""The Gree+ (EWPE) cloud account: sign-in, the account's units and where older units can be reached."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiohttp

from .const import APP_HASH, APP_HEADER, APP_ID, APP_KEY, REQUEST_TIMEOUT
from .crypto import decrypt, encrypt

_LOGGER = logging.getLogger(__name__)


class CloudError(Exception):
    """The cloud could not be reached or did not answer as expected."""


class AuthError(CloudError):
    """The cloud turned the account down."""


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def password_hash(password: str) -> str:
    """What the cloud signs in with: the password itself is not needed again, so it is not kept."""
    return md5(md5(password) + password)


@dataclass(frozen=True)
class CloudUnit:
    """A unit of the account, as the cloud lists it."""

    mac: str
    name: str
    key: str
    model: str | None = None
    version: str | None = None
    online: bool = True
    # the Wi-Fi module a unit is behind, when it is not its own
    parent: str | None = None

    @property
    def module(self) -> str:
        return self.parent or self.mac

    def summary(self) -> dict[str, Any]:
        """The unit without its key, for logs and diagnostics."""
        return {"mac": self.mac, "name": self.name, "model": self.model, "version": self.version, "online": self.online}


@dataclass(frozen=True)
class Gateway:
    host: str
    port: int
    tls: bool


class Cloud:
    """One Gree+ account in one region."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, user: str, hashed: str) -> None:
        self._session = session
        self._base_url = base_url
        self.user = user
        self._hashed = hashed
        self.uid: int | None = None
        self.token: str | None = None

    async def _call(self, path: str, payload: dict[str, Any], signed: list[str]) -> dict[str, Any]:
        now = datetime.now(UTC)
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        moment = int(now.timestamp())
        values = ["_".join(map(str, payload[name])) if isinstance(payload[name], list) else str(payload[name]) for name in signed]
        body = {
            "api": {"appId": APP_ID, "r": moment, "t": stamp, "vc": md5(f"{APP_ID}_{APP_HASH}_{stamp}_{moment}")},
            "datVc": md5(f"{APP_HASH}_{'_'.join(values)}"),
            **payload,
        }
        sealed = base64.b64encode(encrypt(APP_KEY, json.dumps(body).encode())).decode()
        try:
            async with self._session.post(
                f"{self._base_url}{path}",
                data=sealed,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Gaen1": APP_HEADER, "Charset": "utf-8"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT * 3),
            ) as response:
                if response.status != 200:
                    raise CloudError(f"{path}: HTTP {response.status}")
                answer = await response.json(content_type=None)
            return json.loads(decrypt(APP_KEY, base64.b64decode(answer["enRes"])).decode())
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CloudError(f"{path}: {err}") from err
        except (KeyError, TypeError, ValueError) as err:
            raise CloudError(f"{path}: unexpected answer") from err

    async def login(self) -> None:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        answer = await self._call(
            "/App/UserLoginV2",
            {"psw": md5(self._hashed + stamp), "t": stamp, "user": self.user},
            ["user", "psw", "t"],
        )
        data = answer.get("data") if isinstance(answer.get("data"), dict) else answer
        if answer.get("r", 200) != 200 or not data.get("uid") or not data.get("token"):
            raise AuthError(str(answer.get("msg") or "Sign-in refused"))
        self.uid = data["uid"]
        self.token = data["token"]

    async def _signed_in(self, path: str, payload: dict[str, Any], signed: list[str]) -> dict[str, Any]:
        """A call on the account; the token is renewed once when the cloud no longer takes it."""
        for attempt in (1, 2):
            if self.token is None:
                await self.login()
            answer = await self._call(path, {"token": self.token, "uid": self.uid, **payload}, ["token", "uid", *signed])
            if answer.get("r", 200) == 200:
                return answer
            if attempt == 1:
                _LOGGER.debug("%s answered %s, signing in again", path, answer.get("r"))
                self.token = None
        raise CloudError(f"{path}: {answer.get('msg') or answer.get('r')}")

    async def units(self) -> list[CloudUnit]:
        """Every unit of every home of the account. A module that other units name as theirs is not a unit itself."""
        homes = (await self._signed_in("/App/GetHomes", {}, [])).get("home") or []
        found: list[CloudUnit] = []
        for home in homes:
            rooms = (await self._signed_in("/App/GetDevsInRoomsOfHomeV2", {"homeId": home["id"]}, ["homeId"])).get("rooms") or []
            for room in rooms:
                for dev in room.get("devs") or []:
                    found.append(
                        CloudUnit(
                            mac=str(dev["mac"]).strip(),
                            name=str(dev.get("name") or dev["mac"]).strip(),
                            key=str(dev["key"]).strip(),
                            model=(str(dev["model"]).strip() or None) if dev.get("model") else None,
                            version=(str(dev["ver"]).strip() or None) if dev.get("ver") else None,
                            online=bool(dev.get("online", 1)),
                            parent=(str(dev.get("pmac") or "").strip() or None),
                        )
                    )
        modules = {unit.parent for unit in found if unit.parent}
        units = {unit.mac: unit for unit in found if unit.mac not in modules}
        return list(units.values())

    async def gateway(self, mac: str) -> Gateway | None:
        """Where a unit on the older, pre-MQTT link is reached; None when it is offline."""
        answer = await self._signed_in("/App/QueryOnline", {"macs": [mac]}, ["macs"])
        for item in answer.get("online") or []:
            server = str(item.get("svr") or "")
            if item.get("mac") == mac and ":" in server:
                host, port = server.rsplit(":", 1)
                return Gateway(host, int(port), bool(item.get("isSSL")))
        return None
