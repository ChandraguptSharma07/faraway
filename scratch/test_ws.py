import asyncio
import websockets

async def test():
    async with websockets.connect("ws://127.0.0.1:8000/ws") as websocket:
        print("Connected!")
        await websocket.send('{"type":"ping"}')
        res = await websocket.recv()
        print("Received:", len(res))

asyncio.run(test())
