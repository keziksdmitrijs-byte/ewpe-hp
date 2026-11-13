"""A Gree+ cloud, its MQTT broker and a Versati unit, enough to test against.

The cloud checks what the real one is known to check: the app's signature, the request's own signature
and the password hash; the unit answers packs encrypted with its key.
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import Any

from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.ewpe_hp.cloud import md5, password_hash
from custom_components.ewpe_hp.const import APP_HASH, APP_ID, APP_KEY
from custom_components.ewpe_hp.crypto import decrypt, encrypt, open_pack, seal

EMAIL = "owner@example.com"
PASSWORD = "secret-password"
UID = 4242
MAC = "c8f742a1b2c3"
KEY = "Ab12Cd34Ef56Gh78"


class Versati:
    """The unit: values by parameter name, as a Versati IV would hold them."""

    def __init__(self, mac: str = MAC, key: str = KEY, version: str = "V3.5.0") -> None:
        self.mac = mac
        self.key = key
        self.version = version
        self.online = True
        self.values: dict[str, Any] = {
            "Pow": 1,
            "Mod": 4,
            "Quiet": 0,
            "HeWatOutTemSet": 35,
            "CoWatOutTemSet": 18,
            "WatBoxTemSet": 48,
            "HeHomTemSet": 22,
            "CoHomTemSet": 25,
            "FastHtWter": 0,
            "HetHtWter": 1,
            "ColHtWter": 0,
            "TemUn": 0,
            "AllErr": 0,
            "AllOutWatTemHi": 134,
            "AllOutWatTemLo": 5,
            "AllInWatTemHi": 130,
            "AllInWatTemLo": 7,
            "HepOutWatTemHi": 134,
            "HepOutWatTemLo": 2,
            "WatBoxTemHi": 146,
            "WatBoxTemLo": 3,
            # no room sensor fitted
            "RmoHomTemHi": 70,
            "RmoHomTemLo": 0,
            "WatBoxElcHeRunSta": 0,
            "ElcHe1RunSta": 0,
            "ElcHe2RunSta": 0,
            "AnFrzzRunSta": 0,
            "SyAnFroRunSta": 0,
        }
        self.commands: list[dict[str, Any]] = []
        self.status_requests: list[list[str]] = []
        self.refuse: set[str] = set()

    def answer(self, message: dict[str, Any]) -> dict[str, Any]:
        if message["t"] == "status":
            self.status_requests.append(message["cols"])
            # a parameter the unit does not know gets no value in the answer
            cols = [name for name in message["cols"] if name in self.values]
            return {"t": "dat", "r": 200, "mac": self.mac, "cols": cols, "dat": [self.values[name] for name in cols]}
        if message["t"] == "cmd":
            self.commands.append(dict(zip(message["opt"], message["p"], strict=True)))
            if self.refuse & set(message["opt"]):
                return {"t": "res", "r": 400, "mac": self.mac}
            self.values.update(zip(message["opt"], message["p"], strict=True))
            return {
                "t": "res",
                "r": 200,
                "mac": self.mac,
                "opt": message["opt"],
                "p": message["p"],
                "val": message["p"],
            }
        return {"t": "res", "r": 404}


class Cloud:
    """The REST side of the cloud."""

    def __init__(self, unit: Versati) -> None:
        self.unit = unit
        self.token = "token-1"
        self.logins = 0
        self.gateway: tuple[str, int] | None = None
        self.down = False

    def _check(self, body: dict[str, Any], signed: list[str]) -> None:
        api = body["api"]
        assert api["appId"] == APP_ID
        assert api["vc"] == md5(f"{APP_ID}_{APP_HASH}_{api['t']}_{api['r']}")
        values = ["_".join(map(str, body[name])) if isinstance(body[name], list) else str(body[name]) for name in signed]
        assert body["datVc"] == md5(f"{APP_HASH}_{'_'.join(values)}")
        datetime.strptime(api["t"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)

    def _signed_in(self, body: dict[str, Any]) -> bool:
        return body.get("token") == self.token and body.get("uid") == UID

    def handle(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path == "/App/UserLoginV2":
            self._check(body, ["user", "psw", "t"])
            if body["user"] != EMAIL or body["psw"] != md5(password_hash(PASSWORD) + body["t"]):
                return {"r": 4012, "msg": "user or password error"}
            self.logins += 1
            return {"r": 200, "uid": UID, "token": self.token}
        if path == "/App/GetHomes":
            self._check(body, ["token", "uid"])
            if not self._signed_in(body):
                return {"r": 402, "msg": "token expired"}
            return {"r": 200, "home": [{"id": 77, "name": " Home "}]}
        if path == "/App/GetDevsInRoomsOfHomeV2":
            self._check(body, ["token", "uid", "homeId"])
            if not self._signed_in(body) or body["homeId"] != 77:
                return {"r": 402}
            unit = self.unit
            return {
                "r": 200,
                "rooms": [
                    {
                        "devs": [
                            {
                                "mac": unit.mac,
                                "name": "Versati IV ",
                                "key": unit.key,
                                "model": "GRS-CQ8.0Pd/NhG4-E",
                                "ver": unit.version,
                                "online": 1,
                                "pmac": "",
                                "mid": "10001",
                            }
                        ]
                    }
                ],
            }
        if path == "/App/QueryOnline":
            self._check(body, ["token", "uid", "macs"])
            if not self._signed_in(body):
                return {"r": 402}
            online = []
            if self.gateway and self.unit.online and self.unit.mac in body["macs"]:
                online.append({"mac": self.unit.mac, "svr": f"{self.gateway[0]}:{self.gateway[1]}", "isSSL": False})
            return {"r": 200, "online": online}
        return {"r": 404}

    async def side_effect(self, method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        if self.down:
            return AiohttpClientMockResponse(method, url, status=503)
        body = json.loads(decrypt(APP_KEY, base64.b64decode(data)).decode())
        answer = self.handle(url.path, body)
        sealed = base64.b64encode(encrypt(APP_KEY, json.dumps(answer).encode())).decode()
        return AiohttpClientMockResponse(method, url, json={"enRes": sealed})


class _Message:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class Broker:
    """The cloud's MQTT broker with the unit behind it; hands out clients shaped like aiomqtt.Client."""

    def __init__(self, cloud: Cloud) -> None:
        self.cloud = cloud
        self.clients: list[BrokerClient] = []
        self.connections: list[dict[str, Any]] = []
        self.silent = False
        self.refuse = False

    def __call__(self, **kwargs: Any) -> BrokerClient:
        self.connections.append(kwargs)
        client = BrokerClient(self, kwargs)
        self.clients.append(client)
        return client

    def report(self, values: dict[str, Any]) -> None:
        """The unit reports a change by itself."""
        unit = self.cloud.unit
        unit.values.update(values)
        pack = seal(unit.key, {"t": "res", "r": 200, "opt": list(values), "p": list(values.values())})
        for client in self.clients:
            client.deliver(f"status/{unit.mac}/x", {"t": "pack", "pack": pack, "tcid": "app", "cid": unit.mac})


class BrokerClient:
    def __init__(self, broker: Broker, settings: dict[str, Any]) -> None:
        self._broker = broker
        self._settings = settings
        self._queue: asyncio.Queue[_Message | None] = asyncio.Queue()
        self.subscriptions: list[str] = []

    async def __aenter__(self) -> BrokerClient:
        import aiomqtt

        cloud = self._broker.cloud
        if self._broker.refuse or self._settings["password"] != cloud.token or self._settings["username"] != str(UID):
            raise aiomqtt.MqttError("Connection refused: code:5 not authorised")
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self._queue.put_nowait(None)
        if self in self._broker.clients:
            self._broker.clients.remove(self)

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscriptions.append(topic)

    def deliver(self, topic: str, message: dict[str, Any]) -> None:
        module = topic.split("/")[1]
        if any(sub.split("/")[1] == module and sub.startswith(topic.split("/")[0]) for sub in self.subscriptions):
            self._queue.put_nowait(_Message(topic, json.dumps(message).encode()))

    async def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        unit = self._broker.cloud.unit
        outer = json.loads(payload)
        assert topic == f"request/{unit.mac}"
        assert outer["tcid"] == unit.mac and outer["uid"] == UID and outer["t"] == "pack"
        if self._broker.silent or not unit.online:
            return
        answer = unit.answer(open_pack(unit.key, outer["pack"]))
        self.deliver(
            f"response/{unit.mac}/{outer['cid']}",
            {"t": "pack", "i": 0, "pack": seal(unit.key, answer), "cid": unit.mac, "tcid": "app"},
        )

    @property
    def messages(self) -> Any:
        return self._iterate()

    async def _iterate(self) -> Any:
        while True:
            message = await self._queue.get()
            if message is None:
                return
            yield message


async def gateway_server(cloud: Cloud) -> asyncio.Server:
    """The gateway an older Wi-Fi module keeps its session with: one line in, one line out."""
    unit = cloud.unit

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        outer = json.loads(line)
        message = open_pack(unit.key, outer["pack"])
        # the gateway passes a status request on only when the pack names the unit
        named = message["t"] != "status" or message.get("mac") == unit.mac
        if outer["tcid"] == unit.mac and outer["uid"] == UID and named:
            answer = unit.answer(message)
            reply = {"t": "pack", "i": 0, "pack": seal(unit.key, answer), "cid": unit.mac, "tcid": "app"}
            writer.write(json.dumps(reply).encode() + b"\n")
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    cloud.gateway = ("127.0.0.1", server.sockets[0].getsockname()[1])
    return server
