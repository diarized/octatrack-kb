# Octatrack KB — Data Schemas Reference

## 1. Chunk Frontmatter Schema

Each chunk is a Markdown file with a YAML frontmatter block. The chunk's
canonical identity is its `id` field — NOT its filename. This means a file can
be renamed on disk without breaking any concept-graph links.

### Required keys

| Key | Type | Meaning |
|-----|------|---------|
| `id` | `str` (kebab-case) | Stable, unique chunk identifier. Used as the primary key in the vector store and concept graph. |
| `title` | `str` | Human-readable section title (e.g. `"Scene"`). |
| `chapter` | `int` | Manual chapter number the chunk belongs to. |
| `source_pages` | `list[int]` | Page numbers in the source PDF that the chunk covers (inclusive). |
| `concepts` | `list[str]` | Concept slugs that this chunk introduces or significantly explains. Slugs must exist in `concepts.yaml`. |

### Optional keys

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `section` | `str` | `null` | Sub-section identifier (e.g. `"8.2"`). Useful for deep-linking and display. |
| `usage_modes` | `list[str]` | `[]` | Subset of the controlled vocabulary (see §3). Tags the chunk with the Octatrack operating contexts it is relevant to. |
| `related` | `list[str]` | `[]` | Chunk `id`s that are semantically related (see-also). Concept-to-concept relationships live in `concepts.yaml`, not here. |

### Example frontmatter

```yaml
---
id: scene
title: Scene
chapter: 8
section: "8.2"
source_pages: [157, 165]
usage_modes: [live-looper]
concepts: [scene, crossfader, parameter-lock]
related: [crossfader]
---
```

---

## 2. concepts.yaml Schema

`concepts.yaml` holds one entry per concept slug. Concept-to-concept
relationships live here; chunk-to-chunk see-also links live in chunk
frontmatter `related`.

```yaml
# concepts.yaml — one entry per concept slug
scene:
  label: Scene                       # display name
  definition_chunk: parts-and-scenes # chunk id where the concept is defined
  mentioned_in: [parts-and-scenes, patterns-basics]  # chunk ids
  related: [crossfader, parameter-lock, part]         # other concept slugs
  usage_modes: [live-looper]                          # subset of USAGE_MODES
```

### Field reference

| Field | Type | Meaning |
|-------|------|---------|
| `label` | `str` | Display name for the concept (title case). |
| `definition_chunk` | `str` | `id` of the chunk that provides the authoritative definition. |
| `mentioned_in` | `list[str]` | All chunk `id`s where this concept appears. Includes `definition_chunk`. |
| `related` | `list[str]` | Other concept slugs that are semantically related to this one. |
| `usage_modes` | `list[str]` | Subset of the controlled vocabulary (see §3) indicating relevant operating contexts. |

---

## 3. usage_modes Controlled Vocabulary

The following slugs are the only valid values for `usage_modes` in both chunk
frontmatter and `concepts.yaml`. The set is defined in
`octatrack_kb/schema.py:USAGE_MODES` and must be kept in sync with this doc.

| Slug | Description |
|------|-------------|
| `sampler` | Functionality related to recording and playing back audio samples. |
| `sequencer` | Step-sequencer and pattern-based playback features. |
| `groovebox` | Use as an integrated groove/beat production instrument. |
| `live-looper` | Real-time loop recording, scene morphing, and performance features. |
| `midi-sequencer` | MIDI track sequencing and note/CC output. |
| `midi-controller` | Controlling external gear via MIDI. |
| `fx-processor` | Using the Octatrack as a send/insert effects processor. |
| `mixer` | Mixer-specific features: levels, cue, panning, crossfader. |

Any value not in this list will be flagged as an error by `validate_chunk_meta`.
