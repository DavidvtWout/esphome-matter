from dataclasses import dataclass, field

import esphome.codegen as cg
from esphome.components.binary_sensor import BinarySensor
from esphome.components.sensor import Sensor
from esphome.cpp_generator import MockObjClass


@dataclass(frozen=True, slots=True)
class Attribute:
    id: int
    name: str | None  # CamelCase
    type: str
    # max: int | None = None
    define: str | None = None
    # is_nullable: bool = False
    writable: bool = False
    optional: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data.get("name"),
            type=data["type"],
            define=data["define"],
            writable=data["writable"],
            optional=data["optional"],
        )


@dataclass(frozen=True, slots=True)
class SensorAttribute:
    conf_key: str
    converter: str
    sensor_type: MockObjClass = field(default_factory=lambda: Sensor)
    features: tuple[str, ...] = ()

    async def register(
        self,
        var,
        endpoint_id: int,
        cluster_id: int,
        attribute_id: int,
        config: dict,
    ):
        sensor = await cg.get_variable(config[self.conf_key])
        converter = cg.RawExpression(
            f"esphome::matter::sensor_converter::{self.converter}"
        )
        if self.sensor_type is BinarySensor:
            cg.add(
                var.register_binary_sensor_attribute(
                    sensor, endpoint_id, cluster_id, attribute_id, converter
                )
            )
        else:
            cg.add(
                var.register_sensor_attribute(
                    sensor, endpoint_id, cluster_id, attribute_id, converter
                )
            )


# Arranged by Cluster, Attribute
SENSOR_ATTRIBUTES = {
    "BooleanState": {  # 0x0045
        "StateValue": SensorAttribute("contact", "boolean_state", BinarySensor)
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
    "IlluminanceMeasurement": {  # 0x0400
        "MeasuredValue": SensorAttribute("illuminance", "illuminance")
    },
    "TemperatureMeasurement": {  # 0x0402
        "MeasuredValue": SensorAttribute("temperature", "temperature")
    },
    "PressureMeasurement": {  # 0x0403
        "MeasuredValue": SensorAttribute("pressure", "pressure")
    },
    "FlowMeasurement": {  # 0x0404
        "MeasuredValue": SensorAttribute("flow", "flow")
    },
    "RelativeHumidityMeasurement": {  # 0x0405
        "MeasuredValue": SensorAttribute("relative_humidity", "percentage")
    },
    "OccupancySensing": {  # 0x0406
        "Occupancy": SensorAttribute("occupancy", "occupancy", BinarySensor)
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
    "SmokeConcentrationMeasurement": {  # 0x0434
        "MeasuredValue": SensorAttribute(
            "smoke_concentration",
            "concentration",
            features=("NumericMeasurement",),
        )
    },
}
