# Shadow validation

The shadow service compares the live reduced model with the distributed catenary
candidate without connecting the candidate to the controller.

Generate a reproducible JSON report:

```bash
python -m backend.validation.shadow --output shadow-report.json
```

Each report records the source commit, numerical resolution, parameter provenance,
model metrics, EN 50318 benchmark checks, and every acceptance gate. A result can be:

- `WARMING_UP`: background calculation is still running.
- `AGREEMENT`: every declared comparison and numerical gate passed.
- `INVESTIGATE`: at least one gate failed; inspect the reported failure.
- `OUTSIDE_ENVELOPE`: the requested operating condition is not represented.
- `ERROR`: the shadow calculation failed. Live control remains unaffected.

Current scope is nominal vertical dynamics at 250 and 300 km/h. Stochastic turbulence,
tension degradation, gusts, temperature, ice and lateral dynamics are excluded. Model
agreement is not certification; measured contact-force data remains necessary.
