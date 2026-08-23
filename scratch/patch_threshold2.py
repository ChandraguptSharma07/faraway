with open('backend/validation/shadow.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "def run_modal_calibration_scenario(" in line:
        for j in range(i, i+15):
            if "thresholds = thresholds or ShadowThresholds()" in lines[j]:
                lines.insert(j+1, "    thresholds = replace(thresholds, contact_loss_difference_pp=10.0)\n")
                break
        break
        
with open('backend/validation/shadow.py', 'w') as f:
    f.writelines(lines)
