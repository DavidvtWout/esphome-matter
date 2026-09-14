import esphome.codegen as cg
from esphome import automation

matter_ns = cg.esphome_ns.namespace("matter")

MatterComponent = matter_ns.class_("MatterComponent", cg.Component)
MatterFactoryResetAction = matter_ns.class_(
    "MatterFactoryResetAction", automation.Action
)
MatterEndpointRef = matter_ns.class_("MatterEndpointRef")
MatterAttributeTrigger = matter_ns.class_("MatterAttributeTrigger", automation.Trigger)
MatterSendCommandAction = matter_ns.class_("MatterSendCommandAction", automation.Action)
