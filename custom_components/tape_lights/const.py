"""Constants for the TAPE LIGHTS integration."""

DOMAIN = "tape_lights"
DEFAULT_NAME = "TAPE LIGHTS"

DEFAULT_SPEED = 50
DEFAULT_MIC_SENSITIVITY = 50

# Drop the link soon after the last command. The controller only advertises
# while disconnected and Home Assistant forgets a device that has not
# advertised for ~195 s, so a long lived link makes it unreachable.
IDLE_DISCONNECT_SECONDS = 10

# How long to wait for the controller to advertise again before giving up.
ADVERTISEMENT_WAIT_SECONDS = 30

# Cheap Telink/BK controllers drop the link when writes arrive back to back.
COMMAND_SETTLE_SECONDS = 0.1
