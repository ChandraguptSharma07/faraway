import re

with open('backend/validation/shadow.py', 'r') as f:
    content = f.read()

# modify cat = replace(CatenaryParams(), turb_std=0.0)
new_cat = "cat = replace(CatenaryParams(), turb_std=0.0, a_span=0.012, a_span2=0.018, c_aero=0.0017)"
content = content.replace("cat = replace(CatenaryParams(), turb_std=0.0)", new_cat)

with open('backend/validation/shadow.py', 'w') as f:
    f.write(content)
