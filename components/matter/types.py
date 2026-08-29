from esphome import automation
import esphome.codegen as cg


matter_ns = cg.esphome_ns.namespace("matter")
MatterComponent = matter_ns.class_("MatterComponent", cg.Component)
MatterEndpointRef = matter_ns.class_("MatterEndpointRef")
MatterLightMapping = matter_ns.class_("MatterLightMapping")
MatterSensorMapping = matter_ns.class_("MatterSensorMapping")
MatterBinarySensorMapping = matter_ns.class_("MatterBinarySensorMapping")

# Actions
MatterFactoryResetAction = matter_ns.class_(
    "MatterFactoryResetAction", automation.Action
)
MatterSendCommandAction = matter_ns.class_("MatterSendCommandAction", automation.Action)
MatterSetAttributeAction = matter_ns.class_(
    "MatterSetAttributeAction", automation.Action
)
