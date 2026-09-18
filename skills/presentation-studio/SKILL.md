---
name: presentation-studio
description: Use when preparing presentation narration, preserving or extracting PowerPoint speaker notes, generating local Korean Qwen3-TTS audio, or producing a narrated MP4 from rendered slides.
---

# Presentation Studio

Use the bundled CLI for a local, review-gated presentation-to-media workflow. It is standalone: resolve paths relative to this `SKILL.md`, never to a checkout root.

## Safety contract

- Use only local PPTX, model, Python, image, media, ffmpeg, and ffprobe paths supplied by the user.
- Never download a model or dependency during a run, call a proxy/API, or fall back to a cloud service.
- “Local media” describes the CLI backends, not Codex itself. Authoring in a currently approved Enterprise/Codex session is model processing, not offline processing. If a deck is classified local-only or prohibited from model processing, do not read, screenshot, paste, or upload its content into Codex. Have an authorized person prepare the local story/narration/review files, run the CLI locally, and share only content-free status, counts, and hashes.
- Existing speaker notes are authoritative unless the user explicitly requests rewriting. `prepare` copies them into a separate unreviewed draft and never invents missing narration.
- Do not run `notes` or `tts` until a human explicitly approves the whole-deck source or authored draft. Record that approval in top-level `reviewed: true` and `review_basis`; separate per-slide clicks are not required.
- Outputs are create-only. Choose a new path instead of overwriting one.

## Workflow

1. Run `prepare` to inventory physical slide order and create story/narration review files.
2. Choose a source mode. If the user approves existing notes as-is, retain their text exactly and record that whole-deck approval. If the user explicitly requests new/revised narration, author it in the approved session: establish a global thesis, audience decision, chapter themes, transitions, and closing action before slide prose. Plan 45 minutes for body slides, excluding title and agenda; this is a planning target, never permission to force audio speed.
3. Record the approved source/draft in `review_basis` and set top-level `reviewed: true`. In `existing-notes-authoritative` mode, missing text is a stop condition: ask for direction and never fill or edit it. Only `approved-rewrite`, after an explicit rewrite request, may contain authored replacements. One explicit whole-deck approval is sufficient.
4. Run `notes` with the exact source PPTX. Authoritative mode verifies its hash/text and publishes an unchanged copy; approved-rewrite mode writes a managed narration block while retaining prior note text and unrelated PPTX parts.
5. Render slide PNGs natively in PowerPoint, or via LibreOffice/PDF tools.
6. Run `tts` with an existing local Qwen3-TTS model and suitable local Python. Pass `--source-pptx` for either source-bound mode so TTS repeats the hash/text validation. MLX/Metal is preferred; CPU is selectable.
7. Run `audit` with an existing local faster-whisper model; review every flagged transcript comparison.
8. Run `video` from local PNGs or a render manifest. Duration follows measured audio at natural speed. Read `.validation.json` for static fallbacks and decode/probe evidence.

Read [references/usage.md](references/usage.md) before execution for schemas, dependencies, commands, rendering options, and limitations.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
