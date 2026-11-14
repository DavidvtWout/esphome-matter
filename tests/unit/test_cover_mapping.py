import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_cover_command_delegation_and_state_reporting(tmp_path):
    helpers = Path(__file__).with_name("cover_helpers")
    shutil.copytree(helpers, tmp_path, dirs_exist_ok=True)
    for name in ("matter_covers.cpp", "matter_covers.h"):
        shutil.copy2(ROOT / "components" / "matter" / name, tmp_path / name)
    for include in (
        "app-common/zap-generated/attributes/Accessors.h",
        "app/clusters/window-covering-server/WindowCoveringCluster.h",
        "platform/CHIPDeviceLayer.h",
        "esphome/components/cover/cover.h",
    ):
        path = tmp_path / include
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#include "runtime.h"\n')
    core = tmp_path / "esphome" / "core"
    core.mkdir(parents=True)
    (core / "defines.h").write_text("#define USE_MATTER\n#define USE_COVER\n")
    (core / "log.h").write_text("#define ESP_LOGW(...) ((void)0)\n")
    compiler = shutil.which("c++")
    assert compiler, "C++ compiler is required for cover adapter tests"
    binary = tmp_path / "cover-test"
    subprocess.run([
        compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-variable", "-pthread", "-I", str(tmp_path),
        str(tmp_path / "matter_covers.cpp"), str(tmp_path / "cover_mapping.cpp"),
        "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
