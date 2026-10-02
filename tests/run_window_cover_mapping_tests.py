"""Compile the unchanged production mapping with deterministic host interfaces."""

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="matter-cover-tests-") as directory:
        build = Path(directory)
        shutil.copytree(ROOT / "tests/cover_stubs", build, dirs_exist_ok=True)
        # Quote includes resolve beside the translation unit. Place the actual
        # source beside the interface stubs without rewriting its contents.
        for name in [
            "matter_covers.cpp",
            "matter_covers.h",
            "matter_cover_command_queue.h",
        ]:
            shutil.copy2(ROOT / "components/matter" / name, build / name)
        command = shlex.split(os.environ.get("CXX", "c++")) + [
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-variable",
            "-pthread",
            "-I",
            str(build),
            str(build / "matter_covers.cpp"),
            str(ROOT / "tests/test_window_cover_mapping.cpp"),
            "-o",
            str(build / "cover-tests"),
        ]
        subprocess.run(command, check=True)
        subprocess.run([str(build / "cover-tests")], check=True)


if __name__ == "__main__":
    main()
