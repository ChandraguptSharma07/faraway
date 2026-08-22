import asyncio
import websockets

async def test():
    try:
        async with websockets.connect("ws://127.0.0.1:8000/ws", ping_timeout=None) as websocket:
            print("Connected!")
            res = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print("Received:", len(res))
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
