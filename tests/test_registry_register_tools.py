import harness.builtin_tools # noqa: F401
from harness.tools import ToolRegistry

def test_whether_builtin_tools_registered():
    ToolRegistry.initialize()
    definitions = ToolRegistry.definitions()

    assert "list_directory" in definitions
    assert "get_weather" in definitions
