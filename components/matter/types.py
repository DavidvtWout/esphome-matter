from esphome import automation
import esphome.codegen as cg


matter_ns = cg.esphome_ns.namespace("matter")

MatterComponent = matter_ns.class_("MatterComponent", cg.Component)
MatterFactoryResetAction = matter_ns.class_(
    "MatterFactoryResetAction", automation.Action
)
MatterEndpointRef = matter_ns.class_("MatterEndpointRef")
MatterInvokeBoundCommandAction = matter_ns.class_(
    "MatterInvokeBoundCommandAction", automation.Action
)
MatterTurnOnAction = matter_ns.class_("MatterTurnOnAction", automation.Action)
MatterTurnOffAction = matter_ns.class_("MatterTurnOffAction", automation.Action)
MatterToggleAction = matter_ns.class_("MatterToggleAction", automation.Action)
MatterDimAction = matter_ns.class_("MatterDimAction", automation.Action)
MatterDimStopAction = matter_ns.class_("MatterDimStopAction", automation.Action)
