#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_WIFI)

#include "esphome/core/log.h"

#include <inet/IPAddress.h>
#include <lib/dnssd/platform/Dnssd.h>
#include <lib/support/CHIPMem.h>
#include <lib/support/CodeUtils.h>
#include <platform/CHIPDeviceLayer.h>
#include <platform/ESP32/ESP32DnssdImpl.h>
#include <platform/ESP32/ESP32Utils.h>

#include <new>

namespace {

static const char *const TAG = "matter.dnssd";

const char *protocol_to_string(chip::Dnssd::DnssdServiceProtocol protocol) {
  switch (protocol) {
  case chip::Dnssd::DnssdServiceProtocol::kDnssdProtocolTcp:
    return "_tcp";
  case chip::Dnssd::DnssdServiceProtocol::kDnssdProtocolUdp:
    return "_udp";
  default:
    return "?";
  }
}

struct WifiResolveContext {
  chip::Dnssd::DnssdResolveCallback callback;
  void *context;
};

void resolve_callback(void *context, chip::Dnssd::DnssdService *service,
                      const chip::Span<chip::Inet::IPAddress> &addresses,
                      CHIP_ERROR error) {
  auto *resolve_context = static_cast<WifiResolveContext *>(context);

  if (service != nullptr) {
    ESP_LOGD(TAG, "resolved %s.%s.%s as %s:%u", service->mName, service->mType,
             protocol_to_string(service->mProtocol), service->mHostName,
             service->mPort);
  } else {
    ESP_LOGW(TAG, "resolved service=(null)");
  }
  for (const auto &address : addresses) {
    char address_string[chip::Inet::IPAddress::kMaxStringLength];
    address.ToString(address_string);
    ESP_LOGV(TAG, "%s address: %s", service->mHostName, address_string);
  }

  if (resolve_context->callback != nullptr) {
    resolve_context->callback(resolve_context->context, service, addresses,
                              error);
  }
  chip::Platform::Delete(resolve_context);
}

} // namespace

// connectedhomeip/src/platform/ESP32/DnssdImpl.cpp
extern "C" void esphome_matter_link_wifi_dnssd() {}

namespace chip {
namespace Dnssd {

CHIP_ERROR ChipDnssdInit(DnssdAsyncReturnCallback init_callback,
                         DnssdAsyncReturnCallback error_callback,
                         void *context) {
  ESP_LOGI(TAG, "Wi-Fi DNS-SD bridge linked");
  return EspDnssdInit(init_callback, error_callback, context);
}

void ChipDnssdShutdown() { ESP_LOGD(TAG, "ChipDnssdShutdown"); }

CHIP_ERROR ChipDnssdPublishService(const DnssdService *service,
                                   DnssdPublishCallback callback,
                                   void *context) {
  if (service == nullptr) {
    ESP_LOGW(TAG, "Can't publish because DnssdService isn't initialized");
  } else {
    ESP_LOGD(TAG, "publishing %s.%s.%s as %s:%u", service->mName,
             service->mType, protocol_to_string(service->mProtocol),
             service->mHostName, service->mPort);
  }

  return EspDnssdPublishService(service, callback, context);
}

CHIP_ERROR ChipDnssdRemoveServices() {
  ESP_LOGD(TAG, "remove services");
  return EspDnssdRemoveServices();
}

CHIP_ERROR ChipDnssdFinalizeServiceUpdate() {
  ESP_LOGD(TAG, "finalize service update");
  return CHIP_NO_ERROR;
}

CHIP_ERROR ChipDnssdBrowse(const char *type, DnssdServiceProtocol protocol,
                           chip::Inet::IPAddressType address_type,
                           chip::Inet::InterfaceId interface,
                           DnssdBrowseCallback callback, void *context,
                           intptr_t *browse_identifier) {
  ESP_LOGD(TAG, "browse type=%s protocol=%s", type != nullptr ? type : "(null)",
           protocol_to_string(protocol));
  return EspDnssdBrowse(type, protocol, address_type, interface, callback,
                        context, browse_identifier);
}

CHIP_ERROR ChipDnssdStopBrowse(intptr_t) { return CHIP_ERROR_NOT_IMPLEMENTED; }

CHIP_ERROR ChipDnssdResolve(DnssdService *service,
                            chip::Inet::InterfaceId interface,
                            DnssdResolveCallback callback, void *context) {

  if (service == nullptr) {
    ESP_LOGW(TAG, "Can't resolve because DnssdService isn't initialized");
  } else {
    ESP_LOGD(TAG, "resolving %s.%s.%s", service->mName, service->mType,
             protocol_to_string(service->mProtocol));
  }

  auto *resolve_context = chip::Platform::New<WifiResolveContext>();
  VerifyOrReturnError(resolve_context != nullptr, CHIP_ERROR_NO_MEMORY);
  resolve_context->callback = callback;
  resolve_context->context = context;

  CHIP_ERROR error =
      EspDnssdResolve(service, interface, resolve_callback, resolve_context);
  if (error != CHIP_NO_ERROR) {
    ESP_LOGW(TAG, "Wi-Fi DNS-SD resolve start failed: %" CHIP_ERROR_FORMAT,
             error.Format());
    chip::Platform::Delete(resolve_context);
  }
  return error;
}

void ChipDnssdResolveNoLongerNeeded(const char *instance_name) {
  ESP_LOGV(TAG, "resolve no longer needed for %s",
           instance_name != nullptr ? instance_name : "(null)");
}

CHIP_ERROR ChipDnssdReconfirmRecord(const char *hostname, chip::Inet::IPAddress,
                                    chip::Inet::InterfaceId) {
  ESP_LOGD(TAG, "reconfirm hostname=%s",
           hostname != nullptr ? hostname : "(null)");
  return CHIP_ERROR_NOT_IMPLEMENTED;
}

} // namespace Dnssd
} // namespace chip

#endif // USE_MATTER && USE_WIFI
