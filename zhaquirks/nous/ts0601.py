"""Nous temp and humidity sensors."""

from typing import Dict

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
    TuyaPowerConfigurationCluster3AAA,
    TuyaTemperatureMeasurement,
    TuyaRelativeHumidity,
    TemperatureUnit,
    ValueAlarm,
)
from zhaquirks.tuya.mcu import (
    TuyaMCUCluster,
    DPToAttributeMapping,
)


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

    signature = NousClimateSensorE6.signature.copy()
    signature[MODELS_INFO] = [ # substitute models info
        ("_TZE200_locansqn", "TS0601"),
        #("_TZE200_lve3dvpy", "TS0601"), # untested but using same configuration on z2mqtt
        #("_TZE200_c7emyjom", "TS0601"),
    ]

    replacement = NousClimateSensorE6.replacement.copy()
    replacement[ENDPOINTS][1][INPUT_CLUSTERS] = [ # substitute input clusters
        Basic.cluster_id,
        Groups.cluster_id,
        Scenes.cluster_id,
        TuyaTemperatureMeasurement,
        TuyaRelativeHumidity,
        TuyaPowerConfigurationCluster3AAA,
        NousManufClusterSZ_T04,
    ]


# _TZE200_whkgqxse has similar configuration - should be handled in zhaquirks.tuya.ts0601_sensor
