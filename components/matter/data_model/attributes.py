from dataclasses import dataclass, field

from esphome.components.binary_sensor import BinarySensor
from esphome.components.sensor import Sensor
from esphome.cpp_generator import MockObjClass


@dataclass(frozen=True, slots=True)
class SensorAttribute:
    conf_key: str
    sensor_type: MockObjClass = field(default_factory=lambda: Sensor)
    unit: str | None = None  # TODO: map to unit converters


# Arranged by Cluster, Attribute
SENSOR_ATTRIBUTES = {
    "BooleanState": {  # 0x0045
        "StateValue": SensorAttribute("contact", BinarySensor)
    },
    "ElectricalPowerMeasurement": {  # 0x0090
        "Voltage": SensorAttribute("voltage"),
        "ActiveCurrent": SensorAttribute("active_current"),
        "ReactiveCurrent": SensorAttribute("reactive_current"),
        "ApparentCurrent": SensorAttribute("apparent_current"),
        "ActivePower": SensorAttribute("active_power"),
        "ReactivePower": SensorAttribute("reactive_power"),
        "ApparentPower": SensorAttribute("apparent_power"),
        "RMSVoltage": SensorAttribute("rms_voltage"),
        "RMSCurrent": SensorAttribute("rms_current"),
        "RMSPower": SensorAttribute("rms_power"),
        "Frequency": SensorAttribute("frequency"),
        "PowerFactor": SensorAttribute("power_factor"),
    },
    "IlluminanceMeasurement": {  # 0x0400
        "MeasuredValue": SensorAttribute("illuminance")
    },
    "TemperatureMeasurement": {  # 0x0402
        "MeasuredValue": SensorAttribute("temperature")
    },
    "PressureMeasurement": {  # 0x0403
        "MeasuredValue": SensorAttribute("pressure")
    },
    "FlowMeasurement": {  # 0x0404
        "MeasuredValue": SensorAttribute("flow")
    },
    "RelativeHumidityMeasurement": {  # 0x0405
        "MeasuredValue": SensorAttribute("relative_humidity")
    },
    "OccupancySensing": {  # 0x0406
        "Occupancy": SensorAttribute("occupancy", BinarySensor)
    },
    "CarbonMonoxideConcentrationMeasurement": {  # 0x040C
        "MeasuredValue": SensorAttribute("carbon_monoxide")
    },
    "CarbonDioxideConcentrationMeasurement": {  # 0x040D
        "MeasuredValue": SensorAttribute("carbon_dioxide")
    },
    "NitrogenDioxideConcentrationMeasurement": {  # 0x0413
        "MeasuredValue": SensorAttribute("nitrogen_dioxide")
    },
    "OzoneConcentrationMeasurement": {  # 0x0415
        "MeasuredValue": SensorAttribute("ozone")
    },
    "PM2.5ConcentrationMeasurement": {  # 0x042A
        "MeasuredValue": SensorAttribute("pm_2_5")
    },
    "FormaldehydeConcentrationMeasurement": {  # 0x042B
        "MeasuredValue": SensorAttribute("formaldehyde")
    },
    "PM1ConcentrationMeasurement": {  # 0x042C
        "MeasuredValue": SensorAttribute("pm_1")
    },
    "PM10ConcentrationMeasurement": {  # 0x042D
        "MeasuredValue": SensorAttribute("pm_10")
    },
    "TotalVolatileOrganicCompoundsConcentrationMeasurement": {  # 0x042E
        "MeasuredValue": SensorAttribute("total_voc")
    },
    "RadonConcentrationMeasurement": {  # 0x042F
        "MeasuredValue": SensorAttribute("radon")
    },
}
