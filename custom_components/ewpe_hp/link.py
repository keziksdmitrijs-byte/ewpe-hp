"""How packs reach a unit through the cloud.

Wi-Fi modules from protocol 3.2 on are reached over the cloud's MQTT broker: a pack is published to
request/<module> and the answer comes on response/<module>/..., changes the unit reports by itself on
status/<module>/... Older modules keep a TLS session to a gateway of their own, found with QueryOnline;
one line goes there, one line comes back. Either way the pack is the unit's own JSON, AES-encrypted
with its key.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import ssl
from collections.abc import Callable
from typing import Any

import aiomqtt

from .cloud import AuthError, Cloud, CloudError, CloudUnit, Gateway
from .const import MQTT_FROM_VERSION, MQTT_PORT, MQTT_TIMEOUT, REQUEST_TIMEOUT
from .crypto import open_pack, seal

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[dict[str, Any]], None]


class LinkError(Exception):
    """The unit did not answer."""


class UnitOffline(LinkError):
    """The cloud says the unit is not online."""


def protocol(version: str | None) -> tuple[int, ...] | None:
    """'V3.5.0' -> (3, 5, 0); None when there is no number in it."""
    parts: list[int] = []
    for chunk in (version or "").strip().lstrip("vV").split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or None


def over_mqtt(unit: CloudUnit) -> bool:
    """Whether a unit is first tried over MQTT: yes unless its module is known to be older."""
    parsed = protocol(unit.version)
    return parsed is None or parsed >= MQTT_FROM_VERSION


def _insecure_tls() -> ssl.SSLContext:
    """Gree's broker and gateways carry certificates from Gree's own CA, which the app does not check either."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def envelope(uid: int | None, unit: CloudUnit, message: dict[str, Any], cid: str) -> dict[str, Any]:
    return {"cid": cid, "i": 0, "pack": seal(unit.key, message), "t": "pack", "tcid": unit.mac, "uid": uid}


class MqttLink:
    """One MQTT session for the whole account, kept up in the background."""

    def __init__(self, cloud: Cloud, broker: str) -> None:
        self._cloud = cloud
        self._broker = broker
        self._client: Any = None
        self._connected = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._units: dict[str, CloudUnit] = {}
        self._listeners: dict[str, Listener] = {}
        self._waiting: dict[str, asyncio.Future] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.auth_failed = False

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run(), name="ewpe_hp mqtt")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def add(self, unit: CloudUnit, listener: Listener) -> None:
        """Answers and reports of this unit; reports go to the listener as plain values."""
        self._units[unit.module] = unit
        self._listeners[unit.mac] = listener
        if self._connected.is_set():
            await self._subscribe(unit.module)

    async def _subscribe(self, module: str) -> None:
        for topic in (f"response/{module}/#", f"status/{module}/#", f"connect/{module}"):
            await self._client.subscribe(topic, qos=1)
        _LOGGER.debug("Subscribed to %s", module)

    async def _run(self) -> None:
        backoff = 5
        while True:
            try:
                if self._cloud.token is None:
                    await self._cloud.login()
                async with aiomqtt.Client(
                    hostname=self._broker,
                    port=MQTT_PORT,
                    username=str(self._cloud.uid),
                    password=self._cloud.token,
                    identifier=f"app_{secrets.token_hex(8)}",
                    keepalive=60,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    clean_session=True,
                    tls_context=_insecure_tls(),
                    timeout=30,
                ) as client:
                    self._client = client
                    for module in list(self._units):
                        await self._subscribe(module)
                    self._connected.set()
                    self.auth_failed = False
                    backoff = 5
                    _LOGGER.debug("Connected to %s", self._broker)
                    async for message in client.messages:
                        self._received(str(message.topic), message.payload)
            except asyncio.CancelledError:
                raise
            except AuthError as err:
                self.auth_failed = True
                _LOGGER.warning("Gree+ account refused: %s", err)
            except (aiomqtt.MqttError, CloudError, OSError) as err:
                _LOGGER.debug("MQTT link to %s down: %s", self._broker, err)
                # an expired token is the usual reason the broker turns the session down
                if "auth" in str(err).lower() or "code:5" in str(err) or "code:4" in str(err):
                    self._cloud.token = None
            finally:
                self._connected.clear()
                self._client = None
                for future in self._waiting.values():
                    if not future.done():
                        future.set_exception(LinkError("MQTT link lost"))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)

    def _received(self, topic: str, payload: bytes | str) -> None:
        parts = topic.split("/")
        _LOGGER.debug("Message on %s (%s bytes)", topic, len(payload or b""))
        if len(parts) < 2 or parts[0] not in ("response", "status"):
            return
        unit = self._units.get(parts[1]) or next(
            (known for module, known in self._units.items() if module.lower() == parts[1].lower()), None
        )
        if unit is None:
            _LOGGER.debug("Message on %s is for no known unit", topic)
            return
        try:
            outer = json.loads(payload)
            message = open_pack(unit.key, outer["pack"]) if outer.get("pack") else outer
        except (ValueError, KeyError, TypeError) as err:
            _LOGGER.debug("Unreadable message on %s: %s", topic, err)
            return
        _LOGGER.debug("%s sent a %r pack (r=%s) on %s", unit.name, message.get("t"), message.get("r"), parts[0])
        if parts[0] == "response":
            waiting = self._waiting.get(unit.module)
            if waiting and not waiting.done():
                waiting.set_result(message)
            else:
                _LOGGER.debug("%s answered after its request had given up", unit.name)
            return
        values = values_of(message)
        listener = self._listeners.get(unit.mac)
        if values and listener:
            listener(values)

    async def request(self, unit: CloudUnit, message: dict[str, Any], wait: float | None = None) -> dict[str, Any]:
        lock = self._locks.setdefault(unit.module, asyncio.Lock())
        async with lock:
            try:
                await asyncio.wait_for(self._connected.wait(), REQUEST_TIMEOUT)
            except TimeoutError as err:
                raise LinkError("No MQTT link to the cloud") from err
            timeout = wait or MQTT_TIMEOUT
            future = asyncio.get_running_loop().create_future()
            self._waiting[unit.module] = future
            try:
                body = envelope(self._cloud.uid, unit, message, str(secrets.randbelow(9_000_000_000) + 1_000_000_000))
                await self._client.publish(f"request/{unit.module}", json.dumps(body), qos=1)
                _LOGGER.debug("Asked %s for %r on request/%s", unit.name, message.get("t"), unit.module)
                return await asyncio.wait_for(future, timeout)
            except TimeoutError as err:
                raise LinkError(f"{unit.name} did not answer") from err
            except aiomqtt.MqttError as err:
                raise LinkError(str(err)) from err
            finally:
                self._waiting.pop(unit.module, None)


class GatewayLink:
    """Units with an older Wi-Fi module: one connection per request to the gateway the cloud names."""

    def __init__(self, cloud: Cloud) -> None:
        self._cloud = cloud
        self._gateways: dict[str, Gateway] = {}

    async def request(self, unit: CloudUnit, message: dict[str, Any], wait: float | None = None) -> dict[str, Any]:
        timeout = wait or REQUEST_TIMEOUT
        gateway = self._gateways.get(unit.module)
        if gateway is None:
            gateway = await self._cloud.gateway(unit.module)
            if gateway is None:
                raise UnitOffline(f"{unit.name} is offline")
            self._gateways[unit.module] = gateway
        line = json.dumps(envelope(self._cloud.uid, unit, message, "app"), separators=(",", ":")).encode() + b"\n"
        _LOGGER.debug("Asking %s for %r through %s:%s", unit.name, message.get("t"), gateway.host, gateway.port)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(gateway.host, gateway.port, ssl=_insecure_tls() if gateway.tls else None),
                timeout,
            )
        except (OSError, TimeoutError) as err:
            # the unit may have moved to another gateway
            self._gateways.pop(unit.module, None)
            raise LinkError(f"Gateway of {unit.name}: {err}") from err
        try:
            writer.write(line)
            await writer.drain()
            answer = await asyncio.wait_for(reader.readline(), timeout)
        except (OSError, TimeoutError) as err:
            self._gateways.pop(unit.module, None)
            raise LinkError(f"{unit.name} did not answer") from err
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
        if not answer:
            self._gateways.pop(unit.module, None)
            raise LinkError(f"The gateway closed the connection without an answer from {unit.name}")
        try:
            outer = json.loads(answer)
            return open_pack(unit.key, outer["pack"]) if outer.get("pack") else outer
        except (ValueError, KeyError, TypeError) as err:
            raise LinkError(f"Unreadable answer from {unit.name}") from err


def values_of(message: dict[str, Any]) -> dict[str, Any]:
    """Values in a pack: status data ('dat') or what a command or report set ('res', 'p'/'val')."""
    names = message.get("cols") or message.get("opt") or []
    values = message.get("dat") if "dat" in message else message.get("p", message.get("val"))
    if not isinstance(names, list) or not isinstance(values, list):
        return {}
    return dict(zip(names, values, strict=False))
