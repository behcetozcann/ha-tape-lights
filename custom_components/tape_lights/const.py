"""Constants for the TAPE LIGHTS integration."""

DOMAIN = "tape_lights"
DEFAULT_NAME = "TAPE LIGHTS"
ESPHOME_DOMAIN = "esphome"

DEFAULT_SPEED = 50
DEFAULT_MIC_SENSITIVITY = 50

# How the frames reach the controller. "esphome" hands them to an ESP32 that
# keeps the BLE link open; "bluetooth" connects from Home Assistant itself.
CONF_TRANSPORT = "transport"
CONF_ESPHOME_NODE = "esphome_node"
CONF_CONNECTION_SENSOR = "connection_sensor"
TRANSPORT_BLUETOOTH = "bluetooth"
TRANSPORT_ESPHOME = "esphome"
DEFAULT_TRANSPORT = TRANSPORT_BLUETOOTH

# Drop the link soon after the last command. The controller only advertises
# while disconnected and Home Assistant forgets a device that has not
# advertised for ~195 s, so a long lived link makes it unreachable.
# Only used by the direct Bluetooth transport.
IDLE_DISCONNECT_SECONDS = 10

# How long to wait for the controller to advertise again before giving up.
ADVERTISEMENT_WAIT_SECONDS = 30

# Cheap Telink/BK controllers drop the link when writes arrive back to back.
COMMAND_SETTLE_SECONDS = 0.1
