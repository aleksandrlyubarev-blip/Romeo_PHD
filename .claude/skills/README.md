# `.claude/skills/` — video skills

Project-scoped Claude Code skills for working with video correctly. Each
skill lives in its own folder with a `SKILL.md` describing when Claude
should invoke it and the exact FFmpeg/Python commands it should produce.

| Skill | When to invoke |
|---|---|
| `video-probe` | Before any other video work — codec, FPS, VFR, HDR, rotation, audio streams |
| `video-extract-frames` | Per-frame AI processing or per-frame inspection (PNG/PNG-16, pipe-mode) |
| `video-restore-faces` | Full RFV pipeline: probe → extract → restore → encode → mux |
| `video-mux` | Combine a re-encoded video back with original audio + container metadata |
| `video-encode` | Re-encode preserving colour, bit depth, HDR, rotation, audio bitstream |

All skills route through the Python helpers in `scripts/rfv_pipeline/`
(see that package's README for the full design rationale: why every
flag, what naive pipelines get wrong, how to handle VFR/HDR/ProRes/
rotated phone clips).

## Skill anatomy

Each `SKILL.md` has YAML frontmatter (`name`, `description`) followed by
the body that Claude reads after the harness loads the skill. The
description's first sentence is the trigger — it tells the harness when
to surface the skill to Claude based on the user's prompt.

## Adding a new video skill

1. Create `.claude/skills/<name>/SKILL.md`
2. Frontmatter: `name: <name>` and a description that includes (a) what
   the skill does, (b) when to use it (concrete user-phrasing examples),
   and (c) when NOT to use it.
3. Body: decision tree, canonical commands, common pitfalls, references
   to the matching `scripts/rfv_pipeline/` helpers.
