// matter_dnssd.cpp
//
// Linker-override replacements for the chip::Dnssd::ChipDnsd*() platform functions.
//
// Why this file exists
// --------------------
// connectedhomeip gates its ESP32 DNS-SD backend (EspDnssdInit / EspDnssdPublishService etc.)
// behind #if CHIP_DEVICE_CONFIG_ENABLE_WIFI || CHIP_DEVICE_CONFIG_ENABLE_ETHERNET.
// We set both to 0 because:
//   - CONFIG_ENABLE_WIFI_STATION=n: required to prevent CHIP from driving esp_wifi and racing
//     ESPHome's wifi component.
//   - CONFIG_ENABLE_ETHERNET_TELEMETRY=n: on ESP32-C6, enabling it crashes kconfgen because
//     CHIP's Kconfig omits GPIO_RANGE_MAX defaults for that target.
//
// With both flags 0, all ChipDnsd*() functions in DnssdImpl.cpp compile to no-ops. This file
// provides strong-symbol replacements that call ESP-IDF's mdns component directly, bypassing
// the gates. The linker prefers definitions from application .o files over archive members,
// so these replace the CHIP library's no-ops without touching any CHIP source.
//
// We deliberately omit the mdns_hostname_set() call that EspDnssdPublishService() makes —
// Matter services are registered under ESPHome's current hostname, keeping them consistent with
// _esphomelib._tcp. Matter commissioners follow SRV → A/AAAA regardless of hostname text.

#include "esphome/core/defines.h"
#ifdef USE_MATTER

#include <mdns.h>
#include <esp_log.h>

#include <lib/dnssd/platform/Dnssd.h>
#include <lib/support/CHIPMem.h>
#include <lib/support/CodeUtils.h>
#include <lib/support/logging/CHIPLogging.h>

static const char * const TAG = "matter_dnssd";

namespace chip {
namespace Dnssd {

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static const char * GetProtocol(DnssdServiceProtocol protocol)
{
    return protocol == DnssdServiceProtocol::kDnssdProtocolTcp ? "_tcp" : "_udp";
}

// ---------------------------------------------------------------------------
// Init / Shutdown
// ---------------------------------------------------------------------------

CHIP_ERROR ChipDnssdInit(DnssdAsyncReturnCallback initCallback, DnssdAsyncReturnCallback errorCallback, void * context)
{
    // ESPHome's mdns component already called mdns_init(). On ESP-IDF 5.x, calling
    // mdns_init() a second time returns ESP_ERR_INVALID_STATE. Don't call it. The
    // daemon is already running and we can use it directly.
    ESP_LOGD(TAG, "ChipDnssdInit called");
    initCallback(context, CHIP_NO_ERROR);
    return CHIP_NO_ERROR;
}

void ChipDnssdShutdown() {}

// ---------------------------------------------------------------------------
// Advertising
// ---------------------------------------------------------------------------

CHIP_ERROR ChipDnssdPublishService(const DnssdService * service, DnssdPublishCallback callback, void * context)
{
    CHIP_ERROR error = CHIP_NO_ERROR;
    mdns_txt_item_t * items = nullptr;
    esp_err_t espError = ESP_OK;
    const char * proto = GetProtocol(service->mProtocol);

    // Build TXT record array.
    VerifyOrExit(service->mTextEntrySize <= UINT8_MAX, error = CHIP_ERROR_INVALID_ARGUMENT);
    if (service->mTextEntries && service->mTextEntrySize > 0)
    {
        items = static_cast<mdns_txt_item_t *>(
            chip::Platform::MemoryCalloc(service->mTextEntrySize, sizeof(mdns_txt_item_t)));
        VerifyOrExit(items != nullptr, error = CHIP_ERROR_NO_MEMORY);
        for (size_t i = 0; i < service->mTextEntrySize; i++)
        {
            items[i].key   = service->mTextEntries[i].mKey;
            items[i].value = reinterpret_cast<const char *>(service->mTextEntries[i].mData);
        }
    }

    // Remove all instances of this service type — CHIP generates a new random instance name
    // on every re-advertise, so checking by instance name leaves stale entries behind.
    while (mdns_service_exists(service->mType, proto, nullptr))
        mdns_service_remove(service->mType, proto);

    ESP_LOGD(TAG, "mDNS publish: %s.%s.%s port=%u",
             service->mName, service->mType, proto, service->mPort);
    espError = mdns_service_add(service->mName, service->mType, proto, service->mPort,
                                items, service->mTextEntrySize);
    if (espError != ESP_OK)
    {
        ChipLogError(DeviceLayer, "mdns_service_add failed for %s.%s.%s: %s",
                     service->mName, service->mType, proto, esp_err_to_name(espError));
    }
    VerifyOrExit(espError == ESP_OK, error = CHIP_ERROR_INTERNAL);

    for (size_t i = 0; i < service->mSubTypeSize; i++)
    {
        esp_err_t subtypeErr = mdns_service_subtype_add_for_host(
            service->mName, service->mType, proto, nullptr, service->mSubTypes[i]);
        if (subtypeErr != ESP_OK)
        {
            ChipLogError(DeviceLayer, "Failed to add mDNS subtype %s: %s",
                         service->mSubTypes[i], esp_err_to_name(subtypeErr));
        }
    }

exit:
    chip::Platform::MemoryFree(items);
    // ESP32 platform publishes synchronously; callback is not invoked (matches EspDnssdPublishService).
    return error;
}

CHIP_ERROR ChipDnssdRemoveServices()
{
    ESP_LOGD(TAG, "ChipDnssdRemoveServices called");
    while (mdns_service_exists("_matter", "_tcp", nullptr))
        mdns_service_remove("_matter", "_tcp");
    while (mdns_service_exists("_matterc", "_udp", nullptr))
        mdns_service_remove("_matterc", "_udp");
    while (mdns_service_exists("_matterd", "_udp", nullptr))
        mdns_service_remove("_matterd", "_udp");
    return CHIP_NO_ERROR;
}

CHIP_ERROR ChipDnssdFinalizeServiceUpdate()
{
    return CHIP_NO_ERROR;
}

// ---------------------------------------------------------------------------
// Discovery (controller-side) — not needed; return harmless values
// ---------------------------------------------------------------------------

CHIP_ERROR ChipDnssdBrowse(const char *, DnssdServiceProtocol, chip::Inet::IPAddressType,
                           chip::Inet::InterfaceId, DnssdBrowseCallback, void *, intptr_t *)
{
    return CHIP_NO_ERROR;
}

CHIP_ERROR ChipDnssdStopBrowse(intptr_t)
{
    return CHIP_ERROR_NOT_IMPLEMENTED;
}

CHIP_ERROR ChipDnssdResolve(DnssdService *, chip::Inet::InterfaceId, DnssdResolveCallback, void *)
{
    return CHIP_NO_ERROR;
}

void ChipDnssdResolveNoLongerNeeded(const char *) {}

CHIP_ERROR ChipDnssdReconfirmRecord(const char *, chip::Inet::IPAddress, chip::Inet::InterfaceId)
{
    return CHIP_ERROR_NOT_IMPLEMENTED;
}

} // namespace Dnssd
} // namespace chip

#endif // USE_MATTER
