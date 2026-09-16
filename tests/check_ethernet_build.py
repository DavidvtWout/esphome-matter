"""Check the SDK source ownership and linked Init in an Ethernet CI build."""

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import yaml


config_path = Path(sys.argv[1])
name = yaml.safe_load(config_path.read_text())["esphome"]["name"]
build = config_path.parent / ".esphome" / "build" / name / ".pioenvs" / name
commands = json.loads((build / "compile_commands.json").read_text())


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def sdk_source(filename):
    rows = [row for row in commands if Path(row["file"]).name == filename]
    require(len(rows) == 1, f"Expected exactly one compilation of {filename}")
    require(
        "__idf_davidvtwout__esp_matter.dir" in (rows[0].get("command") or shlex.join(rows[0]["arguments"])),
        f"{filename} must compile in the SDK target",
    )
    return rows[0]


adapter = sdk_source("ethernet_driver.cpp")
sdk_source("ESP32DnssdImpl.cpp")
require(
    not any(
        Path(row["file"]).name == "NetworkCommissioningDriver_Ethernet.cpp"
        for row in commands
    ),
    "The SDK's original Ethernet driver must not also be compiled",
)
# CMake may prefix the compiler with ccache/sccache (or provide arguments).
arguments = adapter.get("arguments") or shlex.split(adapter["command"])
compilers = [arg for arg in arguments if Path(arg).name.endswith("-g++")]
require(len(compilers) == 1, "Could not identify the ESP cross-compiler in the compile command")
compiler = Path(shutil.which(compilers[0]) or compilers[0])
nm = compiler.with_name(compiler.name.removesuffix("g++") + "nm")
symbols = subprocess.check_output(
    [str(nm), "--defined-only", str(build / "firmware.elf")], text=True
)
init = "_ZN4chip11DeviceLayer20NetworkCommissioning17ESPEthernetDriver4InitEPNS1_8Internal10BaseDriver27NetworkStatusChangeCallbackE"
require(
    sum(line.split()[-1] == init for line in symbols.splitlines() if line.split()) == 1,
    "Expected exactly one linked Ethernet Init definition",
)
archive = build / "esp-idf" / "davidvtwout__esp_matter" / "libdavidvtwout__esp_matter.a"
archive_symbols = subprocess.check_output(
    [str(nm), "-A", "--defined-only", str(archive)], text=True
)
definitions = [
    line for line in archive_symbols.splitlines()
    if line.split() and line.split()[-1] == init
]
require(
    len(definitions) == 1 and ":ethernet_driver.cpp.o:" in definitions[0],
    "The SDK archive must contain only the adapter's Ethernet Init definition",
)
get_networks = "_ZN4chip11DeviceLayer20NetworkCommissioning21ESPHomeEthernetDriver11GetNetworksEv"
require(
    sum(line.split()[-1] == get_networks for line in symbols.splitlines() if line.split()) == 1,
    "Expected one out-of-line Ethernet GetNetworks definition",
)
network_definitions = [
    line for line in archive_symbols.splitlines()
    if line.split() and line.split()[-1] == get_networks
]
require(
    len(network_definitions) == 1 and ":ethernet_driver.cpp.o:" in network_definitions[0],
    "GetNetworks must be supplied only by the adapter",
)
sdk_source("network_commissioning_integration.cpp")
require(
    not any(row["file"].endswith("/network_commissioning/integration.cpp") for row in commands),
    "The original commissioning integration must not also be compiled",
)
integration_init = "_Z54ESPMatterNetworkCommissioningClusterServerInitCallbackt"
integration_definitions = [
    line for line in archive_symbols.splitlines()
    if line.split() and line.split()[-1] == integration_init
]
require(
    len(integration_definitions) == 1
    and ":network_commissioning_integration.cpp.o:" in integration_definitions[0],
    "The cluster must use the adapted driver factory; clean stale build artifacts if needed",
)
print("Ethernet SDK source ownership and linked driver checks passed")
