#include "esphome/core/defines.h"
#if defined(USE_MATTER) && defined(USE_OPENTHREAD)

#include "esphome/components/openthread/openthread.h"
#include "esphome/core/log.h"

#include <lib/dnssd/platform/Dnssd.h>
#include <lib/support/CodeUtils.h>
#include <openthread/error.h>
#include <openthread/srp_client.h>
#include <platform/OpenThread/OpenThreadDnssdImpl.h>

#include <memory>
#include <new>
#include <string>
#include <vector>

namespace {

static const char *const TAG = "matter.dnssd";

const char *protocol_to_string(chip::Dnssd::DnssdServiceProtocol protocol) {
  switch (protocol) {
  case chip::Dnssd::DnssdServiceProtocol::kDnssdProtocolTcp:
    return "_tcp";
  case chip::Dnssd::DnssdServiceProtocol::kDnssdProtocolUdp:
    return "_udp";
  default:
    return nullptr;
  }
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
    const char *protocol = protocol_to_string(dnssd_service->mProtocol);
    if (protocol == nullptr)
      return false;
    return this->instance == dnssd_service->mName &&
           this->type == std::string(dnssd_service->mType) + "." + protocol;
  }
};

std::vector<std::unique_ptr<MatterSrpService>> matter_services;

CHIP_ERROR build_srp_service(const chip::Dnssd::DnssdService *service,
                             std::unique_ptr<MatterSrpService> &entry) {
  const char *protocol = protocol_to_string(service->mProtocol);
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

} // namespace

// connectedhomeip/src/platform/ESP32/DnssdImpl.cpp
extern "C" void esphome_matter_link_thread_dnssd() {}

namespace chip {
namespace Dnssd {

CHIP_ERROR ChipDnssdInit(DnssdAsyncReturnCallback init_callback,
                         DnssdAsyncReturnCallback, void *context) {
  ESP_LOGI(TAG, "Thread DNS-SD bridge linked");
  if (init_callback != nullptr) {
    init_callback(context, CHIP_NO_ERROR);
  }
  return CHIP_NO_ERROR;
}

void ChipDnssdShutdown() { ESP_LOGD(TAG, "ChipDnssdShutdown"); }

CHIP_ERROR ChipDnssdPublishService(const DnssdService *service,
                                   DnssdPublishCallback callback,
                                   void *context) {
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
    ESP_LOGD(TAG, "Publishing %s.%s via ESPHome OpenThread SRP", service->mName,
             entry->type.c_str());
    matter_services.push_back(std::move(entry));
  } else {
    ESP_LOGW(TAG, "Failed to publish %s.%s via ESPHome OpenThread SRP: %d",
             service->mName, entry->type.c_str(), error);
  }

  if (callback != nullptr) {
    callback(context, chip_error == CHIP_NO_ERROR ? service->mType : nullptr,
             chip_error == CHIP_NO_ERROR ? service->mName : nullptr,
             chip_error);
  }
  return chip_error;
}

CHIP_ERROR ChipDnssdRemoveServices() {
  auto lock = esphome::openthread::InstanceLock::try_acquire(2000);
  VerifyOrReturnError(static_cast<bool>(lock), CHIP_ERROR_INCORRECT_STATE);

  for (auto &entry : matter_services) {
    ESP_LOGD(TAG, "Marking SRP service for removal: %s.%s",
             entry->instance.c_str(), entry->type.c_str());
    entry->invalid = true;
  }
  return CHIP_NO_ERROR;
}

CHIP_ERROR ChipDnssdFinalizeServiceUpdate() {
  auto lock = esphome::openthread::InstanceLock::try_acquire(2000);
  VerifyOrReturnError(static_cast<bool>(lock), CHIP_ERROR_INCORRECT_STATE);

  otInstance *instance = lock.get_instance();
  for (auto it = matter_services.begin(); it != matter_services.end();) {
    if ((*it)->invalid) {
      ESP_LOGD(TAG, "Removing stale %s.%s from ESPHome OpenThread SRP",
               (*it)->instance.c_str(), (*it)->type.c_str());
      otSrpClientClearService(instance, &(*it)->service);
      it = matter_services.erase(it);
    } else {
      ++it;
    }
  }
  return CHIP_NO_ERROR;
}

CHIP_ERROR ChipDnssdBrowse(const char *type, DnssdServiceProtocol protocol,
                           chip::Inet::IPAddressType address_type,
                           chip::Inet::InterfaceId interface,
                           DnssdBrowseCallback callback, void *context,
                           intptr_t *browse_identifier) {
  ESP_LOGD(TAG, "Delegating Thread DNS-SD browse for %s",
           type != nullptr ? type : "(null)");
  return OpenThreadDnssdBrowse(type, protocol, address_type, interface,
                               callback, context, browse_identifier);
}

CHIP_ERROR ChipDnssdStopBrowse(intptr_t) { return CHIP_ERROR_NOT_IMPLEMENTED; }

CHIP_ERROR ChipDnssdResolve(DnssdService *browse_result,
                            chip::Inet::InterfaceId interface,
                            DnssdResolveCallback callback, void *context) {
  ESP_LOGD(TAG, "Delegating Thread DNS-SD resolve for %s",
           browse_result != nullptr ? browse_result->mName : "(null)");
  return OpenThreadDnssdResolve(browse_result, interface, callback, context);
}

void ChipDnssdResolveNoLongerNeeded(const char *) {}

CHIP_ERROR ChipDnssdReconfirmRecord(const char *, chip::Inet::IPAddress,
                                    chip::Inet::InterfaceId) {
  return CHIP_ERROR_NOT_IMPLEMENTED;
}

} // namespace Dnssd
} // namespace chip

#endif // USE_MATTER && USE_OPENTHREAD
