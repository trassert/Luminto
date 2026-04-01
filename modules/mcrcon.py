import asyncio
import contextlib
import struct

from loguru import logger

from . import config

logger.info(f"Загружен модуль {__name__}!")


class ClientError(Exception):
    pass


class InvalidPassword(Exception):
    pass


class MinecraftClient:
    def __init__(self, host: str, port: int, password) -> None:
        self.host = host
        self.port = port
        self.password = password

        self._auth = False
        self._reader = None
        self._writer = None

        self._connected = False

        self._lock = asyncio.Lock()

        self._users = 0

    async def __aenter__(self):
        async with self._lock:
            self._users += 1

            if not self._writer or self._writer.is_closing():
                try:
                    self._reader, self._writer = await asyncio.open_connection(
                        self.host,
                        self.port,
                    )
                    self._connected = True
                    self._auth = False
                    await self._authenticate()
                except Exception:
                    self._users -= 1
                    raise
        return self

    async def __aexit__(self, exc_type, exc, tb):
        async with self._lock:
            self._users -= 1

            if self._users == 0:
                if self._writer and not self._writer.is_closing():
                    self._writer.close()
                    with contextlib.suppress(Exception):
                        await self._writer.wait_closed()
                self._connected = False
                self._auth = False
                self._reader = None
                self._writer = None

    async def _authenticate(self) -> None:
        if not self._auth and self._writer:
            await self._send_internal(3, self.password)
            self._auth = True

    async def _read_data(self, length):
        data = b""
        while len(data) < length:
            if not self._reader:
                msg = "Соединение разорвано (reader is None)"
                raise ClientError(msg)
            try:
                packet = await self._reader.read(length - len(data))
            except Exception as e:
                msg = f"Connection error: {e}"
                raise ClientError(msg)

            if not packet:
                msg = "Connection closed by server (empty packet)"
                raise ClientError(msg)
            data += packet
        return data

    async def _send_internal(self, message_type, message):
        if not self._writer or self._writer.is_closing():
            msg = "Writer is not available or connection is closed."
            raise ClientError(msg)

        packet_id = 0
        body = (
            struct.pack("<ii", packet_id, message_type)
            + message.encode("utf8")
            + b"\x00\x00"
        )
        body_length = len(body)

        self._writer.write(struct.pack("<i", body_length) + body)
        await self._writer.drain()

        in_length_data = await self._read_data(4)
        in_length = struct.unpack("<i", in_length_data)[0]
        in_payload = await self._read_data(in_length)

        if len(in_payload) < 8:
            msg = "Uncorrect response from server: payload too short."
            raise ClientError(msg)

        in_id, _in_type = struct.unpack("<ii", in_payload[:8])
        in_data = in_payload[8:-2]
        in_padding = in_payload[-2:]

        if in_padding != b"\x00\x00":
            msg = "Uncorrect response from server: padding is incorrect."
            raise ClientError(msg)

        if in_id == -1:
            msg = "Authentication failed: invalid password."
            raise InvalidPassword(msg)

        return in_data.decode("utf8")

    async def _send(self, message_type, message):

        async with self._lock:
            if not self._writer or self._writer.is_closing():
                msg = "Writer is not available or connection is closed."
                raise ClientError(msg)

            return await self._send_internal(message_type, message)

    async def send(self, cmd):
        logger.info(f"RCON: {cmd}")
        return await self._send(2, cmd)


Vanilla = MinecraftClient(
    host=config.tokens.modes.vanilla.host,
    port=config.tokens.modes.vanilla.port,
    password=config.tokens.modes.vanilla.password,
)
