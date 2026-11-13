"""Constants of EWPE HP: GREE Versati heat pumps through the Gree+ (EWPE) cloud."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ewpe_hp"

CONF_REGION: Final = "region"
CONF_PASSWORD_HASH: Final = "password_hash"

# Gree+ regions: the REST host and the MQTT broker of each. The account lives in one region only.
REGIONS: Final[dict[str, tuple[str, str]]] = {
    "europe": ("https://eugrih.gree.com", "mqtt-eu.gree.com"),
    "russia": ("https://rugrih.gree.com", "mqtt-ru.gree.com"),
    "middle_east": ("https://megrih.gree.com", "mqtt-me.gree.com"),
    "india": ("https://ingrih.gree.com", "mqtt-in.gree.com"),
    "east_south_asia": ("https://hkgrih.gree.com", "mqtt-hk.gree.com"),
    "australia": ("https://augrih.gree.com", "mqtt-au.gree.com"),
    "north_america": ("https://nagrih.gree.com", "mqtt-na.gree.com"),
    "south_america": ("https://sagrih.gree.com", "mqtt-sa.gree.com"),
    "china": ("https://grih.gree.com", "mqtt.gree.com"),
}
DEFAULT_REGION: Final = "europe"

# What the Gree+ app identifies itself with
APP_ID: Final = "4920681951525131286"
APP_HASH: Final = "0fa513124aa97781d1f3f40d61ca1a89"
APP_KEY: Final = b"#G$&^jgfujy6ujxt"
APP_HEADER: Final = "5ac2bdf935bcca70"

MQTT_PORT: Final = 1984
# Wi-Fi modules from this protocol version on are reached over MQTT, older ones through their gateway
MQTT_FROM_VERSION: Final = (3, 2)

SCAN_INTERVAL_SECONDS: Final = 30
REQUEST_TIMEOUT: Final = 10.0
# a unit can take its time to answer through the broker
MQTT_TIMEOUT: Final = 20.0
# a module answers long status requests badly, so they go in parts
COLUMNS_PER_REQUEST: Final = 12

# device parameters
POW: Final = "Pow"
MOD: Final = "Mod"
QUIET: Final = "Quiet"
HEAT_WATER_SET: Final = "HeWatOutTemSet"
COOL_WATER_SET: Final = "CoWatOutTemSet"
TANK_SET: Final = "WatBoxTemSet"
ROOM_HEAT_SET: Final = "HeHomTemSet"
ROOM_COOL_SET: Final = "CoHomTemSet"
FAST_HOT_WATER: Final = "FastHtWter"
HEAT_PRIORITY: Final = "HetHtWter"
COOL_PRIORITY: Final = "ColHtWter"
UNIT: Final = "TemUn"
ERROR: Final = "AllErr"

# measured temperatures come as <name>Hi (whole degrees + 100) and <name>Lo (tenths)
TEMPERATURES: Final = ("AllOutWatTem", "AllInWatTem", "HepOutWatTem", "WatBoxTem", "RmoHomTem")
TANK_TEMPERATURE: Final = "WatBoxTem"
TEMPERATURE_OFFSET: Final = 100
# Hi 70, Lo 0 (-30 °C): no sensor fitted
NOT_FITTED: Final = -30.0

STATES: Final = ("WatBoxElcHeRunSta", "ElcHe1RunSta", "ElcHe2RunSta", "AnFrzzRunSta", "SyAnFroRunSta")

SETTINGS: Final = (
    POW,
    MOD,
    QUIET,
    HEAT_WATER_SET,
    COOL_WATER_SET,
    TANK_SET,
    ROOM_HEAT_SET,
    ROOM_COOL_SET,
    FAST_HOT_WATER,
    HEAT_PRIORITY,
    COOL_PRIORITY,
    UNIT,
    ERROR,
)
COLUMNS: Final = (
    *SETTINGS,
    *(f"{name}{part}" for name in TEMPERATURES for part in ("Hi", "Lo")),
    *STATES,
)

# Mod, as on the controller: the same numbers as the Versati Modbus table
MODES: Final[dict[str, int]] = {
    "heat": 1,
    "hot_water": 2,
    "cool_hot_water": 3,
    "heat_hot_water": 4,
    "cool": 5,
}
