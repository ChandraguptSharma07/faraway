import time
from backend.server.engine import Engine
from backend.server.app import get_predictor

t0 = time.time()
engine = Engine(predictor=get_predictor())
t1 = time.time()
print("Engine init took:", t1 - t0)
