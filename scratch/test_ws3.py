import asyncio
import websockets

async def test():
    try:
        async with websockets.connect("ws://127.0.0.1:8001/ws", ping_timeout=None) as websocket:
            print("Connected!")
            res = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            print("Received:", len(res))
    except Exception as e:
        print("Error:", type(e), e)

asyncio.run(test())
