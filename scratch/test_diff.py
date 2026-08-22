from backend.server.engine import Engine
e = Engine()
e.step(500)
for _ in range(10):
    e.step(50)
    state = e.frame()
    print(state["passive"]["head_mm"], state["aeropinn"]["head_mm"])
