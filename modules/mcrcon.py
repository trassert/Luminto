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

    async def __aenter__(self):

        async with self._lock:
            if not self._connected:
                self._reader, self._writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                )
                self._connected = True
                await self._authenticate()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self) -> None:

        async with self._lock:
            if self._writer and not self._writer.is_closing():
                self._writer.close()
                with contextlib.suppress(Exception):
                    await self._writer.wait_closed()
            self._connected = False
            self._auth = False
            self._reader = None
            self._writer = None

    async def _authenticate(self) -> None:

        if not self._auth:
            await self._send_internal(3, self.password)
            self._auth = True

    async def _read_data(self, length):
        data = b""
        while len(data) < length:
            try:
                packet = await self._reader.read(length - len(data))
            except Exception as e:
                msg = f"Соединение разорвано: {e}"
                raise ClientError(msg)

            if not packet:
                msg = "Соединение разорвано (пустой пакет)"
                raise ClientError(msg)
            data += packet
        return data

    async def _send_internal(self, message_type, message):
        """Внутренняя отправка без проверки лока (вызывается только под локом)."""
        if not self._writer or self._writer.is_closing():
            msg = "Не подключён."
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
            msg = "Некорректный пакет ответа (слишком короткий)"
            raise ClientError(msg)

        in_id, _in_type = struct.unpack("<ii", in_payload[:8])
        in_data = in_payload[8:-2]
        in_padding = in_payload[-2:]

        if in_padding != b"\x00\x00":
            msg = "Неправильное заполнение."
            raise ClientError(msg)

        if in_id == -1:
            msg = "Неверный пароль."
            raise InvalidPassword(msg)

        return in_data.decode("utf8")

    async def _send(self, message_type, message):
        """Публичный метод отправки, оборачивающий операцию в блокировку."""
        async with self._lock:
            if not self._connected:
                msg = "Соединение не установлено. Используйте async with."
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
