"""Author spine workflow micro-guides with a source-accuracy gate (Task 15).

Per guide, a three-call pipeline:
  AUTHOR  (opus)   write guides/<id>.md grounded ONLY in the supplied reference
                   chunks, citing the chunk ids it used in `sources:` frontmatter.
  REVIEW  (sonnet) check every claim against those chunks; return unsupported ones.
  REVISE  (opus)   if the reviewer flagged anything, rewrite to remove/fix it.

Quality mechanism: micro-guides synthesize across sections and are the highest
hallucination risk, so nothing ships unless the reviewer's claims are addressed.
Source chunks are chosen by concept overlap (via concepts.yaml). Resumable: an
existing guides/<id>.md is skipped. Auth/billing identical to build/tag.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import frontmatter
import yaml

from build.tag import _extract_json_object

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
AUTHOR_MODEL = "opus"
REVIEW_MODEL = "sonnet"

MAX_CHUNKS = 6
PER_CHUNK_CAP = 5000
TOTAL_CAP = 28_000


def gather_sources(guide: dict, concepts_index: dict, by_id: dict) -> list[tuple[str, str]]:
    """Pick the most relevant reference chunks for a guide by concept overlap."""
    score: dict[str, int] = {}
    for concept in guide["concepts"]:
        entry = concepts_index.get(concept, {})
        for cid in entry.get("mentioned_in", []):
            score[cid] = score.get(cid, 0) + 1
    # A chunk whose id IS a guide concept is a definition: boost it.
    for concept in guide["concepts"]:
        if concept in by_id:
            score[concept] = score.get(concept, 0) + 5

    ranked = sorted(score, key=lambda cid: (-score[cid], cid))[:MAX_CHUNKS]
    out: list[tuple[str, str]] = []
    total = 0
    for cid in ranked:
        body = by_id[cid].content[:PER_CHUNK_CAP]
        if total + len(body) > TOTAL_CAP:
            break
        out.append((cid, body))
        total += len(body)
    return out


def _sources_block(sources: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"### SOURCE chunk id: {cid}\n{body}" for cid, body in sources)


def build_author_prompt(guide: dict, sources: list[tuple[str, str]]) -> str:
    ids = [cid for cid, _ in sources]
    return (
        "You are writing one task-oriented micro-guide for an Elektron Octatrack "
        "knowledge base, for AI retrieval. Ground EVERY statement in the source "
        "chunks below — do NOT add facts from outside them. If the sources lack a "
        "detail, omit it rather than invent it.\n\n"
        f"Guide id: {guide['id']}\n"
        f"Task: {guide['description']}\n"
        f"Usage modes: {guide['modes']}\n"
        f"Concepts in scope: {guide['concepts']}\n\n"
        f"Available SOURCE chunk ids (cite the ones you actually use): {ids}\n\n"
        f"{_sources_block(sources)}\n\n"
        "--- END SOURCES ---\n\n"
        "Write the guide as a single Markdown file. Output ONLY the file content, "
        "starting immediately with a YAML frontmatter block (no prose before it):\n"
        "---\n"
        f"id: {guide['id']}\n"
        "title: <concise imperative title>\n"
        f"modes: {guide['modes']}\n"
        f"concepts: {guide['concepts']}\n"
        "sources: [<subset of the source ids you actually drew from>]\n"
        "---\n"
        "Then the body: a short intro, a numbered step-by-step of the core workflow, "
        "and a 'Variations & subtleties' section covering the different ways / gotchas "
        "the sources mention. Keep it tight and factual."
    )


def build_review_prompt(guide_md: str, sources: list[tuple[str, str]]) -> str:
    return (
        "You are a source-accuracy reviewer for an Octatrack knowledge base. Below is "
        "a drafted micro-guide and the ONLY source chunks it is allowed to rely on. "
        "Flag every statement in the guide that is NOT supported by the sources "
        "(hallucinations, invented parameter names, wrong button combos, etc.).\n\n"
        f"--- GUIDE ---\n{guide_md}\n--- END GUIDE ---\n\n"
        f"--- SOURCES ---\n{_sources_block(sources)}\n--- END SOURCES ---\n\n"
        "Output ONLY JSON:\n"
        '{ "verdict": "ok" | "revise",\n'
        '  "issues": [ {"claim": "<quoted/paraphrased unsupported claim>", '
        '"problem": "<why it is unsupported>"} ] }\n'
        "verdict is 'ok' ONLY if issues is empty."
    )


def build_revise_prompt(guide: dict, sources: list[tuple[str, str]],
                        guide_md: str, issues: list[dict]) -> str:
    issue_lines = "\n".join(f"- claim: {i.get('claim')!r} — problem: {i.get('problem')!r}"
                            for i in issues)
    return (
        "Revise this Octatrack micro-guide to fix the reviewer's source-accuracy "
        "issues. Remove or correct each flagged claim using ONLY the sources. Keep the "
        "same frontmatter shape. Output ONLY the corrected Markdown file content.\n\n"
        f"--- REVIEWER ISSUES ---\n{issue_lines}\n\n"
        f"--- CURRENT GUIDE ---\n{guide_md}\n--- END GUIDE ---\n\n"
        f"--- SOURCES ---\n{_sources_block(sources)}\n--- END SOURCES ---"
    )


def _extract_guide_md(raw: str) -> str:
    """Pull the guide file out of a model reply.

    Tolerates a prose preamble and/or a ```markdown fence around the guide (a
    failure mode seen on the opus revise step), then trims to the first YAML
    frontmatter delimiter so frontmatter.loads sees `---` on line 1.
    """
    t = raw.strip()
    if "```" in t:
        segments = t.split("```")
        for seg in segments[1::2]:  # contents inside fences
            if seg.startswith("markdown"):
                seg = seg[len("markdown"):]
            seg = seg.lstrip("\n")
            if seg.lstrip().startswith("---"):
                t = seg
                break
    idx = t.find("---")
    if idx != -1:
        t = t[idx:]
    return t.strip()


def _run_text(prompt: str, model: str, env: dict, timeout: int, attempts: int = 2) -> str:
    last = None
    for _ in range(attempts):
        proc = subprocess.run(
            ["claude", "-p", prompt, "--disallowedTools",
             "Read,WebFetch,WebSearch,Bash,Write,Edit,Glob,Grep",
             "--permission-mode", "default", "--model", model, "--output-format", "json"],
            cwd=str(_PROJECT_ROOT), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            last = RuntimeError(f"CLI exit {proc.returncode}: {proc.stderr[:200]!r}")
            continue
        obj = json.loads(proc.stdout)
        if obj.get("is_error"):
            last = ValueError(f"is_error: {obj.get('result')!r}")
            continue
        return obj["result"]
    raise last  # type: ignore[misc]


def author_guide(guide: dict, sources: list[tuple[str, str]], valid_ids: set[str],
                 env: dict, timeout: int) -> str:
    md = _extract_guide_md(_run_text(build_author_prompt(guide, sources),
                                    AUTHOR_MODEL, env, timeout))
    review_raw = _run_text(build_review_prompt(md, sources), REVIEW_MODEL, env, timeout)
    review = _extract_json_object(review_raw)
    issues = review.get("issues", []) if review.get("verdict") != "ok" else []
    if issues:
        md = _extract_guide_md(_run_text(build_revise_prompt(guide, sources, md, issues),
                                        AUTHOR_MODEL, env, timeout))
    # Sanitize sources frontmatter to valid reference ids.
    post = frontmatter.loads(md)
    post["sources"] = [s for s in post.get("sources", []) if s in valid_ids]
    return frontmatter.dumps(post), len(issues)


def guides_all(spine_path: str = "build/inputs/spine-guides.yaml",
               concepts_path: str = "knowledge/concepts.yaml",
               reference_dir: str = "knowledge/reference",
               out_dir: str = "knowledge/guides", timeout: int = 600) -> None:
    if "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:
        raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN is not set.")
    guides = yaml.safe_load(pathlib.Path(spine_path).read_text())
    concepts_index = yaml.safe_load(pathlib.Path(concepts_path).read_text())
    by_id = {p.stem if (m := frontmatter.load(p)).get("id") is None else m["id"]: m
             for p in sorted(pathlib.Path(reference_dir).glob("*.md"))}
    valid_ids = set(by_id)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)

    done = skipped = revised = failed = 0
    for guide in guides:
        dest = out / f"{guide['id']}.md"
        if dest.exists():
            skipped += 1
            continue
        sources = gather_sources(guide, concepts_index, by_id)
        if not sources:
            print(f"{guide['id']}: NO sources — skipping", file=sys.stderr)
            failed += 1
            continue
        try:
            md, n_issues = author_guide(guide, sources, valid_ids, env, timeout)
        except (RuntimeError, ValueError, json.JSONDecodeError, KeyError,
                subprocess.TimeoutExpired) as exc:
            print(f"{guide['id']}: FAIL — {exc}", file=sys.stderr)
            failed += 1
            continue
        dest.write_text(md, encoding="utf-8")
        revised += 1 if n_issues else 0
        print(f"{guide['id']}: wrote ({len(sources)} sources, "
              f"{n_issues} issues fixed)", file=sys.stderr)
        done += 1

    print(f"\nGuides complete: {done} done ({revised} revised), "
          f"{skipped} skipped, {failed} failed.", file=sys.stderr)


if __name__ == "__main__":
    guides_all()
