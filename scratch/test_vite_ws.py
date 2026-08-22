import asyncio
import websockets

async def test():
    try:
        async with websockets.connect("ws://127.0.0.1:5173/ws") as websocket:
            print("Connected to Vite proxy!")
            res = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print("Received:", len(res))
    except Exception as e:
        print("Error:", type(e), e)

asyncio.run(test())
