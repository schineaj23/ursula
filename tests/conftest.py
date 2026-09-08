import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", help="also run tests that call the real APIs"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="needs --live (calls real APIs)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
