from collections.abc import Generator

from esphome.core import CORE
import pytest

CORE.name = "matter-unit-tests"


@pytest.fixture(autouse=True)
def reset_core() -> Generator[None]:
    CORE.reset()
    CORE.name = "matter-unit-tests"
    yield
    CORE.reset()
