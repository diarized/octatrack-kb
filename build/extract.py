"""Per-page vision extraction → Markdown, driven via the `claude` CLI in headless mode.

MAGIC:
- Auth: CLAUDE_CODE_OAUTH_TOKEN environment variable (set via `claude setup-token`).
  The Messages API (x-api-key / ANTHROPIC_API_KEY) is NOT used. The OAuth token only
  works through the `claude` CLI, not the SDK.
- Each page = one `claude -p` headless subprocess call.  The model uses the Read tool
  to load the page PNG from disk; the page text layer (OCR) is embedded directly in
  the prompt as a label-spelling hint.
- Flat-rate subscription: we MEASURE tokens via usage.jsonl for observability.
  The `total_cost_usd` value reported by the CLI is NOTIONAL (API-equivalent pricing),
  not real money charged against a subscription.
- Resume is free: any page whose output .md already exists is skipped, so a crashed
  or interrupted run continues exactly where it left off.
- Per-page timeout guards the subprocess so one stuck page cannot hang a 478-page run.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

MODEL = "sonnet"  # CLI alias. Switched opus→sonnet (2026-06-10): an opus pass hit
                  # the subscription rate ceiling at ~151/478 (327 fast-failures);
                  # sonnet is lighter on quota and prototyped with good page fidelity.

# Project root: two levels up from this file (build/extract.py → octatrack-kb/)
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


def build_prompt(instruction: str, png_path: str, text_hint: str) -> str:
    """Return the full -p prompt string for one page extraction call.

    The prompt embeds the absolute PNG path, an explicit instruction to use the
    Read tool to load that image, and the verbatim text-layer hint for label
    spelling correction.
    """
    return (
        f"{instruction}\n\n"
        f"---\n\n"
        f"Page image: {png_path}\n\n"
        f"Use the Read tool to load that image file before responding.\n\n"
        f"Text layer hint for label spelling (may be unordered, may have OCR artefacts):\n"
        f"{text_hint}\n\n"
        f"Extract this page as Markdown per your instructions."
    )


def build_cli_cmd(
    prompt: str,
    model: str = MODEL,
    claude_bin: str = "claude",
) -> list[str]:
    """Return the argv list for a headless `claude -p` call.

    Includes --output-format json, --allowedTools Read, --disallowedTools for
    all write/network tools, --permission-mode default, and --model.
    """
    return [
        claude_bin,
        "-p", prompt,
        "--allowedTools", "Read",
        "--disallowedTools", "WebFetch,WebSearch,Bash,Write,Edit,Glob,Grep",
        "--permission-mode", "default",
        "--model", model,
        "--output-format", "json",
    ]


def should_skip(out_dir: pathlib.Path, page: int) -> bool:
    """True iff the output .md for this page already exists (resume support)."""
    return (out_dir / f"page-{page:04d}.md").exists()


def parse_result(stdout: str) -> tuple[str, dict, dict]:
    """Parse the JSON stdout from a headless `claude -p --output-format json` call.

    Returns:
        (markdown_string, usage_dict, full_parsed_obj)

    Raises:
        ValueError: if obj["is_error"] is True, with a message containing the
                    error fields so a bad page is visible, not silently written.
    """
    obj = json.loads(stdout)
    if obj.get("is_error"):
        raise ValueError(
            f"is_error=True from CLI; result={obj.get('result')!r}; "
            f"error fields: { {k: v for k, v in obj.items() if k != 'result'} }"
        )
    md = obj["result"]
    usage = obj.get("usage", {})
    return md, usage, obj


def extract_all(
    render_dir: str,
    out_dir: str,
    prompt_path: str,
    model: str = MODEL,
    claude_bin: str = "claude",
    timeout: int = 300,
) -> None:
    """Extract all pages from render_dir into out_dir using the claude CLI.

    Requires CLAUDE_CODE_OAUTH_TOKEN in the environment (injected by the caller).
    Does NOT fall back to ANTHROPIC_API_KEY.
    """
    if "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:
        raise RuntimeError(
            "CLAUDE_CODE_OAUTH_TOKEN is not set. "
            "Run `claude setup-token` and export the token before invoking extract_all."
        )

    render = pathlib.Path(render_dir)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    instruction = pathlib.Path(prompt_path).read_text(encoding="utf-8")
    manifest = json.loads((render / "manifest.json").read_text())

    # Build subprocess env: inherit everything (so the token is present) but
    # remove ANTHROPIC_API_KEY to avoid the CLI falling back to the SDK auth path.
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)

    done = skipped = failed = 0

    for entry in manifest:
        page = entry["page"]

        if should_skip(out, page):
            skipped += 1
            continue

        png_path = str(pathlib.Path(entry["png"]).resolve())
        text_hint = pathlib.Path(entry["txt"]).read_text(encoding="utf-8")

        prompt = build_prompt(instruction, png_path, text_hint)
        cmd = build_cli_cmd(prompt, model=model, claude_bin=claude_bin)

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(_PROJECT_ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            print(
                f"page {page}: TIMEOUT after {timeout}s — skipping (will retry on re-run)",
                file=sys.stderr,
            )
            failed += 1
            continue

        if proc.returncode != 0:
            print(
                f"page {page}: CLI exited {proc.returncode}; "
                f"stderr={proc.stderr[:200]!r} — skipping",
                file=sys.stderr,
            )
            failed += 1
            continue

        try:
            md, usage, obj = parse_result(proc.stdout)
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            print(f"page {page}: parse error — {exc} — skipping", file=sys.stderr)
            failed += 1
            continue

        # Write markdown output
        (out / f"page-{page:04d}.md").write_text(md, encoding="utf-8")

        # Append usage JSONL record (notional cost, not real subscription billing)
        usage_record = {
            "page": page,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
            "notional_cost_usd": obj.get("total_cost_usd"),
        }
        with (out / "usage.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(usage_record) + "\n")

        print(
            f"page {page}: {usage.get('input_tokens', 0)} in / "
            f"{usage.get('output_tokens', 0)} out "
            f"(cache_read={usage.get('cache_read_input_tokens', 0)})",
            file=sys.stderr,
        )
        done += 1

    print(
        f"\nExtraction complete: {done} done, {skipped} skipped, {failed} failed.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    extract_all(sys.argv[1], sys.argv[2], sys.argv[3])
