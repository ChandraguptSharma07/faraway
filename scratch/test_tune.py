from backend.validation.shadow import simulate_live, ShadowConfig
from backend.sim.parameters import CatenaryParams, kmh_to_ms
from dataclasses import replace

for a2 in [0.004, 0.01, 0.015, 0.02]:
    cat = replace(CatenaryParams(), turb_std=0.0, a_span2=a2)
    res = simulate_live(kmh_to_ms(250), 3.0, dt=0.001, cat=cat)
    print(f"a2={a2}: std={res['std_N']:.1f}, mean={res['mean_N']:.1f}")
