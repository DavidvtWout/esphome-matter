"""Check the SDK source ownership and linked Init in an Ethernet CI build."""

import json
from pathlib import Path
import shlex
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
        "__idf_davidvtwout__esp_matter.dir" in rows[0]["command"],
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
compiler = Path(shlex.split(adapter["command"])[0])
require(
    compiler.name.endswith("g++"),
    "Expected the ESP cross-compiler in compile_commands.json",
)
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
print("Ethernet SDK source ownership and linked Init checks passed")
