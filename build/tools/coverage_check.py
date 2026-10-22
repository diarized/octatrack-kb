"""Phase G acceptance: coverage-gap check against the live retriever.

Runs a battery of representative Octatrack queries (spanning the 8 usage modes,
high-value concepts, and spine workflows) and flags any where retrieval is weak:
top hit below a score floor, or no expected topic token in the top-k titles/ids.
Pure-Python judgement (no model spend) — the report is for human triage.
"""
from __future__ import annotations
import sys
from octatrack_kb.retrieval import Retriever

SCORE_FLOOR = 0.45  # top hit below this = suspect coverage

# (query, expected token that SHOULD appear in a top-k id or title, lowercased)
BATTERY: list[tuple[str, str]] = [
    # --- usage-mode spanning tasks ---
    ("how do I record external audio into a sampler track", "record"),
    ("slice a drum break and trigger slices from steps", "slice"),
    ("set up a live looper with pickup machines", "pickup"),
    ("sequence external synth over MIDI", "midi"),
    ("play samples chromatically from a MIDI keyboard", "chromatic"),
    ("use the octatrack as an effects processor for external audio", "thru"),
    ("route a track to the cue outputs", "cue"),
    ("configure track 8 as a master track", "master"),
    # --- core concepts ---
    ("what is a parameter lock", "lock"),
    ("how do scenes and the crossfader work together", "scene"),
    ("difference between flex and static machines", "machine"),
    ("what is a part and how does it relate to a pattern", "part"),
    ("conditional trigs and fill mode", "conditional"),
    ("assign an LFO to modulate a parameter", "lfo"),
    ("trig modes chromatic slots slices", "trig-mode"),
    ("recording buffer and the audio pool", "buffer"),
    # --- workflow / compare ---
    ("different ways to vary a pattern live", "part"),
    ("build a song with the arranger", "arrang"),
    ("set pattern length and scale per track", "scale"),
    ("micro timing and swing", "timing"),
    # --- deeper / edge ---
    ("MIDI sync clock and transport with external gear", "sync"),
    ("noise gate and delay compensation on inputs", "gate"),
    ("neighbor machines for extended fx chains", "neighbor"),
    ("crossfader scene morphing for performance", "crossfader"),
    ("one shot trigs vs trigless trigs", "trig"),
]


def run(db="server/kb.db", ref="knowledge/reference", concepts="knowledge/concepts.yaml", guides="knowledge/guides"):
    r = Retriever(db, ref, concepts, guides_dir=guides)
    weak, missing, ok = [], [], 0
    print(f"{'top':>5}  {'hit?':4}  query")
    for q, expect in BATTERY:
        hits = r.search(q, k=5)
        top = hits[0].score if hits else 0.0
        blob = " ".join(f"{h.id} {h.title}".lower() for h in hits)
        found = expect in blob
        flag = "ok"
        if not found:
            flag = "MISS"; missing.append((q, expect, [h.id for h in hits]))
        elif top < SCORE_FLOOR:
            flag = "weak"; weak.append((q, top, [h.id for h in hits[:3]]))
        else:
            ok += 1
        print(f"{top:5.2f}  {flag:4}  {q}")

    print(f"\n=== {ok}/{len(BATTERY)} clean | {len(weak)} weak | {len(missing)} miss ===")
    if weak:
        print("\nWEAK (top score < floor):")
        for q, t, ids in weak:
            print(f"  [{t:.2f}] {q}\n        top3: {ids}")
    if missing:
        print("\nMISS (expected topic not in top-5):")
        for q, exp, ids in missing:
            print(f"  want '{exp}' :: {q}\n        got: {ids}")
    return len(weak), len(missing)


if __name__ == "__main__":
    w, m = run()
    sys.exit(0)
