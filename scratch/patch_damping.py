import re

with open('backend/validation/shadow.py', 'r') as f:
    content = f.read()

# Increase damping_ratio in fine_params for run_modal_calibration_scenario
new_fine_params = """    fine_params = replace(
        DistributedCatenaryParams(),
        n_spans=config.n_spans,
        elements_per_span=config.fine_elements_per_span,
        damping_ratio=0.05,  # 10x damping to kill startup shock fast
    )"""

content = re.sub(r'    fine_params = replace\(\n        DistributedCatenaryParams\(\),\n        n_spans=config\.n_spans,\n        elements_per_span=config\.fine_elements_per_span,\n    \)', new_fine_params, content)

with open('backend/validation/shadow.py', 'w') as f:
    f.write(content)
