import re

with open('frontend/src/components/World3D.jsx', 'r') as f:
    content = f.read()

# Exaggerate the vibration visually in the 3D renderer by clamping to 100 and multiplying by 0.05
content = content.replace("clamp(headMm, -25, 25) * 0.022", "clamp(headMm, -100, 100) * 0.05")
content = content.replace("clamp(wireMm, -25, 25) * 0.022", "clamp(wireMm, -100, 100) * 0.05")
# Widen the clamp for topY so it doesn't hit a rigid ceiling
content = content.replace("topY = clamp(topY, baseY + 0.72, baseY + 2.05)", "topY = clamp(topY, baseY + 0.1, baseY + 4.0)")
content = content.replace("clamp(frameMm, -25, 25) * 0.003", "clamp(frameMm, -100, 100) * 0.015")

with open('frontend/src/components/World3D.jsx', 'w') as f:
    f.write(content)
