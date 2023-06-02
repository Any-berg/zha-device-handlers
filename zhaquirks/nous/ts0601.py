"""Nous temp and humidity sensors (with all dependencies)."""

from typing import Dict, Any

from zigpy.profiles import zha
from zigpy.quirks import CustomDevice
import zigpy.types as t
from zigpy.zcl.clusters.general import (
    Basic,
    Groups,
    Ota,
    Scenes,
    Time,
    PowerConfiguration,
)
from zhaquirks.const import (
    DEVICE_TYPE,
    ENDPOINTS,
    INPUT_CLUSTERS,
    MODELS_INFO,
    OUTPUT_CLUSTERS,
    PROFILE_ID,
    SKIP_CONFIGURATION,
)
from zhaquirks.tuya import (
    NoManufacturerCluster,
    TuyaPowerConfigurationCluster2AAA,
    TuyaLocalCluster,
    TuyaTimePayload,
    TUYA_SET_TIME,
)
from zhaquirks.tuya.mcu import (
    TuyaMCUCluster as OriginalTuyaMCUCluster,
    DPToAttributeMapping,
    TUYA_MCU_CONNECTION_STATUS,
)
from zigpy.zcl import foundation
import datetime
from zigpy.zcl.clusters.measurement import (
    RelativeHumidity,
    TemperatureMeasurement,
)


class TuyaMCUCluster(OriginalTuyaMCUCluster):
    """My hope is that these fixes get merged into TuyaMCUCluster."""

    def handle_set_time_request(self, payload: t.uint16_t) -> foundation.Status:
        """Handle set_time requests (0x24)."""

        self.debug("handle_set_time_request payload: %s", payload)
        payload_rsp = TuyaTimePayload()

        utc_now = datetime.datetime.utcnow()
        now = datetime.datetime.now()

        offset_time = datetime.datetime(self.set_time_offset, 1, 1)
        offset_time_local = datetime.datetime(
            self.set_time_local_offset or self.set_time_offset, 1, 1
        )

        utc_timestamp = int((utc_now - offset_time).total_seconds())
        local_timestamp = int((now - offset_time_local).total_seconds())

        payload_rsp.extend(utc_timestamp.to_bytes(4, "big", signed=False))
        payload_rsp.extend(local_timestamp.to_bytes(4, "big", signed=False))

        self.debug("handle_set_time_request response: %s", payload_rsp)
        self.create_catching_task(
            self.command(TUYA_SET_TIME, payload_rsp, expect_reply=False)
        )

        return foundation.Status.SUCCESS

    def handle_mcu_connection_status(
        self, payload: TuyaConnectionStatus
    ) -> foundation.Status:
        """Handle gateway connection status requests (0x25)."""

        payload_rsp = TuyaMCUCluster.TuyaConnectionStatus()
        payload_rsp.tsn = payload.tsn
        payload_rsp.status = b"\x01"  # 0x00 not connected to internet | 0x01 connected to internet | 0x02 time out

        self.create_catching_task(
            self.command(TUYA_MCU_CONNECTION_STATUS, payload_rsp, expect_reply=False)
        )

        return foundation.Status.SUCCESS


class TuyaTemperatureMeasurement(TemperatureMeasurement, TuyaLocalCluster):
    """Tuya local TemperatureMeasurement cluster."""


class TuyaRelativeHumidity(RelativeHumidity, TuyaLocalCluster):
    """Tuya local RelativeHumidity cluster with a device RH_MULTIPLIER factor."""

    def update_attribute(self, attr_name: str, value: Any) -> None:
        """Apply a correction factor to value."""

        if attr_name == "measured_value":
            value = value * (
                self.endpoint.device.RH_MULTIPLIER
                if hasattr(self.endpoint.device, "RH_MULTIPLIER")
                else 100
            )
        return super().update_attribute(attr_name, value)


class TuyaPowerConfigurationCluster3AAA(PowerConfiguration, TuyaLocalCluster):
    """PowerConfiguration cluster for devices with 3 AAA."""

    BATTERY_SIZES = 0x0031
    BATTERY_QUANTITY = 0x0033
    BATTERY_RATED_VOLTAGE = 0x0034

    _CONSTANT_ATTRIBUTES = {
        BATTERY_SIZES: 4,
        BATTERY_QUANTITY: 3,
        BATTERY_RATED_VOLTAGE: 15,
    }


class TemperatureUnit(t.enum8):
    CELSIUS = 0x00
    FAHRENHEIT = 0x01


class ValueAlarm(t.enum8):
    """Temperature and humidity alarm values."""

    ALARM_OFF = 0x02
    MAX_ALARM_ON = 0x01
    MIN_ALARM_ON = 0x00


class decimal1(int):
    """Helper int subclass that emulates fixed decimals in TuyaClusterData."""

    def __new__(cls, *args, **kwargs):
        """Convert written str and bool but pass read int unchanged."""
        return super(decimal1, cls).__new__(cls,
            round(float(args[0]) * 10)
            if isinstance(args[0], (str, bool))
            else args[0]
        )

    def __str__(cls):
        return '{0:.1f}'.format(int(cls) / 10)


class NousManufClusterE6(NoManufacturerCluster, TuyaMCUCluster):
    """Tuya Manufacturer Cluster with climate data points and NoManufacturerID."""

    attributes = TuyaMCUCluster.attributes.copy()
    attributes.update(
        {
            # 0x0201: ("temperature", t.int16s, True),                   # -
            # 0x0202: ("humidity", t.int16s, True),                      # -
            # 0x0204: ("battery", t.int16s, True),                       # -
            0xF409: ("temperature_unit_convert", TemperatureUnit, True), # 0   (0=CELSIUS, 1=FAHRENHEIT)
            0xF20A: ("max_temperature", decimal1, True),                 # 390 /10
            0xF20B: ("min_temperature", decimal1, True),                 # 0
            0xF40E: ("temperature_alarm", ValueAlarm, True),             # -   (None=unset, 0=low, 1=high, 2=OK)
            0xF213: ("temperature_sensitivity", decimal1, True),         # 6   /10
        }
    )

    dp_to_attribute: Dict[int, DPToAttributeMapping] = {
        1: DPToAttributeMapping(
            TuyaTemperatureMeasurement.ep_attribute, "measured_value", lambda x: x * 10,
        ),
        2: DPToAttributeMapping(TuyaRelativeHumidity.ep_attribute, "measured_value"), # converted in cluster
        4: DPToAttributeMapping(
            PowerConfiguration.ep_attribute, "battery_percentage_remaining", lambda x: x * 2,
        ),
        9: DPToAttributeMapping(
            TuyaMCUCluster.ep_attribute, "temperature_unit_convert", lambda x: TemperatureUnit(x),
        ),
        10: DPToAttributeMapping(
            TuyaMCUCluster.ep_attribute, "max_temperature", lambda x: decimal1(x),
        ),
        11: DPToAttributeMapping(
            TuyaMCUCluster.ep_attribute, "min_temperature", lambda x: decimal1(x),
        ),
        14: DPToAttributeMapping(
            TuyaMCUCluster.ep_attribute, "temperature_alarm", lambda x: ValueAlarm(x),
        ),
        19: DPToAttributeMapping(
            TuyaMCUCluster.ep_attribute, "temperature_sensitivity", lambda x: decimal1(x),
        ),
    }

    data_point_handlers = { key: "_dp_2_attr_update" for key in dp_to_attribute.keys() }


class NousManufClusterSZ_T04(NousManufClusterE6):
    """Tuya Manufacturer cluster with additional climate data points."""

    attributes = NousManufClusterE6.attributes.copy()
    attributes.update(
        {
            0xF20C: ("max_humidity", t.int16s, True),                    # 60
            0xF20D: ("min_humidity", t.int16s, True),                    # 20
            0xF40F: ("humidity_alarm", ValueAlarm, True),                # -   (None=unset, 0=low, 1=high, 2=OK)
            0xF211: ("temperature_report_interval", t.int16s, True),     # 120
            0xF212: ("humidity_report_interval", t.int16s, True),        # 120
            0xF214: ("humidity_sensitivity", t.int16s, True),            # 6
        }
    )

    dp_to_attribute = NousManufClusterE6.dp_to_attribute.copy()
    dp_to_attribute.update(
        {
            12: DPToAttributeMapping(TuyaMCUCluster.ep_attribute, "max_humidity"),
            13: DPToAttributeMapping(TuyaMCUCluster.ep_attribute, "min_humidity"),
            15: DPToAttributeMapping(
                TuyaMCUCluster.ep_attribute, "humidity_alarm", lambda x: ValueAlarm(x),
            ),
            17: DPToAttributeMapping(TuyaMCUCluster.ep_attribute, "temperature_report_interval"),
            18: DPToAttributeMapping(TuyaMCUCluster.ep_attribute, "humidity_report_interval"),
            20: DPToAttributeMapping(TuyaMCUCluster.ep_attribute, "humidity_sensitivity"),
        }
    )

    data_point_handlers = { key: "_dp_2_attr_update" for key in dp_to_attribute.keys() }


class NousClimateSensorE6(CustomDevice):
    """Nous model E6 temperature and humidity sensor with clock."""

    signature = {
        # "profile_id": 260,
        # "device_type": "0x0051",
        # "in_clusters": ["0x0000","0x0004","0x0005",0xef00"],
        # "out_clusters": ["0x000a","0x0019"]
        MODELS_INFO: [("_TZE200_nnrfa68v", "TS0601")],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.SMART_PLUG,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    Groups.cluster_id,
                    Scenes.cluster_id,
                    TuyaMCUCluster.cluster_id,
                ],
                OUTPUT_CLUSTERS: [Ota.cluster_id, Time.cluster_id],
            }
        },
    }

    replacement = {
        SKIP_CONFIGURATION: True,
        ENDPOINTS: {
            1: {
                DEVICE_TYPE: zha.DeviceType.TEMPERATURE_SENSOR,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    Groups.cluster_id,
                    Scenes.cluster_id,
                    TuyaTemperatureMeasurement,
                    TuyaRelativeHumidity,
                    TuyaPowerConfigurationCluster2AAA,
                    NousManufClusterE6,

                ],
                OUTPUT_CLUSTERS: [Ota.cluster_id, Time.cluster_id],
            }
        },
    }


class NousClimateSensorSZ_T04(NousClimateSensorE6):
    """Nous model SZ-T04 temperature and humidity sensor with clock."""

    signature = NousClimateSensorE6.signature.copy() # substitute models info
    signature[MODELS_INFO] = [
        ("_TZE200_locansqn", "TS0601"),
        #("_TZE200_lve3dvpy", "TS0601"), # untested but using same configuration on z2mqtt
        #("_TZE200_c7emyjom", "TS0601"),
    ]

    replacement = NousClimateSensorE6.replacement.copy() # substitute input clusters
    replacement[ENDPOINTS][1][INPUT_CLUSTERS] = [
        Basic.cluster_id,
        Groups.cluster_id,
        Scenes.cluster_id,
        TuyaTemperatureMeasurement,
        TuyaRelativeHumidity,
        TuyaPowerConfigurationCluster3AAA,
        NousManufClusterSZ_T04,
    ]


# _TZE200_whkgqxse has a similar configuration but it should be handled in zhaquirks.tuya.ts0601_sensor
