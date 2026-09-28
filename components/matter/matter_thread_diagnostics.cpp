#include "esphome/core/defines.h"

#if defined(USE_MATTER) && defined(USE_OPENTHREAD)

#include "esphome/components/openthread/openthread.h"

#include <app/clusters/thread-network-diagnostics-server/DirectThreadNetworkDiagnosticsProvider.h>

namespace {

using Provider = chip::app::Clusters::ThreadNetworkDiagnostics::
    DirectThreadNetworkDiagnosticsProvider;

extern "C" CHIP_ERROR real_read_attribute(
    Provider *provider, chip::AttributeId attribute_id,
    chip::app::AttributeValueEncoder
        &encoder) asm("__real__"
                      "ZN4chip3app8Clusters24ThreadNetworkDiagnostics38DirectTh"
                      "readNetworkDiagnosticsProvider13ReadAttributeEmRNS0_"
                      "21AttributeValueEncoderE");

extern "C" CHIP_ERROR wrapped_read_attribute(
    Provider *provider, chip::AttributeId attribute_id,
    chip::app::AttributeValueEncoder
        &encoder) asm("__wrap__"
                      "ZN4chip3app8Clusters24ThreadNetworkDiagnostics38DirectTh"
                      "readNetworkDiagnosticsProvider13ReadAttributeEmRNS0_"
                      "21AttributeValueEncoderE");

extern "C" CHIP_ERROR
wrapped_read_attribute(Provider *provider, chip::AttributeId attribute_id,
                       chip::app::AttributeValueEncoder &encoder) {
  // The direct provider assumes Matter owns the OpenThread task. In ESPHome the
  // OT task runs independently, so protect every provider access to OT-owned
  // state (including pointers and list iterators) for the complete encoding.
  auto lock = esphome::openthread::InstanceLock::acquire();
  return real_read_attribute(provider, attribute_id, encoder);
}

} // namespace

#endif // USE_MATTER && USE_OPENTHREAD
