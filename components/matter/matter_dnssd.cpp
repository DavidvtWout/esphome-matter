#include "esphome/core/defines.h"
#if defined(USE_MATTER) && (defined(USE_OPENTHREAD) || defined(USE_WIFI))

#ifdef USE_OPENTHREAD
#include "esphome/components/openthread/openthread.h"
#endif // USE_OPENTHREAD
#include "esphome/core/log.h"

#include <inet/IPAddress.h>
#include <lib/dnssd/platform/Dnssd.h>
#include <lib/support/CHIPMem.h>
#include <lib/support/CodeUtils.h>
#ifdef USE_OPENTHREAD
#include <openthread/error.h>
#include <openthread/srp_client.h>
#include <platform/OpenThread/OpenThreadDnssdImpl.h>
#endif // USE_OPENTHREAD
#ifdef USE_WIFI
#include <platform/ESP32/ESP32DnssdImpl.h>
#endif // USE_WIFI

#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <vector>

namespace {

static const char *const TAG = "matter.dnssd";

const char *safe_string(const char *value) {
  return value != nullptr ? value : "(null)";
}

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

struct MatterResolveContext {
  chip::Dnssd::DnssdResolveCallback callback;
  void *context;
  char name[chip::Dnssd::Common::kInstanceNameMaxLength + 1] = "";
  char type[chip::Dnssd::kDnssdTypeMaxSize + 1] = "";
  chip::Dnssd::DnssdServiceProtocol protocol =
      chip::Dnssd::DnssdServiceProtocol::kDnssdProtocolUnknown;
};

void resolve_callback(void *context, chip::Dnssd::DnssdService *service,
                      const chip::Span<chip::Inet::IPAddress> &addresses,
                      CHIP_ERROR error) {
  auto *resolve_context = static_cast<MatterResolveContext *>(context);

  if (error != CHIP_NO_ERROR) {
#ifdef USE_OPENTHREAD
    if (error.IsRange(chip::ChipError::Range::kOpenThread)) {
      otError ot_error = static_cast<otError>(error.GetValue());
      ESP_LOGW(TAG,
               "Resolve %s.%s.%s failed: chip=0x%08" CHIP_ERROR_INTEGER_FORMAT
               " openthread=%u (%s)",
               safe_string(resolve_context->name),
               safe_string(resolve_context->type),
               protocol_to_string(resolve_context->protocol), error.AsInteger(),
               static_cast<unsigned>(ot_error),
               otThreadErrorToString(ot_error));
    } else
#endif // USE_OPENTHREAD
      ESP_LOGW(TAG, "Resolve %s.%s.%s failed: %" CHIP_ERROR_FORMAT,
               safe_string(resolve_context->name),
               safe_string(resolve_context->type),
               protocol_to_string(resolve_context->protocol), error.Format());
  } else if (service == nullptr) {
    ESP_LOGW(TAG, "Can't resolve because DnssdService isn't initialized");
  } else {
    ESP_LOGD(TAG, "Resolved %s.%s.%s as %s:%u", safe_string(service->mName),
             safe_string(service->mType),
             protocol_to_string(service->mProtocol),
             safe_string(service->mHostName), service->mPort);
    for (const auto &address : addresses) {
      char address_string[chip::Inet::IPAddress::kMaxStringLength];
      address.ToString(address_string);
      ESP_LOGV(TAG, "%s address: %s", safe_string(service->mHostName),
               address_string);
    }
  }

  if (resolve_context->callback != nullptr) {
    resolve_context->callback(resolve_context->context, service, addresses,
                              error);
  }
  chip::Platform::Delete(resolve_context);
}

#ifdef USE_OPENTHREAD
const char *protocol_to_srp_suffix(chip::Dnssd::DnssdServiceProtocol protocol) {
  const char *protocol_string = protocol_to_string(protocol);
  return protocol_string[0] == '?' ? nullptr : protocol_string;
}

CHIP_ERROR map_ot_error(otError error) {
  switch (error) {
  case OT_ERROR_NONE:
    return CHIP_NO_ERROR;
  case OT_ERROR_INVALID_ARGS:
    return CHIP_ERROR_INVALID_ARGUMENT;
  case OT_ERROR_NO_BUFS:
    return CHIP_ERROR_NO_MEMORY;
  case OT_ERROR_INVALID_STATE:
    return CHIP_ERROR_INCORRECT_STATE;
  default:
    return CHIP_ERROR_INTERNAL;
  }
}

struct MatterSrpService {
  std::string instance;
  std::string type;
  std::vector<std::string> subtype_storage;
  std::vector<const char *> subtype_ptrs;
  std::vector<std::string> txt_key_storage;
  std::vector<std::vector<uint8_t>> txt_value_storage;
  std::vector<otDnsTxtEntry> txt_entries;
  otSrpClientService service{};
  bool invalid{false};

  bool matches(const chip::Dnssd::DnssdService *dnssd_service) const {
    const char *protocol = protocol_to_srp_suffix(dnssd_service->mProtocol);
    if (protocol == nullptr)
      return false;
    return this->instance == dnssd_service->mName &&
           this->type == std::string(dnssd_service->mType) + "." + protocol;
  }
};

std::vector<std::unique_ptr<MatterSrpService>> matter_services;

CHIP_ERROR build_srp_service(const chip::Dnssd::DnssdService *service,
                             std::unique_ptr<MatterSrpService> &entry) {
  const char *protocol = protocol_to_srp_suffix(service->mProtocol);
  VerifyOrReturnError(protocol != nullptr, CHIP_ERROR_INVALID_ARGUMENT);

  entry.reset(new (std::nothrow) MatterSrpService());
  VerifyOrReturnError(entry != nullptr, CHIP_ERROR_NO_MEMORY);

  entry->instance = service->mName;
  entry->type = std::string(service->mType) + "." + protocol;

  entry->subtype_storage.reserve(service->mSubTypeSize);
  for (size_t i = 0; i < service->mSubTypeSize; i++) {
    entry->subtype_storage.emplace_back(service->mSubTypes[i]);
  }
  entry->subtype_ptrs.reserve(entry->subtype_storage.size() + 1);
  for (const auto &subtype : entry->subtype_storage) {
    entry->subtype_ptrs.push_back(subtype.c_str());
  }
  entry->subtype_ptrs.push_back(nullptr);

  entry->txt_key_storage.reserve(service->mTextEntrySize);
  entry->txt_value_storage.reserve(service->mTextEntrySize);
  entry->txt_entries.resize(service->mTextEntrySize);
  for (size_t i = 0; i < service->mTextEntrySize; i++) {
    VerifyOrReturnError(service->mTextEntries != nullptr,
                        CHIP_ERROR_INVALID_ARGUMENT);
    const auto &txt = service->mTextEntries[i];
    VerifyOrReturnError(txt.mKey != nullptr, CHIP_ERROR_INVALID_ARGUMENT);

    entry->txt_key_storage.emplace_back(txt.mKey);
    entry->txt_value_storage.emplace_back();
    if (txt.mDataSize > 0) {
      VerifyOrReturnError(txt.mData != nullptr, CHIP_ERROR_INVALID_ARGUMENT);
      entry->txt_value_storage.back().assign(txt.mData,
                                             txt.mData + txt.mDataSize);
    }
  }
  for (size_t i = 0; i < service->mTextEntrySize; i++) {
    entry->txt_entries[i].mKey = entry->txt_key_storage[i].c_str();
    entry->txt_entries[i].mValue = entry->txt_value_storage[i].empty()
                                       ? nullptr
                                       : entry->txt_value_storage[i].data();
    entry->txt_entries[i].mValueLength = entry->txt_value_storage[i].size();
  }

  entry->service.mName = entry->type.c_str();
  entry->service.mInstanceName = entry->instance.c_str();
  entry->service.mSubTypeLabels = entry->subtype_ptrs.data();
  entry->service.mTxtEntries =
      entry->txt_entries.empty() ? nullptr : entry->txt_entries.data();
  entry->service.mNumTxtEntries = entry->txt_entries.size();
  entry->service.mPort = service->mPort;
  return CHIP_NO_ERROR;
}
#endif // USE_OPENTHREAD
} // namespace

extern "C" void esphome_matter_link_dnssd() {}

namespace chip {
namespace Dnssd {

CHIP_ERROR ChipDnssdInit(DnssdAsyncReturnCallback init_callback,
                         DnssdAsyncReturnCallback error_callback,
                         void *context) {
  ESP_LOGD(TAG, "DNS-SD initialized");
#ifdef USE_OPENTHREAD
  // Prevent OpenThreadDnssdInit from being called.
  if (init_callback != nullptr) {
    init_callback(context, CHIP_NO_ERROR);
  }
  return CHIP_NO_ERROR;
#endif // USE_OPENTHREAD
#ifdef USE_WIFI
  return EspDnssdInit(init_callback, error_callback, context);
#endif // USE_WIFI
}

void ChipDnssdShutdown() { ESP_LOGV(TAG, "ChipDnssdShutdown"); }

CHIP_ERROR ChipDnssdPublishService(const DnssdService *service,
                                   DnssdPublishCallback callback,
                                   void *context) {
  if (service == nullptr) {
    ESP_LOGW(TAG, "Can't publish because DnssdService isn't initialized");
  } else {
    ESP_LOGD(TAG, "Publishing %s.%s.%s as %s:%u", service->mName,
             service->mType, protocol_to_string(service->mProtocol),
             service->mHostName, service->mPort);
  }

#ifdef USE_OPENTHREAD
  VerifyOrReturnError(service != nullptr, CHIP_ERROR_INVALID_ARGUMENT);

  std::unique_ptr<MatterSrpService> entry;
  ReturnErrorOnFailure(build_srp_service(service, entry));

  auto lock = esphome::openthread::InstanceLock::try_acquire(2000);
  VerifyOrReturnError(static_cast<bool>(lock), CHIP_ERROR_INCORRECT_STATE);

  otInstance *instance = lock.get_instance();
  for (auto it = matter_services.begin(); it != matter_services.end();) {
    if ((*it)->matches(service)) {
      otSrpClientClearService(instance, &(*it)->service);
      it = matter_services.erase(it);
    } else {
      ++it;
    }
  }

  otError error = otSrpClientAddService(instance, &entry->service);
  CHIP_ERROR chip_error = map_ot_error(error);
  if (chip_error == CHIP_NO_ERROR) {
    matter_services.push_back(std::move(entry));
  } else {
    ESP_LOGW(TAG, "Publish failed: %d", error);
  }

  if (callback != nullptr) {
    callback(context, chip_error == CHIP_NO_ERROR ? service->mType : nullptr,
             chip_error == CHIP_NO_ERROR ? service->mName : nullptr,
             chip_error);
  }
  return chip_error;
#endif // USE_OPENTHREAD
#ifdef USE_WIFI
  return EspDnssdPublishService(service, callback, context);
#endif // USE_WIFI
}

CHIP_ERROR ChipDnssdRemoveServices() {
  ESP_LOGD(TAG, "Remove services");
#ifdef USE_OPENTHREAD
  auto lock = esphome::openthread::InstanceLock::try_acquire(2000);
  VerifyOrReturnError(static_cast<bool>(lock), CHIP_ERROR_INCORRECT_STATE);

  for (auto &entry : matter_services) {
    ESP_LOGD(TAG, "Marking service for removal: %s.%s", entry->instance.c_str(),
             entry->type.c_str());
    entry->invalid = true;
  }
  return CHIP_NO_ERROR;
#endif // USE_OPENTHREAD
#ifdef USE_WIFI
  return EspDnssdRemoveServices();
#endif // USE_WIFI
}

CHIP_ERROR ChipDnssdFinalizeServiceUpdate() {
  ESP_LOGD(TAG, "Finalize service update");
#ifdef USE_OPENTHREAD
  auto lock = esphome::openthread::InstanceLock::try_acquire(2000);
  VerifyOrReturnError(static_cast<bool>(lock), CHIP_ERROR_INCORRECT_STATE);

  otInstance *instance = lock.get_instance();
  for (auto it = matter_services.begin(); it != matter_services.end();) {
    if ((*it)->invalid) {
      ESP_LOGD(TAG, "Removing stale service: %s.%s", (*it)->instance.c_str(),
               (*it)->type.c_str());
      otSrpClientClearService(instance, &(*it)->service);
      it = matter_services.erase(it);
    } else {
      ++it;
    }
  }
#endif // USE_OPENTHREAD
  return CHIP_NO_ERROR;
}

CHIP_ERROR ChipDnssdBrowse(const char *type, DnssdServiceProtocol protocol,
                           chip::Inet::IPAddressType address_type,
                           chip::Inet::InterfaceId interface,
                           DnssdBrowseCallback callback, void *context,
                           intptr_t *browse_identifier) {
  ESP_LOGD(TAG, "Browse type=%s protocol=%s", type != nullptr ? type : "(null)",
           protocol_to_string(protocol));
#ifdef USE_OPENTHREAD
  return OpenThreadDnssdBrowse(type, protocol, address_type, interface,
                               callback, context, browse_identifier);
#endif // USE_OPENTHREAD
#ifdef USE_WIFI
  return EspDnssdBrowse(type, protocol, address_type, interface, callback,
                        context, browse_identifier);
#endif // USE_WIFI
}

CHIP_ERROR ChipDnssdStopBrowse(intptr_t) { return CHIP_ERROR_NOT_IMPLEMENTED; }

CHIP_ERROR ChipDnssdResolve(DnssdService *service,
                            chip::Inet::InterfaceId interface,
                            DnssdResolveCallback callback, void *context) {

  if (service == nullptr) {
    ESP_LOGW(TAG, "Can't resolve because DnssdService isn't initialized");
    return CHIP_ERROR_INVALID_ARGUMENT;
  } else {
    ESP_LOGD(TAG, "Resolving %s.%s.%s", service->mName, service->mType,
             protocol_to_string(service->mProtocol));
  }

  auto *resolve_context = chip::Platform::New<MatterResolveContext>();
  VerifyOrReturnError(resolve_context != nullptr, CHIP_ERROR_NO_MEMORY);
  resolve_context->callback = callback;
  resolve_context->context = context;
  strncpy(resolve_context->name, service->mName, sizeof(resolve_context->name));
  resolve_context->name[sizeof(resolve_context->name) - 1] = '\0';
  strncpy(resolve_context->type, service->mType, sizeof(resolve_context->type));
  resolve_context->type[sizeof(resolve_context->type) - 1] = '\0';
  resolve_context->protocol = service->mProtocol;

#ifdef USE_OPENTHREAD
  CHIP_ERROR error = OpenThreadDnssdResolve(service, interface,
                                            resolve_callback, resolve_context);
#endif // USE_OPENTHREAD
#ifdef USE_WIFI
  CHIP_ERROR error =
      EspDnssdResolve(service, interface, resolve_callback, resolve_context);
#endif // USE_WIFI
  if (error != CHIP_NO_ERROR) {
    ESP_LOGW(TAG, "Resolve start failed: %" CHIP_ERROR_FORMAT, error.Format());
    chip::Platform::Delete(resolve_context);
  }
  return error;
}

void ChipDnssdResolveNoLongerNeeded(const char *instance_name) {}

CHIP_ERROR ChipDnssdReconfirmRecord(const char *hostname, chip::Inet::IPAddress,
                                    chip::Inet::InterfaceId) {
  return CHIP_ERROR_NOT_IMPLEMENTED;
}

} // namespace Dnssd
} // namespace chip

#endif // USE_MATTER && (USE_OPENTHREAD || USE_WIFI)
