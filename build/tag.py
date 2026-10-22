"""Triaged concept/usage-mode/related tagging of reference chunks via the `claude` CLI.

MAGIC:
- Two-tier model routing. Every chunk is tagged by SONNET first (cheap). A chunk is
  re-tagged by OPUS only if the sonnet pass self-reports it as hard, OR a cheap
  deterministic signal flags it (see `should_escalate`). The opus result wins.
- Text-only: the chunk body is small enough to embed in the prompt, so NO tools are
  granted to the CLI (no Read needed, unlike extraction).
- Resumable: a chunk whose frontmatter already has a non-empty `concepts` list is
  skipped, so an interrupted run continues where it stopped.
- Auth + flat-rate billing are identical to build/extract.py (CLAUDE_CODE_OAUTH_TOKEN
  via the CLI; total_cost_usd is notional). Minted slugs are appended to
  build/artifacts/minted-slugs.jsonl for the later Opus consistency reconcile.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import frontmatter
import yaml

MODEL_DEFAULT = "sonnet"   # cheap first pass
MODEL_ESCALATE = "opus"    # hard chunks only

# Triage thresholds
CONFIDENCE_FLOOR = 0.6
NEW_SLUG_CEIL = 3
BODY_BYTES_CEIL = 15_000

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

USAGE_MODES = sorted({
    "sampler", "sequencer", "groovebox", "live-looper",
    "midi-sequencer", "midi-controller", "fx-processor", "mixer",
})


def build_tag_prompt(
    *, title: str, section: str | None, body: str,
    glossary_slugs: list[str], all_ids: list[str], self_id: str,
) -> str:
    """Return the -p prompt asking for a single JSON tagging object."""
    others = [i for i in all_ids if i != self_id]
    return (
        "You are tagging one section of an Elektron Octatrack reference manual for an "
        "AI-consumable knowledge base. Read the section and emit tags.\n\n"
        f"Section title: {title}\n"
        f"Section number: {section or '(none)'}\n"
        f"Chunk id: {self_id}\n\n"
        "Controlled USAGE_MODES vocabulary (use ONLY these, pick those the section "
        f"actually serves; may be empty): {USAGE_MODES}\n\n"
        "Existing concept-slug glossary (prefer these exact slugs; mint a new kebab-case "
        "slug ONLY when no existing slug fits a genuinely distinct concept):\n"
        f"{glossary_slugs}\n\n"
        "Valid `related` chunk ids (use ONLY ids from this list that the section "
        f"genuinely cross-references; may be empty):\n{others}\n\n"
        "--- SECTION BODY ---\n"
        f"{body}\n"
        "--- END BODY ---\n\n"
        "Output ONLY a JSON object (no prose, no markdown fence) with EXACTLY these keys:\n"
        '{\n'
        '  "concepts": [slugs, 3-10, from glossary or newly minted],\n'
        '  "usage_modes": [subset of the controlled vocabulary],\n'
        '  "related": [chunk ids from the valid list],\n'
        '  "new_slugs": [any slugs you minted that were NOT in the glossary],\n'
        '  "difficulty": "low" | "medium" | "high",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reason": "one short sentence justifying difficulty/confidence"\n'
        "}\n"
        "difficulty=high when the section is conceptually dense, spans many overlapping "
        "features, or the right slugs/usage_modes are genuinely ambiguous."
    )


def build_cli_cmd(prompt: str, model: str, claude_bin: str = "claude") -> list[str]:
    return [
        claude_bin, "-p", prompt,
        "--disallowedTools", "Read,WebFetch,WebSearch,Bash,Write,Edit,Glob,Grep",
        "--permission-mode", "default",
        "--model", model,
        "--output-format", "json",
    ]


def _extract_json_object(raw: str) -> dict:
    """Parse the first balanced top-level JSON object out of a model reply.

    Tolerates ```json fences and prose wrapped around the object (a failure mode
    seen with large chunks on opus), unlike a bare json.loads.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Scan for the first balanced {...}, respecting string literals.
    start = raw.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in result: {raw[:80]!r}")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:i + 1])
    raise ValueError(f"unbalanced JSON in result: {raw[:80]!r}")


def parse_tag_result(stdout: str) -> tuple[dict, dict]:
    """Return (tags_dict, full_cli_obj). Raises ValueError on CLI error / bad JSON."""
    obj = json.loads(stdout)
    if obj.get("is_error"):
        raise ValueError(f"CLI is_error: {obj.get('result')!r}")
    tags = _extract_json_object(obj["result"])
    return tags, obj


def should_escalate(tags: dict, body_bytes: int) -> tuple[bool, str]:
    """Decide whether to re-tag with Opus. Returns (escalate, reason)."""
    if tags.get("difficulty") == "high":
        return True, "difficulty=high"
    conf = tags.get("confidence")
    if isinstance(conf, (int, float)) and conf < CONFIDENCE_FLOOR:
        return True, f"confidence={conf:.2f}<{CONFIDENCE_FLOOR}"
    if len(tags.get("new_slugs", [])) >= NEW_SLUG_CEIL:
        return True, f"minted {len(tags['new_slugs'])} slugs"
    if body_bytes > BODY_BYTES_CEIL:
        return True, f"body {body_bytes}B>{BODY_BYTES_CEIL}"
    return False, ""


def _run(prompt: str, model: str, env: dict, timeout: int, attempts: int = 2) -> tuple[dict, dict]:
    last: Exception | None = None
    for _ in range(attempts):
        proc = subprocess.run(
            build_cli_cmd(prompt, model), cwd=str(_PROJECT_ROOT), env=env,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"CLI exit {proc.returncode}: {proc.stderr[:200]!r}")
        try:
            return parse_tag_result(proc.stdout)
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            last = exc  # transient empty/prose reply — retry once
    raise last  # type: ignore[misc]


def is_tagged(post: frontmatter.Post) -> bool:
    return bool(post.get("concepts"))


def tag_all(
    reference_dir: str,
    glossary_path: str,
    *,
    claude_bin: str = "claude",
    timeout: int = 300,
) -> None:
    if "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:
        raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN is not set.")

    ref = pathlib.Path(reference_dir)
    glossary = yaml.safe_load(pathlib.Path(glossary_path).read_text())
    glossary_slugs = sorted(glossary)

    paths = sorted(ref.glob("*.md"))
    all_ids = [frontmatter.load(p).get("id") for p in paths]

    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)

    minted_log = _PROJECT_ROOT / "build" / "artifacts" / "minted-slugs.jsonl"

    done = skipped = escalated = failed = 0
    for path in paths:
        post = frontmatter.load(path)
        if is_tagged(post):
            skipped += 1
            continue

        self_id = post.get("id")
        body = post.content
        prompt = build_tag_prompt(
            title=post.get("title", ""), section=post.get("section"),
            body=body, glossary_slugs=glossary_slugs,
            all_ids=all_ids, self_id=self_id,
        )

        try:
            tags, _ = _run(prompt, MODEL_DEFAULT, env, timeout)
        except (RuntimeError, ValueError, json.JSONDecodeError, KeyError,
                subprocess.TimeoutExpired) as exc:
            print(f"{path.name}: sonnet FAIL — {exc} — skipping", file=sys.stderr)
            failed += 1
            continue

        model_used = MODEL_DEFAULT
        esc, why = should_escalate(tags, len(body.encode()))
        if esc:
            try:
                tags, _ = _run(prompt, MODEL_ESCALATE, env, timeout)
                model_used = MODEL_ESCALATE
                escalated += 1
            except (RuntimeError, ValueError, json.JSONDecodeError, KeyError,
                    subprocess.TimeoutExpired) as exc:
                print(f"{path.name}: opus escalation FAIL ({why}) — {exc} — "
                      f"keeping sonnet tags", file=sys.stderr)

        # Sanitize against the controlled vocab / valid ids.
        valid_ids = set(all_ids)
        concepts = [s for s in tags.get("concepts", []) if isinstance(s, str)]
        usage_modes = [m for m in tags.get("usage_modes", []) if m in USAGE_MODES]
        related = [r for r in tags.get("related", []) if r in valid_ids and r != self_id]

        post["concepts"] = concepts
        post["usage_modes"] = usage_modes
        post["related"] = related
        path.write_text(frontmatter.dumps(post), encoding="utf-8")

        new_slugs = [s for s in tags.get("new_slugs", []) if s not in glossary]
        if new_slugs:
            with minted_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"chunk": self_id, "new_slugs": new_slugs,
                                     "model": model_used}) + "\n")

        print(f"{path.name}: [{model_used}] {len(concepts)} concepts, "
              f"{usage_modes}, conf={tags.get('confidence')}"
              + (f" ESC({why})" if esc else ""), file=sys.stderr)
        done += 1

    print(f"\nTagging complete: {done} done ({escalated} escalated to opus), "
          f"{skipped} skipped, {failed} failed.", file=sys.stderr)


if __name__ == "__main__":
    tag_all(
        sys.argv[1] if len(sys.argv) > 1 else "knowledge/reference",
        sys.argv[2] if len(sys.argv) > 2 else "build/inputs/concept-glossary.yaml",
    )
