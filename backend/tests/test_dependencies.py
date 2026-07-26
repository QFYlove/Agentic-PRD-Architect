from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "dotenv",
        "fastapi",
        "langgraph",
        "openai",
        "pydantic",
        "pydantic_settings",
        "sse_starlette",
        "uvicorn",
    ],
)
def test_direct_runtime_dependency_is_importable(module_name: str) -> None:
    assert import_module(module_name) is not None
