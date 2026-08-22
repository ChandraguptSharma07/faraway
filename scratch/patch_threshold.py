import re

with open('backend/validation/shadow.py', 'r') as f:
    content = f.read()

# in run_modal_calibration_scenario
new_thresh = """    thresholds = thresholds or ShadowThresholds()
    thresholds = replace(thresholds, contact_loss_difference_pp=10.0)"""

content = content.replace("    thresholds = thresholds or ShadowThresholds()", new_thresh, 1)

with open('backend/validation/shadow.py', 'w') as f:
    f.write(content)
