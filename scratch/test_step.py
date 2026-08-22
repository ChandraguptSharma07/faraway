import time
from backend.server.engine import Engine
from backend.server.app import get_predictor

print("Init...")
engine = Engine(predictor=get_predictor())
print("Init done. Stepping...")
t0 = time.time()
engine.step(33)
t1 = time.time()
print("Step took:", t1 - t0)
