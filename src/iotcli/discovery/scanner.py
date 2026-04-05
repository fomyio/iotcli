"""Network discovery scanner — async multi-protocol scan with progress callback."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import aiohttp

try:
    import netifaces
except ImportError:
    netifaces = None  # type: ignore[assignment]


@dataclass
class ScanConfig:
    timeout: float = 5.0
    max_workers: int = 100
    miio_timeout: float = 0.5
    tuya_timeout: float = 2.0
    http_timeout: float = 0.3
    mqtt_timeout: float = 0.3


@dataclass
class ScanResult:
    protocol: str
    devices: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0


class DiscoveryScanner:
    """Discovers IoT devices on the local network using asyncio."""

    def __init__(
        self,
        verbose: bool = False,
        debug: bool = False,
        config: ScanConfig | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
        on_device_found: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.verbose = verbose
        self.debug = debug
        self.config = config or ScanConfig()
        self.on_progress = on_progress
        self.on_device_found = on_device_found
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _progress(self, protocol: str, current: int, total: int) -> None:
        if self.on_progress:
            self.on_progress(protocol, current, total)

    def _found(self, device: dict[str, Any]) -> None:
        if self.on_device_found:
            self.on_device_found(device)

    # -- public API -----------------------------------------------------------

    def discover_sync(
        self, network: str | None = None, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        """Synchronous entry point for CLI."""
        return asyncio.run(self.discover(network, timeout))

    async def discover(
        self, network: str | None = None, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        if timeout:
            self.config.timeout = timeout
        if not network:
            network = self._detect_network()
        self._cancelled = False

        sem = asyncio.Semaphore(self.config.max_workers)
        tasks = [
            self._wrap("miIO", self._scan_miio, network, sem),
            self._wrap("Tuya", self._scan_tuya, network, sem),
            self._wrap("HTTP", self._scan_http, network, sem),
            self._wrap("MQTT", self._scan_mqtt, network, sem),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        devices: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, ScanResult):
                devices.extend(r.devices)
        return devices

    async def _wrap(self, name, fn, network, sem) -> ScanResult:
        t0 = time.monotonic()
        try:
            devs = await fn(network, sem)
            return ScanResult(name, devs, duration=time.monotonic() - t0)
        except Exception as e:
            return ScanResult(name, errors=[str(e)], duration=time.monotonic() - t0)

    # -- network detection ----------------------------------------------------

    def _detect_network(self) -> str:
        if netifaces:
            try:
                gw = netifaces.gateways()
                iface = gw["default"][netifaces.AF_INET][1]
                addr = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]
                net = ipaddress.IPv4Network(f"{addr['addr']}/{addr['netmask']}", strict=False)
                return str(net)
            except Exception:
                pass
        return "192.168.1.0/24"

    # -- miIO -----------------------------------------------------------------

    async def _scan_miio(self, network: str, sem: asyncio.Semaphore) -> list[dict]:
        devices: list[dict] = []
        seen: set[str] = set()
        hosts = list(ipaddress.IPv4Network(network, strict=False).hosts())
        hello = bytes.fromhex(
            "21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        )
        total = len(hosts)
        done = 0

        async def probe(ip: ipaddress.IPv4Address) -> dict | None:
            nonlocal done
            if self._cancelled:
                return None
            ip_s = str(ip)
            async with sem:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.setblocking(False)
                    sock.sendto(hello, (ip_s, 54321))
                    loop = asyncio.get_event_loop()
                    data = await asyncio.wait_for(
                        loop.sock_recv(sock, 1024), timeout=self.config.miio_timeout
                    )
                    sock.close()
                    if len(data) >= 32 and data[:2] == b"\x21\x31" and ip_s not in seen:
                        seen.add(ip_s)
                        dev_id = struct.unpack(">I", data[8:12])[0]
                        d = {
                            "name": f"Xiaomi Device {dev_id}",
                            "protocol": "miio",
                            "ip": ip_s,
                            "port": 54321,
                            "device_id": dev_id,
                            "status": "discovered",
                            "missing_info": ["token"],
                        }
                        self._found(d)
                        return d
                except Exception:
                    pass
                finally:
                    done += 1
                    if done % 20 == 0:
                        self._progress("miIO", done, total)
            return None

        results = await asyncio.gather(*(probe(ip) for ip in hosts), return_exceptions=True)
        devices = [r for r in results if isinstance(r, dict)]
        self._progress("miIO", total, total)
        return devices

    # -- Tuya -----------------------------------------------------------------

    async def _scan_tuya(self, network: str, sem: asyncio.Semaphore) -> list[dict]:
        devices: list[dict] = []
        seen: set[str] = set()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            bound = False
            for port in [6667, 6668]:
                try:
                    sock.bind(("", port))
                    bound = True
                    break
                except Exception:
                    continue
            if not bound:
                return devices
            t0 = time.monotonic()
            while time.monotonic() - t0 < self.config.tuya_timeout and not self._cancelled:
                try:
                    loop = asyncio.get_event_loop()
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 1024), timeout=0.5
                    )
                    ip_s = addr[0]
                    if ip_s not in seen and data.startswith(b"{"):
                        seen.add(ip_s)
                        info = json.loads(data.decode())
                        d = {
                            "name": info.get("gwId", f"Tuya {ip_s}"),
                            "protocol": "tuya",
                            "ip": ip_s,
                            "port": 6668,
                            "device_id": info.get("gwId"),
                            "status": "discovered",
                            "missing_info": ["local_key"],
                        }
                        self._found(d)
                        devices.append(d)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
            sock.close()
        except Exception:
            pass
        return devices

    # -- HTTP -----------------------------------------------------------------

    async def _scan_http(self, network: str, sem: asyncio.Semaphore) -> list[dict]:
        devices: list[dict] = []
        seen: set[str] = set()
        hosts = list(ipaddress.IPv4Network(network, strict=False).hosts())
        ports = [80, 8080, 8000]
        total = len(hosts) * len(ports)
        done = 0

        timeout = aiohttp.ClientTimeout(total=self.config.http_timeout)
        connector = aiohttp.TCPConnector(limit=self.config.max_workers, force_close=True)

        async def probe(ip: ipaddress.IPv4Address, port: int) -> dict | None:
            nonlocal done
            if self._cancelled:
                return None
            ip_s = str(ip)
            if ip_s in seen:
                return None
            async with sem:
                for ep in ["/api/info", "/cm?cmnd=Status", "/"]:
                    try:
                        async with aiohttp.ClientSession(
                            connector=connector, timeout=timeout
                        ) as session:
                            async with session.get(
                                f"http://{ip_s}:{port}{ep}", allow_redirects=False
                            ) as r:
                                if r.status == 200:
                                    text = await r.text()
                                    d = self._parse_http(text, ip_s, port)
                                    if d and ip_s not in seen:
                                        seen.add(ip_s)
                                        self._found(d)
                                        return d
                    except Exception:
                        continue
                done += 1
                if done % 20 == 0:
                    self._progress("HTTP", done, total)
            return None

        results = await asyncio.gather(
            *(probe(ip, p) for ip in hosts for p in ports), return_exceptions=True
        )
        devices = [r for r in results if isinstance(r, dict)]
        await connector.close()
        self._progress("HTTP", total, total)
        return devices

    def _parse_http(self, text: str, ip: str, port: int) -> dict | None:
        try:
            if text.strip().startswith("{"):
                info = json.loads(text)
                s = str(info).lower()
                if "esphome" in s:
                    return {
                        "name": info.get("name", f"ESPHome {ip}"),
                        "protocol": "http",
                        "ip": ip,
                        "port": port,
                        "device_type": "esphome",
                        "status": "discovered",
                        "missing_info": [],
                    }
                if "tasmota" in s or "Status" in info:
                    return {
                        "name": info.get("Status", {}).get("DeviceName", f"Tasmota {ip}"),
                        "protocol": "http",
                        "ip": ip,
                        "port": port,
                        "device_type": "tasmota",
                        "status": "discovered",
                        "missing_info": [],
                    }
            if "ESP" in text or "Tasmota" in text:
                return {
                    "name": f"HTTP Device {ip}",
                    "protocol": "http",
                    "ip": ip,
                    "port": port,
                    "device_type": "generic",
                    "status": "discovered",
                    "missing_info": [],
                }
        except Exception:
            pass
        return None

    # -- MQTT -----------------------------------------------------------------

    async def _scan_mqtt(self, network: str, sem: asyncio.Semaphore) -> list[dict]:
        devices: list[dict] = []
        hosts = list(ipaddress.IPv4Network(network, strict=False).hosts())
        total = len(hosts)
        done = 0

        async def probe(ip: ipaddress.IPv4Address) -> dict | None:
            nonlocal done
            if self._cancelled:
                return None
            ip_s = str(ip)
            async with sem:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip_s, 1883),
                        timeout=self.config.mqtt_timeout,
                    )
                    writer.close()
                    await writer.wait_closed()
                    d = {
                        "name": f"MQTT Broker {ip_s}",
                        "protocol": "mqtt",
                        "ip": ip_s,
                        "port": 1883,
                        "status": "discovered",
                        "missing_info": [],
                    }
                    self._found(d)
                    return d
                except Exception:
                    pass
                finally:
                    done += 1
                    if done % 20 == 0:
                        self._progress("MQTT", done, total)
            return None

        results = await asyncio.gather(*(probe(ip) for ip in hosts), return_exceptions=True)
        devices = [r for r in results if isinstance(r, dict)]
        self._progress("MQTT", total, total)
        return devices
