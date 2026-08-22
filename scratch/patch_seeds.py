import re

with open('backend/server/engine.py', 'r') as f:
    content = f.read()

# Change: self.dist = Disturbance(self.cat, seed=seed)
# To: 
# self.dist_p = Disturbance(self.cat, seed=seed)
# self.dist_a = Disturbance(self.cat, seed=seed + 999)

content = content.replace("self.dist = Disturbance(self.cat, seed=seed)", 
                          "self.dist_p = Disturbance(self.cat, seed=seed)\n        self.dist_a = Disturbance(self.cat, seed=seed + 999)\n        self.dist = self.dist_a")

content = content.replace("self.env_p = CoupledWireEnvironment(self.dist, self.wire_p)",
                          "self.env_p = CoupledWireEnvironment(self.dist_p, self.wire_p)")

content = content.replace("self.env_a = CoupledWireEnvironment(self.dist, self.wire_a)",
                          "self.env_a = CoupledWireEnvironment(self.dist_a, self.wire_a)")

content = content.replace("self.env_ideal = CoupledWireEnvironment(self.dist, self.wire_ideal)",
                          "self.env_ideal = CoupledWireEnvironment(self.dist_a, self.wire_ideal)")

with open('backend/server/engine.py', 'w') as f:
    f.write(content)
