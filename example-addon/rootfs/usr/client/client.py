import socketio
import asyncio
import aiohttp
import time

from typing import Dict, Tuple
import sys
import logging
import os
import json
from constants import WS_TIMEOUT

# Set LOGLEVEL env variable in your own machine
LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()
logging.basicConfig(level=LOGLEVEL)


class HassioProxyClient:
    def __init__(
        self,
        subdomain: str,
        token: str,
        events_json: str,
        ha_url: str = "http://localhost:8123",
        ha_ws_url: str = "ws://localhost:8123",
    ):
        self.subdomain: str = subdomain
        self.token: str = token
        self.ha_url: str = ha_url
        self.ha_ws_url: str = ha_ws_url
        self.websocket_route: str = "/api/websocket"
        self.sessions: Dict[
            str, Tuple[aiohttp.ClientWebSocketResponse, aiohttp.ClientSession]
        ] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        # Reconnection variables for reconnection with HA Instance
        self.reconnect_attempts: int = 5
        self.reconnect_interval: int = 5
        self.isConnected = False
        # Load event names from shared JSON file
        with open(events_json) as json_file:
            self.events = json.load(json_file)
        # Socketio event listeners
        self.sio: socketio.AsyncClient = socketio.AsyncClient(
            reconnection_delay=5, reconnection_delay_max=15
        )
        self.sio.on(self.events["CONNECT"], self._connect)
        self.sio.on(self.events["DISCONNECT"], self._disconnect)
        self.sio.on(self.events["EXTERNAL_WS_CONNECTED"], self._handle_ws_connected)
        self.sio.on(
            self.events["EXTERNAL_WS_DISCONNECTED"], self._handle_ws_disconnected
        )
        self.sio.on(self.events["GET_REQUEST"], self._on_get)
        self.sio.on(self.events["POST_REQUEST"], self._on_post)
        self.sio.on(self.events["TO_WS_API"], self._handle_to_ws)

    @staticmethod
    def validate_connection(subdomain: str, token: str) -> bool:
        if not subdomain and not token:
            logging.error("Invalid command line arguments to start Client")
            return False
        return True

    # Socketio event handlers
    async def _connect(self):
        self.isConnected = True
        logging.info("Connected to Proxy Server")

    async def _disconnect(self):
        self.isConnected = False
        logging.info("Disconnected from Proxy Server")
        await self._close_all_ws()

    async def _close_all_ws(self):
        for uuid in list(self.sessions.keys()):
            await self._close_ws(uuid)

    async def _close_ws(self, uuid: str):
        if uuid in self.sessions:
            ws, session = self.sessions[uuid]
            await ws.close()
            await session.close()
            del self.sessions[uuid]

    async def _handle_ws_connected(self, uuid: str, path: str, headers: str):
        logging.info(f"connecting to ha websocket for {uuid}")

        if uuid in self.sessions:
            logging.info(
                f"already connected to HA websocket for {uuid}, new connection ignored"
            )
            return

        session = aiohttp.ClientSession()
        ws = await session.ws_connect(
            self.ha_ws_url + path, timeout=WS_TIMEOUT, headers=headers
        )

        self.sessions[uuid] = (ws, session)
        self.tasks[uuid] = asyncio.create_task(self._run_ws_listener(uuid, ws))

    async def _handle_ws_disconnected(self, uuid: str):
        logging.info(f"server_ws_disconnected for {uuid}")

        await self._close_ws(uuid)

        if uuid in self.tasks:
            self.tasks[uuid].cancel()
            del self.tasks[uuid]

    async def _on_post(self, data):
        response = await self._post(data)
        return response

    async def _on_get(self, data):
        response = await self._get(data)
        return response

    async def _handle_to_ws(self, data: bytes, uuid: str, isBinary: bool):
        if uuid not in self.sessions:
            logging.info(f"No websocket session for {uuid}")
            return

        ws, _ = self.sessions[uuid]
        try:
            if isBinary:
                # Attempting to solve Ingress issue
                print(data)
                await ws.send_bytes(data)
            else:
                await ws.send_str(data.decode())

        # Might need to handle specific errors
        except Exception as err:
            logging.error(err)

            # Need to check if this will correctly restore connection to HA instance.
            # However, disconnection from HA instance will not happen often.
            # If reconnection does not happen, the external browser would have to reload their webpage.
            for _ in range(self.reconnect_attempts):
                logging.warning(f"Attempting websocket reconnect to HA for {uuid}")
                if ws != None:
                    await self._close_ws(uuid)

                session = aiohttp.ClientSession()
                ws = await session.ws_connect(
                    self.ha_url + self.websocket_route,
                    timeout=WS_TIMEOUT,
                )
                self.sessions[uuid] = (ws, session)

                if ws:
                    if isBinary:
                        await ws.send_bytes(data)
                    else:
                        await ws.send_str(data.decode())
                    break

                await asyncio.sleep(self.reconnect_interval)

    # End of socketio event handlers

    async def _run_ws_listener(self, uuid: str, ws: aiohttp.ClientWebSocketResponse):
        try:
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.sio.emit(
                        f"ha_reply", {"message": msg.data, "uuid": uuid}
                    )

                elif msg.type in [aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING]:
                    logging.info(f"connection to HA websocket for {uuid} closed")
                    break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logging.error(
                        f"error occurred in connection to HA websocket for {uuid}"
                    )
                    break

        except asyncio.CancelledError:
            logging.info(f"Listener for {uuid} was cancelled")

        # Might need to handle specific exception
        except Exception as e:
            logging.error(e)
            await self._handle_ws_connected(uuid)

    async def _get(self, data):
        async with aiohttp.ClientSession(auto_decompress=False) as session:
            url = self.ha_url + data["path"]
            custom_headers = data["headers"]
            params = None
            if "params" in data:
                params = data["params"]
            async with session.get(
                url=url,
                headers=custom_headers,
                params=params,
                allow_redirects=False,
            ) as response:
                data = await response.read()
                headers = dict(response.headers)

                return {
                    "data": data,
                    "headers": headers,
                    "status": response.status,
                }

    async def _post(self, data):
        async with aiohttp.ClientSession(auto_decompress=False) as session:
            url = self.ha_url + data["path"]
            custom_headers = data["headers"]
            body = data["data"]
            params = None
            if "params" in data:
                params = data["params"]

            async with session.post(
                url=url,
                data=body,
                headers=custom_headers,
                params=params,
                allow_redirects=False,
            ) as response:
                res = await response.read()
                headers = dict(response.headers)

                return {
                    "data": res,
                    "headers": headers,
                    "status": response.status,
                }

    async def start(self):
        try:
            # Change to correct domain name in production server
            # Server set up such that
            while (not self.isConnected):
                await self.sio.connect(
                    f"wss://{self.subdomain}.vida-quantum.com/socket.io/?EIO=3&transport=websocket",
                    headers={"subdomain": self.subdomain, "token": self.token},
                )

                if (not self.isConnected):
                    # Add delay to avoid busy-waiting
                    time.sleep(2)

            await self.sio.wait()

        except KeyboardInterrupt:
            logging.info("Shutting down gracefully...")
            await self.sio.disconnect()

            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()

            await self._close_all_ws()


def main():
    # Load subdomain from command line args
    # e.g. python client.py [subdomain] [hash]
    if len(sys.argv) != 3:
        logging.error("Incorrect number of command line arguments")
        return

    subdomain = sys.argv[1]
    token = sys.argv[2]

    if HassioProxyClient.validate_connection(subdomain, token):
        client = HassioProxyClient(subdomain, token, "/usr/client/events.json")
        asyncio.run(client.start())


if __name__ == "__main__":
    main()
