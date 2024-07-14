import aiohttp
import asyncio
import random
import ssl
import json
import time
import uuid
from loguru import logger
from websockets_proxy import Proxy, proxy_connect
from fake_useragent import UserAgent

user_agent = UserAgent()
random_user_agent = user_agent.random

async def fetch_proxies(url="https://sunny9577.github.io/proxy-scraper/generated/socks5_proxies.txt"):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                proxies = await response.text()
                # Filter out only SOCKS5 proxies
                socks5_proxies = [f"socks5://{proxy}" for proxy in proxies.splitlines()]
                return socks5_proxies
            else:
                logger.error(f"Failed to fetch proxies: {response.status}")
                return []

async def update_proxies(interval=600):
    while True:
        new_proxies = await fetch_proxies()
        if new_proxies:
            with open("proxy_list.txt", "w") as file:
                for proxy in new_proxies:
                    file.write(proxy + "\n")
            logger.info(f"Updated proxy list with {len(new_proxies)} new proxies.")
        await asyncio.sleep(interval)

async def connect_to_wss(socks5_proxy, user_id):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, socks5_proxy))
    logger.info(device_id)
    while True:
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {"User-Agent": random_user_agent}
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            uri = "wss://proxy.wynd.network:4650/"
            server_hostname = "proxy.wynd.network"
            proxy = Proxy.from_url(socks5_proxy)
            async with proxy_connect(
                uri,
                proxy=proxy,
                ssl=ssl_context,
                server_hostname=server_hostname,
                extra_headers=custom_headers,
            ) as websocket:

                async def send_ping():
                    while True:
                        send_message = json.dumps(
                            {
                                "id": str(uuid.uuid4()),
                                "version": "1.0.0",
                                "action": "PING",
                                "data": {},
                            }
                        )
                        logger.debug(send_message)
                        await websocket.send(send_message)
                        await asyncio.sleep(20)

                await asyncio.sleep(1)
                asyncio.create_task(send_ping())

                while True:
                    response = await websocket.recv()
                    message = json.loads(response)
                    logger.info(message)
                    if message.get("action") == "AUTH":
                        auth_response = {
                            "id": message["id"],
                            "origin_action": "AUTH",
                            "result": {
                                "browser_id": device_id,
                                "user_id": user_id,
                                "user_agent": custom_headers["User-Agent"],
                                "timestamp": int(time.time()),
                                "device_type": "extension",
                                "version": "3.3.2",
                            },
                        }
                        logger.debug(auth_response)
                        await websocket.send(json.dumps(auth_response))

                    elif message.get("action") == "PONG":
                        pong_response = {"id": message["id"], "origin_action": "PONG"}
                        logger.debug(pong_response)
                        await websocket.send(json.dumps(pong_response))

                        existing_proxies = set()
                        with open("super_proxy.txt", "r") as file:
                            existing_proxies.update(line.strip() for line in file)
                        existing_proxies.add(socks5_proxy[len("socks5://"):])
                        with open("super_proxy.txt", "w") as file:
                            for proxy in existing_proxies:
                                file.write(proxy + "\n")

        except Exception as e:
            logger.error(e)
            if "Empty connect reply" in str(e):
                await remove_proxy_from_file("proxy_list.txt", socks5_proxy[len("socks5://"):])
            break

async def remove_proxy_from_file(file_path, proxy):
    logger.info(f"Removing {proxy} from {file_path}")
    if proxy.startswith("socks5://"):
        proxy = proxy[len("socks5://"):]  # Remove "socks5://" prefix

    try:
        with open(file_path, "r") as file:
            proxies = file.readlines()

        with open(file_path, "w") as file:
            for p in proxies:
                if p.strip() != proxy:
                    file.write(p)

        logger.info(f"{proxy} removed from {file_path}")
    except Exception as e:
        logger.error(f"Error removing {proxy} from {file_path}: {e}")

async def main():
    with open("user_id.txt", "r") as file:
        _user_id = file.read().strip()

    # Start the task to update proxies periodically
    asyncio.create_task(update_proxies())

    while True:
        with open("proxy_list.txt", "r") as file:
            socks5_proxy_list = file.read().splitlines()

        if not socks5_proxy_list:
            logger.warning("No proxies available. Waiting for proxy update.")
            await asyncio.sleep(60)
            continue

        tasks = []
        for proxy in socks5_proxy_list:
            try:
                task = asyncio.ensure_future(connect_to_wss(proxy, _user_id))
                tasks.append(task)
            except Exception as e:
                logger.error(f"Error creating task for proxy {proxy}: {e}")

        if not tasks:
            logger.error("No proxies available to connect. Retrying...")
            await asyncio.sleep(60)
            continue

        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
