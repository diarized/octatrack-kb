import json
import pathlib
import pytest
from build.extract import build_prompt, build_cli_cmd, should_skip, parse_result


def test_should_skip_when_output_exists(tmp_path):
    (tmp_path / "page-0001.md").write_text("done")
    assert should_skip(tmp_path, 1) is True
    assert should_skip(tmp_path, 2) is False


def test_build_prompt_contains_image_path_and_hint():
    p = build_prompt("INSTR", "/abs/page-0016.png", "LABELS")
    assert "/abs/page-0016.png" in p
    assert "LABELS" in p
    assert "Read" in p


def test_build_cli_cmd_has_json_read_and_model():
    cmd = build_cli_cmd("PROMPT", model="opus")
    assert "-p" in cmd
    assert "PROMPT" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--allowedTools") + 1] == "Read"
    assert cmd[cmd.index("--model") + 1] == "opus"
    j = cmd.index("--disallowedTools")
    assert "WebFetch" in cmd[j + 1] and "Bash" in cmd[j + 1]


def test_build_cli_cmd_default_binary_is_claude():
    cmd = build_cli_cmd("PROMPT")
    assert cmd[0] == "claude"


def test_build_cli_cmd_custom_binary():
    cmd = build_cli_cmd("PROMPT", claude_bin="/usr/local/bin/claude")
    assert cmd[0] == "/usr/local/bin/claude"


def test_parse_result_extracts_markdown_and_usage():
    stdout = json.dumps({
        "result": "# Heading\nbody",
        "is_error": False,
        "total_cost_usd": 0.33,
        "usage": {"input_tokens": 10, "output_tokens": 5,
                  "cache_creation_input_tokens": 2, "cache_read_input_tokens": 0},
    })
    md, usage, obj = parse_result(stdout)
    assert md.startswith("# Heading")
    assert usage["input_tokens"] == 10
    assert obj["total_cost_usd"] == 0.33


def test_parse_result_raises_on_error():
    stdout = json.dumps({"is_error": True, "result": "boom"})
    with pytest.raises(ValueError, match="is_error"):
        parse_result(stdout)
