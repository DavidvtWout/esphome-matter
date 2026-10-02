import esphome.codegen as cg
from esphome import automation

matter_ns = cg.esphome_ns.namespace("matter")

MatterComponent = matter_ns.class_("MatterComponent", cg.Component)
MatterFactoryResetAction = matter_ns.class_(
    "MatterFactoryResetAction", automation.Action
)
MatterOpenCommissioningWindowAction = matter_ns.class_(
    "MatterOpenCommissioningWindowAction", automation.Action
)
MatterCloseCommissioningWindowAction = matter_ns.class_(
    "MatterCloseCommissioningWindowAction", automation.Action
)
MatterCancelCoverPendingAction = matter_ns.class_(
    "MatterCancelCoverPendingAction", automation.Action
)
MatterEndpointRef = matter_ns.class_("MatterEndpointRef")
MatterAttributeTrigger = matter_ns.class_("MatterAttributeTrigger", automation.Trigger)
MatterSetAttributeAction = matter_ns.class_(
    "MatterSetAttributeAction", automation.Action
)
MatterSendCommandAction = matter_ns.class_("MatterSendCommandAction", automation.Action)
