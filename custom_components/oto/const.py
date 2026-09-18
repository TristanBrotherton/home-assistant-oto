"""Constants for the OTO integration."""

from datetime import timedelta

DOMAIN = "oto"

CONF_REFRESH_TOKEN = "refresh_token"
CONF_UID = "uid"
CONF_WATERING_DEPTH = "watering_depth"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_WATERING_DEPTH_MM = 1.0
DEFAULT_SCAN_INTERVAL = 30
MIN_WATERING_DEPTH_MM = 1.0
MAX_WATERING_DEPTH_MM = 50.0
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 300

PLATFORMS = ["binary_sensor", "button", "number"]

DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

ATTR_WATERING_DEPTH_MM = "watering_depth_mm"
ATTR_ESTIMATED_RUNTIME_MIN = "estimated_runtime_min"
COMMAND_COOLDOWN_SECONDS = 10
