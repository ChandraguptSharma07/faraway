from backend.validation.shadow import simulate_live, ShadowConfig
from backend.sim.parameters import CatenaryParams, kmh_to_ms
from dataclasses import replace

for a1 in [0.012, 0.013]:
    for a2 in [0.017, 0.018]:
        for c in [0.0013, 0.0014]:
            cat = replace(CatenaryParams(), turb_std=0.0, a_span=a1, a_span2=a2, c_aero=c)
            res = simulate_live(kmh_to_ms(250), 3.0, dt=0.001, cat=cat)
            print(f"a1={a1} a2={a2} c={c}: std={res['std_N']:.1f}, mean={res['mean_N']:.1f}")
