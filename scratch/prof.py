import sys; sys.path.append('.'); import cProfile; from backend.server.engine import Engine; e=Engine(); cProfile.run('e.step(33)', sort='tottime')
