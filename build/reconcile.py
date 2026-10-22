"""Consistency reconcile for concept slugs (Task 13 Step 3-4).

Two auditable steps:
  generate  — Opus reads the full slug census and emits a canonicalization map
              (alias -> canonical, plus a drop list of OCR-noise / non-concept
              slugs). Saved to build/artifacts/slug-reconcile.json for inspection.
  apply     — deterministically rewrite every reference chunk's `concepts` through
              the map (dropping noise, de-duplicating, preserving order) and refresh
              build/inputs/concept-glossary.yaml with the surviving canonical slugs.

MAGIC: the LLM only PROPOSES the mapping; application is pure Python, so the result
is reviewable and re-runnable. Auth/billing identical to build/tag.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import frontmatter
import yaml

from build.tag import _extract_json_object  # reuse robust JSON parsing

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
MAP_PATH = _PROJECT_ROOT / "build" / "artifacts" / "slug-reconcile.json"
CENSUS_PATH = _PROJECT_ROOT / "build" / "artifacts" / "slug-census.json"


def build_reconcile_prompt(census: dict[str, int]) -> str:
    listing = "\n".join(f"{v:3}  {k}" for k, v in
                        sorted(census.items(), key=lambda kv: (-kv[1], kv[0])))
    return (
        "You are normalizing a controlled vocabulary of concept slugs for an Elektron "
        "Octatrack knowledge base. Below is every concept slug currently tagged across "
        "149 manual sections, with its usage count.\n\n"
        "Your job: collapse synonyms/duplicates onto ONE canonical slug, and drop slugs "
        "that are OCR noise or not real concepts.\n\n"
        "Rules:\n"
        "- Prefer the more frequent / cleaner slug as canonical (e.g. keep "
        "`time-stretching` over `timestretch`, `lfo-destination` over `lfo-destinations`).\n"
        "- Merge obvious singular/plural and hyphenation variants.\n"
        "- Merge near-synonyms only when they denote the SAME concept (e.g. "
        "`retrig` -> `retrigger`); do NOT over-merge distinct features.\n"
        "- DROP garbage like `trig-mode-one-one2-hold` (OCR artifact) and any slug that "
        "is a UI label rather than a concept.\n"
        "- Leave a good, distinct slug mapping to itself (omit it from the map entirely).\n\n"
        f"SLUGS (count, slug):\n{listing}\n\n"
        "Output ONLY a JSON object, no prose:\n"
        '{\n'
        '  "canonical": { "alias-slug": "canonical-slug", ... },   // only slugs that CHANGE\n'
        '  "drop": [ "noise-slug", ... ]                            // removed entirely\n'
        "}"
    )


def generate_map(census_path: str = str(CENSUS_PATH), model: str = "opus",
                 timeout: int = 600) -> dict:
    if "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:
        raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN is not set.")
    census = json.loads(pathlib.Path(census_path).read_text())
    prompt = build_reconcile_prompt(census)
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    cmd = ["claude", "-p", prompt,
           "--disallowedTools", "Read,WebFetch,WebSearch,Bash,Write,Edit,Glob,Grep",
           "--permission-mode", "default", "--model", model, "--output-format", "json"]
    last = None
    for attempt in range(3):
        proc = subprocess.run(cmd, cwd=str(_PROJECT_ROOT), env=env,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout)
        if proc.returncode == 0:
            break
        last = f"CLI exit {proc.returncode}: {proc.stderr[:200]!r}"
        print(f"reconcile attempt {attempt+1} failed ({last}); retrying", file=sys.stderr)
    else:
        raise RuntimeError(last)
    obj = json.loads(proc.stdout)
    mapping = _extract_json_object(obj["result"])
    mapping.setdefault("canonical", {})
    mapping.setdefault("drop", [])
    MAP_PATH.write_text(json.dumps(mapping, indent=2))
    print(f"wrote {MAP_PATH.name}: {len(mapping['canonical'])} merges, "
          f"{len(mapping['drop'])} drops", file=sys.stderr)
    return mapping


def apply_map(reference_dir: str = "knowledge/reference",
              glossary_path: str = "build/inputs/concept-glossary.yaml",
              map_path: str = str(MAP_PATH)) -> dict:
    mapping = json.loads(pathlib.Path(map_path).read_text())
    canon: dict[str, str] = mapping["canonical"]
    drop: set[str] = set(mapping["drop"])

    ref = pathlib.Path(reference_dir)
    surviving: set[str] = set()
    rewritten = 0
    for path in sorted(ref.glob("*.md")):
        post = frontmatter.load(path)
        old = post.get("concepts", [])
        new: list[str] = []
        for s in old:
            if s in drop:
                continue
            c = canon.get(s, s)
            if c not in new:
                new.append(c)
        if new != old:
            post["concepts"] = new
            path.write_text(frontmatter.dumps(post), encoding="utf-8")
            rewritten += 1
        surviving.update(new)

    # Refresh glossary to exactly the surviving canonical slugs.
    glossary = {
        slug: {"label": slug.replace("-", " ").title(), "aliases":
               sorted(a for a, c in canon.items() if c == slug)}
        for slug in sorted(surviving)
    }
    pathlib.Path(glossary_path).write_text(
        yaml.safe_dump(glossary, sort_keys=True, allow_unicode=True), encoding="utf-8")
    print(f"applied: {rewritten} chunks rewritten; "
          f"glossary now {len(surviving)} canonical slugs", file=sys.stderr)
    return {"rewritten": rewritten, "surviving": len(surviving)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if cmd == "generate":
        generate_map()
    elif cmd == "apply":
        apply_map()
    else:
        sys.exit(f"unknown command: {cmd!r} (use generate|apply)")
