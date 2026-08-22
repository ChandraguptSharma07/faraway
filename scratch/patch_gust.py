import re

with open('backend/server/engine.py', 'r') as f:
    content = f.read()

content = content.replace("self.dist.inject_transient(self.t, magnitude)", 
                          "self.dist_p.inject_transient(self.t, magnitude)\n        self.dist_a.inject_transient(self.t, magnitude)")

with open('backend/server/engine.py', 'w') as f:
    f.write(content)
