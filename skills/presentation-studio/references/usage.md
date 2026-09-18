# Presentation Studio usage

Set the skill directory without assuming the caller's working directory:

```bash
SKILL_DIR=/path/to/presentation-studio
CLI="$SKILL_DIR/scripts/presentation_studio.py"
```

## Runtime requirements

All commands need Python 3.10+ and use only the standard library until their selected operation needs more:

- `prepare`, `existing-notes`, `notes`: no third-party Python package.
- `video`: existing local `ffmpeg` and `ffprobe` executables with H.264, AAC, FLAC, and mov_text support.
- `tts --backend mlx`: Apple Silicon/Metal, NumPy, MLX, and `mlx-audio` in the selected local Python.
- `tts --backend cpu`: NumPy, PyTorch, and `qwen-tts` in the selected local Python.
- `audit`: `faster-whisper` plus an existing local CTranslate2 model directory containing `model.bin`; execution is CPU/int8.
- TTS model: an already-present local Qwen3-TTS CustomVoice model directory containing `.safetensors` weights. The speaker/language are fixed to `Sohee`/`Korean`.

No command installs or downloads dependencies. A missing runtime fails explicitly. Offline Hugging Face/Transformers flags are set before model loading.

## Model-processing boundary

The media/TTS/ASR commands are local-only. Codex authoring is separate model processing, even when used from an approved Enterprise environment; do not describe it as offline. Confirm that the current Codex session is approved before asking it to read or author presentation content.

If policy says a document must remain local or forbids model processing, do not let Codex read, screenshot, paste, translate, summarize, or otherwise ingest it. An authorized local operator must prepare the story, narration, and review JSON. Codex may provide generic commands and consume only content-free local status such as exit codes, slide counts, durations, hashes, and pass/fail summaries.

## Prepare and review

```bash
python3 "$CLI" prepare --pptx deck.pptx --output prepared
python3 "$CLI" existing-notes --pptx deck.pptx --output existing-notes.json
```

`prepare` creates `inventory.json`, `existing-notes.json`, `story-template.md`, and `narration-draft.json`. The extraction follows `ppt/presentation.xml` physical order. It removes only recognized script/control labels; the remaining note text is not rewritten. Empty notes stay empty.

Existing notes are authoritative by default. If the user explicitly approves them as-is, keep the extracted text unchanged, set top-level `reviewed` to `true`, and write that source approval into `review_basis`. This whole-deck evidence replaces per-slide clicking; row-level `reviewed` fields are informational.

Keep `source_mode: existing-notes-authoritative` only when every narration string exactly matches cleaned notes from the PPTX identified by `source_pptx_sha256`. Empty notes or requested changes are stop conditions; ask the user. For explicitly requested authorship, change to `source_mode: approved-rewrite`, keep the original source hash, and obtain approval of the complete draft.

Only author or rewrite narration when the user explicitly asks in the current session. First complete the story template: global thesis, audience decision, chapter themes, transitions, and closing action. Mark slide roles such as `title`, `agenda`, `body`, and `closing`; plan approximately 45 minutes across body roles only. Then draft all slide text, obtain whole-deck approval, and record it in `review_basis`. The CLI never invents missing text, and final media timing always follows measured natural-speed audio rather than stretching speech to hit 45 minutes.

## Write managed speaker notes

```bash
python3 "$CLI" notes \
  --pptx deck.pptx \
  --narration prepared/narration-draft.json \
  --output deck-reviewed-notes.pptx
```

Both modes verify `source_pptx_sha256` against `--pptx`. Authoritative mode also compares every narration string with freshly extracted, control-cleaned notes, then publishes a byte-identical create-only copy. Approved-rewrite mode replaces only text between the `PRESENTATION-STUDIO:NARRATION` markers in each existing notes-body placeholder. Text outside that block is retained and unrelated ZIP members are copied byte-for-byte. If a slide has no notes part, the CLI adds a minimal notes master/slide, required relationships, and content-type entries without changing slide content. Re-running the rewrite with the same narration is idempotent.

## Render slides locally

PowerPoint: export all slides as PNG and name them `slide-1.png` ... `slide-N.png` (zero-padded names also work).

LibreOffice/Poppler example:

```bash
soffice --headless --convert-to pdf --outdir rendered deck-reviewed-notes.pptx
pdftoppm -png -r 150 rendered/deck-reviewed-notes.pdf rendered/slide
```

Rename/map files to physical indexes. Native PowerPoint rendering is preferred when fidelity matters.

Animations cannot be recovered from static PNGs. With only PNGs, the report deliberately records a static fallback. To preserve an already-rendered animation/video for a slide, provide a render manifest:

```json
{
  "slides": [
    {"physical_index": 1, "image": "rendered/slide-1.png"},
    {"physical_index": 2, "image": "rendered/slide-2.png", "media": "rendered/slide-2.mov"}
  ]
}
```

Explicit `media` is used as that slide's full-frame moving visual. It must be prepared locally beforehand. A background `image` remains required for inventory/validation.

Relative `image` and `media` values resolve from the render manifest's directory, not the caller's working directory.

## Local Sohee TTS

MLX/Metal, preferred:

```bash
PYTHONPATH=/path/to/local/mlx-packages \
python3 "$CLI" tts \
  --python /path/to/tts-python \
  --backend mlx \
  --model /path/to/local/qwen3-tts-model \
  --narration prepared/narration-draft.json \
  --source-pptx deck.pptx \
  --output audio-cache \
  --ffmpeg /path/to/ffmpeg \
  --ffprobe /path/to/ffprobe
```

CPU fallback, selected explicitly:

```bash
python3 "$CLI" tts \
  --python /path/to/cpu-tts-python \
  --backend cpu \
  --model /path/to/local/qwen3-tts-model \
  --narration prepared/narration-draft.json \
  --source-pptx deck.pptx \
  --output audio-cache
```

`--source-pptx` is mandatory when the narration has either source mode; TTS repeats the same source-hash and authoritative-text checks before inspecting its backend/model. Synthetic narration with no deck source mode does not need this option.

`--backend auto` prefers usable MLX/Metal and otherwise selects the local CPU package. Explicit `mlx` never silently falls back. Audio is cached directly as verified FLAC; no retained WAV intermediates. Cache identity includes exact text, backend, speaker, language, and a content hash of the local model files. `audio-checkpoint.json` is atomically updated after each verified unique key, so duplicate slide text reuses one FLAC and an interrupted run resumes verified prior keys.

Some Qwen tokenizer versions emit a known Mistral-regex compatibility warning during local model load. Treat it as a third-party runtime warning: record it, listen to/audit the result, and do not mutate a shared model or environment during this workflow.

New audio manifests store FLAC paths relative to the manifest directory. Absolute paths in older manifests remain supported.

## Local transcript audit

```bash
python3 "$CLI" audit \
  --python /path/to/asr-python \
  --audio-manifest audio-cache/audio-manifest.json \
  --asr-model /path/to/local/faster-whisper-model \
  --output audio-cache/asr-audit.json
```

The command uses faster-whisper with `device=cpu`, `compute_type=int8`, Korean transcription, and `local_files_only=True`. The local report contains expected text, recognized text, similarity ratio, and review flags. Standard output contains metadata counts/provider only. Missing packages/models fail explicitly; no service or download fallback exists. Treat every `review_required` entry as a human-listening gate before video publication. `--threshold` defaults to `0.82`.

## MP4, SRT, and chapters

From conventionally named PNGs:

```bash
python3 "$CLI" video \
  --audio-manifest audio-cache/audio-manifest.json \
  --slides-dir rendered \
  --output presentation.mp4
```

Or replace `--slides-dir rendered` with `--render-manifest render.json`. `--width`, `--height`, `--fps`, `--lead-seconds`, `--tail-seconds`, `--ffmpeg`, and `--ffprobe` are configurable.

Outputs are `presentation.mp4`, `presentation.srt`, `presentation.chapters.ffmetadata`, and `presentation.validation.json`. Timing uses probed FLAC durations at `tempo: 1.0`; there is no promised target length or forced speech speed. The final MP4 must contain video, audio, and subtitle streams and pass a complete ffmpeg decode. Validation is probed from the published file and records only final basenames/references plus output bytes and SHA-256—never temporary absolute paths.
