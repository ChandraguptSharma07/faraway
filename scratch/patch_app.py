import re

with open('backend/server/app.py', 'r') as f:
    content = f.read()

# Add get_modal_shadow_service
new_service = """
_modal_shadow_service = None
def get_modal_shadow_service():
    global _modal_shadow_service
    if _modal_shadow_service is None:
        from backend.validation.shadow import ShadowValidationService, run_modal_calibration_scenario
        _modal_shadow_service = ShadowValidationService(runner=run_modal_calibration_scenario)
    return _modal_shadow_service

"""

content = content.replace("def get_shadow_service():", new_service + "def get_shadow_service():")
content = content.replace("get_shadow_service().warm()", "get_shadow_service().warm()\n            get_modal_shadow_service().warm()")
content = content.replace("_shadow_service.close()", "_shadow_service.close()\n    if _modal_shadow_service is not None:\n        _modal_shadow_service.close()")

new_endpoint = """
@app.get("/api/modal-calibration")
def modal_calibration(
    speed_kmh: float = 250.0,
    tension_factor: float = 1.0,
    turbulence_gain: float = 1.0,
    gust_active: bool = False,
):
    from backend.validation.shadow import classify_operating_point
    snapshot = get_modal_shadow_service().snapshot()
    snapshot["operating_point"] = classify_operating_point(
        snapshot, speed_kmh, tension_factor, turbulence_gain, gust_active
    )
    return snapshot

"""

content = content.replace("def _handle_input(", new_endpoint + "def _handle_input(")

with open('backend/server/app.py', 'w') as f:
    f.write(content)
