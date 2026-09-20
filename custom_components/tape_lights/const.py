"""Constants for the TAPE LIGHTS integration."""

DOMAIN = "tape_lights"
DEFAULT_NAME = "TAPE LIGHTS"

DEFAULT_SPEED = 50
DEFAULT_MIC_SENSITIVITY = 50

# Keep the BLE link for this long after the last command: reconnecting costs
# seconds, so back to back commands would otherwise queue up and arrive in a
# burst. The phone app can connect again once the link is dropped.
IDLE_DISCONNECT_SECONDS = 120
