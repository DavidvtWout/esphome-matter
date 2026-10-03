from collections.abc import Generator

import pytest
from esphome.core import CORE

CORE.name = "matter-unit-tests"


@pytest.fixture(autouse=True)
def reset_core() -> Generator[None]:
    CORE.reset()
    CORE.name = "matter-unit-tests"
    yield
    CORE.reset()
