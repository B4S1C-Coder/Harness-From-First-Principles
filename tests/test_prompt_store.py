import pytest
from harness.prompts import PromptStore

def test_initialize(prompt_store):
    assert PromptStore._connection is not None
    assert PromptStore._queries

def test_initialize_twice_raises_error(prompt_store, tmp_path):
    with pytest.raises(RuntimeError, match="already initialized"):
        PromptStore.initialize(
            database=tmp_path / "another.db",
            sql_directory=tmp_path,
        )

def test_add_new_prompt(prompt_store):
    prompt_id = PromptStore.add_prompt(
        "system", "You are a helpful assistant", description="System Prompt"
    )

    assert isinstance(prompt_id, int)
    assert PromptStore.load_prompt("system") == "You are a helpful assistant"

def test_add_new_prompt_creates_first_version(prompt_store):
    _ = PromptStore.add_prompt(
        "system", "Test"
    )

    assert PromptStore.load_prompt("system", version=1) == "Test"

def test_changed_template_creates_new_version(prompt_store):
    PromptStore.add_prompt("system", "v1")
    PromptStore.add_prompt("system", "v2")

    assert PromptStore.load_prompt("system", version=1) == "v1"
    assert PromptStore.load_prompt("system", version=2) == "v2"
    assert PromptStore.load_prompt("system") == "v2"

def test_unchanged_template_does_not_create_new_version(prompt_store):
    first_id  = PromptStore.add_prompt("system", "v1")
    second_id = PromptStore.add_prompt("system", "v1")

    assert first_id == second_id
    assert PromptStore.load_prompt("system", version=1) == "v1"

    with pytest.raises(LookupError):
        PromptStore.load_prompt("system", version=2)

def test_new_version_keeps_same_prompt_family_id(prompt_store):
    first_id  = PromptStore.add_prompt("system", "v1")
    second_id = PromptStore.add_prompt("system", "v2")

    assert first_id == second_id

def test_different_prompt_names_creates_separate_families(prompt_store):
    first_id  = PromptStore.add_prompt("system", "sp")
    second_id = PromptStore.add_prompt("user", "up")

    assert first_id != second_id

def test_load_latest_version(prompt_store):
    PromptStore.add_prompt("system", "v1")
    PromptStore.add_prompt("system", "v2")
    PromptStore.add_prompt("system", "v3")

    assert PromptStore.load_prompt("system") == "v3"

def test_load_specific_version(prompt_store):
    PromptStore.add_prompt("system", "v1")
    PromptStore.add_prompt("system", "v2")

    assert PromptStore.load_prompt("system", version=1) == "v1"
    assert PromptStore.load_prompt("system", version=2) == "v2"

def test_load_nonexistent_prompt_raises_error(prompt_store):
    with pytest.raises(LookupError, match="Prompt 'unknown'"):
        PromptStore.load_prompt("unknown")

def test_load_nonexistent_version_raises_error(prompt_store):
    PromptStore.add_prompt("system", "v1")

    with pytest.raises(LookupError, match = "version 2"):
        PromptStore.load_prompt("system", version=2)

def test_load_prompt_formats_template(prompt_store):
    PromptStore.add_prompt(
        "greeting",
        "Hello, {name} - {age}"
    )

    result = PromptStore.load_prompt("greeting", name="Foo", age=69)

    assert result == "Hello, Foo - 69"

def test_add_prompt_without_initialization():
    PromptStore.close()

    with pytest.raises(RuntimeError, match="initialize"):
        PromptStore.add_prompt("system", "Template")

def test_load_prompt_without_initialization():
    PromptStore.close()

    with pytest.raises(RuntimeError, match="initialize"):
        PromptStore.load_prompt("system")