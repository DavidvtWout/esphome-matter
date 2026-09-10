from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from esphome.components.binary_sensor import BinarySensor
from esphome.components.sensor import Sensor
from esphome.cpp_generator import MockObjClass

if TYPE_CHECKING:
    from .clusters import Cluster


@dataclass(frozen=True, slots=True)
class Attribute:
    id: int
    name: str | None  # CamelCase
    type: str
    # max: int | None = None
    # is_nullable: bool = False
    writable: bool = False
    optional: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data.get("name"),
            type=data["type"],
            writable=data["writable"],
            optional=data["optional"],
        )


@dataclass(frozen=True, slots=True)
class SensorAttribute:
    conf_key: str
    converter: str
    sensor_type: MockObjClass = field(default_factory=lambda: Sensor)
    features: tuple[str, ...] = ()
    code_driven: bool = False
    # Set by DeviceType:
    cluster: "Cluster | None" = None
    attribute: Attribute | None = None


# Arranged by Cluster, Attribute
SENSOR_ATTRIBUTES = {
    "BooleanState": {  # 0x0045
        "StateValue": SensorAttribute("boolean_state", "boolean_state", BinarySensor)
    },
    "OccupancySensing": {  # 0x0406
        "Occupancy": SensorAttribute("occupancy", "occupancy", BinarySensor)
    },
    "IlluminanceMeasurement": {  # 0x0400
        "MeasuredValue": SensorAttribute(
            "illuminance",
            "illuminance",
            code_driven=True,
        )
    },
    "TemperatureMeasurement": {  # 0x0402
        "MeasuredValue": SensorAttribute(
            "temperature",
            "temperature",
            code_driven=True,
        )
    },
    "PressureMeasurement": {  # 0x0403
        "MeasuredValue": SensorAttribute(
            "pressure",
            "pressure",
            code_driven=True,
        )
    },
    "FlowMeasurement": {  # 0x0404
        "MeasuredValue": SensorAttribute(
            "flow",
            "flow",
            code_driven=True,
        )
    },
    "RelativeHumidityMeasurement": {  # 0x0405
        "MeasuredValue": SensorAttribute(
            "relative_humidity",
            "percentage",
            code_driven=True,
        )
    },
    "ElectricalPowerMeasurement": {  # 0x0090
        "Voltage": SensorAttribute("voltage", "volts"),
        "ActiveCurrent": SensorAttribute("active_current", "ampere"),
        "ReactiveCurrent": SensorAttribute("reactive_current", "ampere"),
        "ApparentCurrent": SensorAttribute("apparent_current", "ampere"),
        "ActivePower": SensorAttribute("active_power", "watts"),
        "ReactivePower": SensorAttribute("reactive_power", "watts"),
        "ApparentPower": SensorAttribute("apparent_power", "watts"),
        "RMSVoltage": SensorAttribute("rms_voltage", "volts"),
        "RMSCurrent": SensorAttribute("rms_current", "ampere"),
        "RMSPower": SensorAttribute("rms_power", "watts"),
        "Frequency": SensorAttribute("frequency", "frequency"),
        "PowerFactor": SensorAttribute("power_factor", "percentage"),
        "NeutralCurrent": SensorAttribute("neutral_current", "ampere"),
    },
    "CarbonMonoxideConcentrationMeasurement": {  # 0x040C
        "MeasuredValue": SensorAttribute(
            "carbon_monoxide", "concentration", features=("NumericMeasurement",)
        )
    },
    "CarbonDioxideConcentrationMeasurement": {  # 0x040D
        "MeasuredValue": SensorAttribute(
            "carbon_dioxide", "concentration", features=("NumericMeasurement",)
        )
    },
    "NitrogenDioxideConcentrationMeasurement": {  # 0x0413
        "MeasuredValue": SensorAttribute(
            "nitrogen_dioxide", "concentration", features=("NumericMeasurement",)
        )
    },
    "OzoneConcentrationMeasurement": {  # 0x0415
        "MeasuredValue": SensorAttribute(
            "ozone", "concentration", features=("NumericMeasurement",)
        )
    },
    "PM25ConcentrationMeasurement": {  # 0x042A
        "MeasuredValue": SensorAttribute(
            "pm_2_5", "concentration", features=("NumericMeasurement",)
        )
    },
    "FormaldehydeConcentrationMeasurement": {  # 0x042B
        "MeasuredValue": SensorAttribute(
            "formaldehyde", "concentration", features=("NumericMeasurement",)
        )
    },
    "PM1ConcentrationMeasurement": {  # 0x042C
        "MeasuredValue": SensorAttribute(
            "pm_1", "concentration", features=("NumericMeasurement",)
        )
    },
    "PM10ConcentrationMeasurement": {  # 0x042D
        "MeasuredValue": SensorAttribute(
            "pm_10", "concentration", features=("NumericMeasurement",)
        )
    },
    "TotalVolatileOrganicCompoundsConcentrationMeasurement": {  # 0x042E
        "MeasuredValue": SensorAttribute(
            "total_voc", "concentration", features=("NumericMeasurement",)
        )
    },
    "RadonConcentrationMeasurement": {  # 0x042F
        "MeasuredValue": SensorAttribute(
            "radon", "concentration", features=("NumericMeasurement",)
        )
    },
    "SoilMeasurement": {  # 0x0430
        "SoilMoistureMeasuredValue": SensorAttribute("soil_moisture", "percentage")
    },
    # Not used by any device type?
    "SmokeConcentrationMeasurement": {  # 0x0434
        "MeasuredValue": SensorAttribute(
            "smoke_concentration",
            "concentration",
            features=("NumericMeasurement",),
        )
    },
}
