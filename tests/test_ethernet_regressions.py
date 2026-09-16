"""Host checks for Ethernet failure handling, NetworkID, and SDK adaptation."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "components/matter/esphome_matter_ethernet"


def run(*args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


class EthernetRegressions(unittest.TestCase):
    def test_delayed_start_is_rejected(self):
        for fixture in ("esp32-ethernet", "esp32-wifi-ethernet"):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as tmp:
                config = yaml.safe_load((ROOT / f"tests/configs/{fixture}.yaml").read_text())
                config["ethernet"]["enable_on_boot"] = False
                config["external_components"][0]["source"] = str(ROOT / "components")
                path = Path(tmp) / "invalid.yaml"
                path.write_text(yaml.safe_dump(config))
                result = run(sys.executable, "-m", "esphome", "config", str(path))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Matter requires ethernet.enable_on_boot: true", result.stdout + result.stderr)

    def test_iterator_and_init_failure(self):
        # Compile the actual adapter against small SDK/netif doubles. The real
        # P4/S3 firmware builds separately verify SDK compatibility and linking.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            headers = {
                "esp_netif.h": """
#pragma once
#include <cstring>
struct esp_netif_t { bool up; };
extern esp_netif_t *test_netif;
inline esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) {
  return std::strcmp(key, "ETH_DEF") == 0 ? test_netif : nullptr;
}
inline bool esp_netif_is_netif_up(esp_netif_t *netif) { return netif->up; }
""",
                "lib/support/logging/CHIPLogging.h": """
#pragma once
#define ChipLogProgress(...) ((void)0)
#define ChipLogError(...) ((void)0)
""",
                "platform/ESP32/NetworkCommissioningDriver.h": """
#pragma once
#include <cstddef>
#include <cstdint>
using CHIP_ERROR = int;
constexpr int CHIP_NO_ERROR = 0;
constexpr int CHIP_ERROR_INCORRECT_STATE = 1;
namespace chip::DeviceLayer::NetworkCommissioning {
constexpr size_t kMaxNetworkIDLen = 32;
struct Network { uint8_t networkID[32]; uint8_t networkIDLen; bool connected; };
struct NetworkIterator {
  virtual ~NetworkIterator() = default;
  virtual size_t Count() = 0;
  virtual bool Next(Network &) = 0;
  virtual void Release() = 0;
};
class ESPEthernetDriver {
 public:
  struct NetworkStatusChangeCallback {};
  virtual ~ESPEthernetDriver() = default;
  virtual NetworkIterator *GetNetworks() { return nullptr; }
  virtual CHIP_ERROR Init(NetworkStatusChangeCallback *callback);
};
}
""",
            }
            for filename, content in headers.items():
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            test = root / "test.cpp"
            test.write_text('''
#include <cassert>
#include <cstring>
#include <esp_netif.h>
#include "esphome_matter_ethernet_driver.h"
using namespace chip::DeviceLayer::NetworkCommissioning;
esp_netif_t *test_netif = nullptr;
int main() {
  ESPEthernetDriver &driver = ESPHomeEthernetDriver::GetInstance();
  assert(driver.Init(nullptr) == (CHIP_DEVICE_CONFIG_ENABLE_WIFI ? CHIP_NO_ERROR : CHIP_ERROR_INCORRECT_STATE));
  auto *it = driver.GetNetworks();
  Network value{};
  assert(it->Count() == 0 && !it->Next(value));
  it->Release();
  esp_netif_t netif{false};
  test_netif = &netif;
  assert(driver.Init(nullptr) == CHIP_NO_ERROR);
  it = driver.GetNetworks();
  assert(it->Count() == 1 && it->Next(value));
  assert(value.networkIDLen > 0 && value.networkIDLen <= kMaxNetworkIDLen);
  assert(!value.connected && !it->Next(value));
  Network disconnected = value;
  it->Release();
  netif.up = true;
  it = driver.GetNetworks();
  assert(it->Next(value) && value.connected && !it->Next(value));
  assert(value.networkIDLen == disconnected.networkIDLen);
  assert(std::memcmp(value.networkID, disconnected.networkID, value.networkIDLen) == 0);
  it->Release();
}
''')
            for wifi in (0, 1):
                with self.subTest(wifi=wifi):
                    binary = root / f"test-{wifi}"
                    result = run(shutil.which("c++"), "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                 f"-DCHIP_DEVICE_CONFIG_ENABLE_WIFI={wifi}", f"-I{root}", f"-I{ADAPTER}",
                                 str(ADAPTER / "ethernet_driver.cpp"), str(test), "-o", str(binary))
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = run(str(binary))
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cmake_symlinks_and_ambiguous_sources(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sdk = root / "sdk"
                platform = sdk / "connectedhomeip/connectedhomeip/src/platform/ESP32"
                platform.mkdir(parents=True)
                for filename in ("NetworkCommissioningDriver_Ethernet.cpp", "ESP32DnssdImpl.cpp"):
                    (platform / filename).write_text("// fixture\n")
                integration = sdk / "network_commissioning/integration.cpp"
                integration.parent.mkdir()
                original = "void f() { ESPEthernetDriver::GetInstance(); }\n"
                integration.write_text(original)
                alias = root / "sdk-alias"
                alias.symlink_to(sdk, target_is_directory=True)
                paths = [alias / file.relative_to(sdk) for file in (platform / "NetworkCommissioningDriver_Ethernet.cpp",
                          platform / "ESP32DnssdImpl.cpp", integration)]
                if duplicate:
                    extra = sdk / "other/NetworkCommissioningDriver_Ethernet.cpp"
                    extra.parent.mkdir()
                    extra.write_text("// duplicate\n")
                    paths.append(extra)
                sources = " ".join(f'"{path}"' for path in paths)
                (root / "CMakeLists.txt").write_text(f'''
cmake_minimum_required(VERSION 3.16)
project(adapter_test LANGUAGES CXX)
add_library(sdk STATIC {sources})
macro(idf_component_register)
endmacro()
function(idf_component_get_property output component property)
  if(property STREQUAL "COMPONENT_LIB")
    set(${{output}} sdk PARENT_SCOPE)
  else()
    set(${{output}} "{sdk}" PARENT_SCOPE)
  endif()
endfunction()
set(CONFIG_ENABLE_ETHERNET_TELEMETRY ON)
add_subdirectory("{ADAPTER}" adapter)
get_target_property(sources sdk SOURCES)
file(WRITE "${{CMAKE_BINARY_DIR}}/sources.txt" "${{sources}}")
''')
                result = run(shutil.which("cmake"), "-S", str(root), "-B", str(root / "build"))
                if duplicate:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Expected exactly one esp_matter Ethernet driver source", result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    sources = (root / "build/sources.txt").read_text()
                    self.assertNotIn("NetworkCommissioningDriver_Ethernet.cpp", sources)
                    self.assertEqual(sources.count("ESP32DnssdImpl.cpp"), 1)
                    generated = (root / "build/adapter/network_commissioning_integration.cpp").read_text()
                    self.assertIn("ESPHomeEthernetDriver::GetInstance()", generated)
                    self.assertEqual(integration.read_text(), original)


if __name__ == "__main__":
    unittest.main()
