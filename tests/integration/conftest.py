import os
import re
from pathlib import Path

import pytest
from esphome.core import CORE

REPO_DIR = Path(__file__).parents[2]
ESP_MATTER_COMPONENT = "davidvtwout__esp_matter"
LEGACY_ENDPOINT_HEADER = (
    Path("components")
    / "esp_matter"
    / "data_model"
    / "legacy"
    / "esp_matter_endpoint_impl.h"
)

CORE.name = "matter-integration-tests"

_MATRIX_PARAMETERS = {
    "device_type": "Device types",
    "cluster": "Clusters",
}
_matrix_columns: dict[str, list[str]] = {
    parameter: [] for parameter in _MATRIX_PARAMETERS
}
_matrix_rows: dict[str, dict[str, dict[str, str]]] = {
    parameter: {} for parameter in _MATRIX_PARAMETERS
}


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "allowed_to_fail: permit an assertion failure until this data model entry is required",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for columns in _matrix_columns.values():
        columns.clear()
    for rows in _matrix_rows.values():
        rows.clear()

    for item in items:
        callspec = getattr(item, "callspec", None)
        if callspec is None:
            continue
        for parameter in _MATRIX_PARAMETERS:
            if parameter not in callspec.params:
                continue

            value = callspec.params[parameter]
            entity = value.name if parameter == "device_type" else value.conf_key
            column = item.originalname.removeprefix("test_")
            if column not in _matrix_columns[parameter]:
                _matrix_columns[parameter].append(column)
            _matrix_rows[parameter].setdefault(entity, {})
            item.user_properties.extend(
                (
                    ("matrix_parameter", parameter),
                    ("matrix_entity", entity),
                    (
                        "matrix_allowed_to_fail",
                        item.get_closest_marker("allowed_to_fail") is not None,
                    ),
                )
            )
            break


def _matrix_item(report: pytest.TestReport) -> tuple[str, str] | None:
    properties = dict(report.user_properties)
    parameter = properties.get("matrix_parameter")
    entity = properties.get("matrix_entity")
    if not isinstance(parameter, str) or not isinstance(entity, str):
        return None
    return parameter, entity


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item):
    outcome = yield
    report = outcome.get_result()
    marker = item.get_closest_marker("allowed_to_fail")
    if marker is not None and report.when == "call" and report.failed:
        report.outcome = "skipped"
        report.wasxfail = marker.kwargs.get("reason", "Allowed to fail")


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    matrix_item = _matrix_item(report)
    if matrix_item is None:
        return

    if report.when == "call":
        if report.skipped and hasattr(report, "wasxfail"):
            result = "x"
        elif report.skipped:
            result = "s"
        elif report.passed and hasattr(report, "wasxfail"):
            result = "X"
        elif report.passed:
            result = (
                "a"
                if dict(report.user_properties).get("matrix_allowed_to_fail")
                else "."
            )
        else:
            result = "F"
    elif report.failed:
        result = "E"
    else:
        return

    parameter, entity = matrix_item
    column = report.nodeid.split("::")[-1].split("[")[0].removeprefix("test_")
    _matrix_rows[parameter][entity][column] = result


@pytest.hookimpl(tryfirst=True)
def pytest_report_teststatus(report: pytest.TestReport):
    if _matrix_item(report) is None or report.when != "call":
        return None
    if report.skipped and hasattr(report, "wasxfail"):
        return "xfailed", "", ""
    if report.skipped:
        return "skipped", "", ""
    if report.passed and hasattr(report, "wasxfail"):
        return "xpassed", "", ""
    if report.passed:
        return "passed", "", ""
    return "failed", "", ""


def pytest_terminal_summary(terminalreporter) -> None:
    terminalreporter.section("Matter data model support")
    for parameter, title in _MATRIX_PARAMETERS.items():
        rows = _matrix_rows[parameter]
        if not rows:
            continue

        columns = _matrix_columns[parameter]
        name_width = max(len(entity) for entity in rows)
        terminalreporter.write_line(title, bold=True)
        for entity, results in rows.items():
            terminalreporter.write(f"{entity:<{name_width}}  ")
            for column in columns:
                result = results.get(column, "?")
                markup = {
                    ".": {"green": True},
                    "a": {"yellow": True},
                    "F": {"red": True, "bold": True},
                    "E": {"red": True, "bold": True},
                    "x": {"yellow": True},
                    "X": {"yellow": True},
                    "s": {"yellow": True},
                    "?": {"yellow": True},
                }[result]
                terminalreporter.write("." if result == "a" else result, **markup)
            terminalreporter.write_line("")
        terminalreporter.write_line("")


@pytest.fixture(scope="session")
def esp_matter_source() -> Path:
    if source := os.environ.get("ESP_MATTER_SOURCE"):
        component_path = Path(source)
        assert component_path.is_dir(), f"Invalid ESP_MATTER_SOURCE: {component_path}"
        kconfig = component_path / "components" / "esp_matter" / "Kconfig"
        assert re.search(
            r"config ESP_MATTER_ENABLE_GENERATED_DATA_MODEL\s+"
            r"bool .*?\s+default n(?:\s|$)",
            kconfig.read_text(),
            re.DOTALL,
        ), "esp-matter no longer defaults to its legacy data model"
        assert (
            "CONFIG_ESP_MATTER_ENABLE_GENERATED_DATA_MODEL"
            not in (REPO_DIR / "components" / "matter" / "__init__.py").read_text()
        ), "esphome-matter now explicitly configures the generated data model"
    else:
        component_paths = sorted(
            (REPO_DIR / "tests" / "configs" / ".esphome" / "build").glob(
                f"*/managed_components/{ESP_MATTER_COMPONENT}"
            )
        )
        assert component_paths, (
            "esp-matter source is unavailable; compile an ESPHome test configuration first"
        )
        component_path = component_paths[0]
        sdkconfig_paths = sorted(component_path.parents[1].glob("sdkconfig.*"))
        assert sdkconfig_paths, "Missing sdkconfig for resolved esp-matter component"
        assert (
            "# CONFIG_ESP_MATTER_ENABLE_GENERATED_DATA_MODEL is not set"
            in sdkconfig_paths[0].read_text()
        ), "This test currently expects esp-matter's legacy data model"

    return component_path


@pytest.fixture(scope="session")
def esp_matter_device_type_ids(esp_matter_source: Path) -> set[int]:
    header = esp_matter_source / LEGACY_ENDPOINT_HEADER

    assert header.is_file(), f"Missing esp-matter legacy data model header: {header}"

    return {
        int(value, 16)
        for value in re.findall(
            r"^#define ESP_MATTER_[A-Z0-9_]+_DEVICE_TYPE_ID (0x[0-9A-F]+)$",
            header.read_text(),
            re.MULTILINE,
        )
    }
