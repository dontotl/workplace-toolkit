from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from presentation_studio import (  # noqa: E402
    audio_cache_key,
    build_timeline,
    clean_control_labels,
    compare_transcript,
    ensure_new_path,
    extract_existing_notes,
    generate_tts,
    inventory_pptx,
    _load_narration,
    _materialize_audio_records,
    prepare_workspace,
    render_video,
    select_backend,
    validate_narration_source,
    write_managed_notes,
)


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def _presentation_fixture(path: Path, payload: bytes = b"unchanged payload") -> None:
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="{P}" xmlns:r="{R}">
  <p:sldIdLst><p:sldId id="301" r:id="rId2"/><p:sldId id="302" r:id="rId1"/></p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000"/>
</p:presentation>'''
    presentation_rels = f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PR}">
  <Relationship Id="rId1" Type="{R}/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId2" Type="{R}/slide" Target="slides/slide2.xml"/>
</Relationships>'''
    slide_rels = lambda note: f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PR}"><Relationship Id="rId9" Type="{R}/notesSlide" Target="../notesSlides/{note}"/></Relationships>'''
    slide = lambda title: f'''<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'''
    notes = lambda prior, managed: f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr><p:txBody>
<a:p><a:r><a:t>{prior}</a:t></a:r></a:p>
<a:p><a:r><a:t>[[PRESENTATION-STUDIO:NARRATION:BEGIN]]</a:t></a:r></a:p>
<a:p><a:r><a:t>{managed}</a:t></a:r></a:p>
<a:p><a:r><a:t>[[PRESENTATION-STUDIO:NARRATION:END]]</a:t></a:r></a:p>
</p:txBody></p:sp></p:spTree></p:cSld></p:notes>'''
    members = {
        "[Content_Types].xml": "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>",
        "ppt/presentation.xml": presentation,
        "ppt/_rels/presentation.xml.rels": presentation_rels,
        "ppt/slides/slide1.xml": slide("First file"),
        "ppt/slides/slide2.xml": slide("Second file"),
        "ppt/slides/_rels/slide1.xml.rels": slide_rels("notesSlide1.xml"),
        "ppt/slides/_rels/slide2.xml.rels": slide_rels("notesSlide2.xml"),
        "ppt/notesSlides/notesSlide1.xml": notes("Prior one", "Old one"),
        "ppt/notesSlides/notesSlide2.xml": notes("Prior two", "Old two"),
        "docProps/custom.bin": payload,
    }
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def _presentation_without_notes_fixture(path: Path) -> None:
    _presentation_fixture(path)
    with ZipFile(path) as source:
        kept = {info.filename: source.read(info.filename) for info in source.infolist()
                if not info.filename.startswith("ppt/notesSlides/")}
    empty_rels = f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PR}"/>'''.encode()
    kept["ppt/slides/_rels/slide1.xml.rels"] = empty_rels
    kept["ppt/slides/_rels/slide2.xml.rels"] = empty_rels
    with ZipFile(path, "w", ZIP_DEFLATED) as output:
        for name, value in kept.items():
            output.writestr(name, value)


class PresentationStudioTests(unittest.TestCase):
    def test_cleaning_removes_only_control_labels(self):
        source = "[발표 스크립트 시작]\n  Keep  two spaces  \n발표 스크립트 끝"
        self.assertEqual(clean_control_labels(source), "  Keep  two spaces  ")
        self.assertEqual(clean_control_labels("발표 스크립트: 실제 문장"), "실제 문장")

    def test_inventory_and_extract_follow_physical_presentation_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            pptx = Path(temporary) / "deck.pptx"
            _presentation_fixture(pptx)
            inventory = inventory_pptx(pptx)
            self.assertEqual([row["slide_part"] for row in inventory["slides"]], [
                "ppt/slides/slide2.xml", "ppt/slides/slide1.xml"
            ])
            self.assertEqual([row["title"] for row in inventory["slides"]], ["Second file", "First file"])
            notes = extract_existing_notes(pptx)
            self.assertEqual([row["physical_index"] for row in notes], [1, 2])
            self.assertEqual(notes[0]["text"], "Prior two\nOld two")

    def test_managed_notes_preserve_prior_text_other_parts_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, first, second = root / "in.pptx", root / "out1.pptx", root / "out2.pptx"
            _presentation_fixture(source)
            write_managed_notes(source, first, {1: "Reviewed second", 2: "Reviewed first"})
            write_managed_notes(first, second, {1: "Reviewed second", 2: "Reviewed first"})
            with ZipFile(source) as before, ZipFile(first) as after, ZipFile(second) as repeated:
                note_parts = {"ppt/notesSlides/notesSlide1.xml", "ppt/notesSlides/notesSlide2.xml"}
                for name in before.namelist():
                    if name not in note_parts:
                        self.assertEqual(after.read(name), before.read(name), name)
                for name in note_parts:
                    xml = after.read(name)
                    self.assertIn(b"Prior", xml)
                    self.assertNotIn(b"Old one", xml)
                    self.assertNotIn(b"Old two", xml)
                    self.assertEqual(xml, repeated.read(name))

    def test_managed_notes_add_missing_notes_parts_without_changing_unrelated_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "in.pptx", root / "out.pptx"
            _presentation_without_notes_fixture(source)
            write_managed_notes(source, output, {1: "Reviewed second", 2: "Reviewed first"})
            notes = extract_existing_notes(output)
            self.assertEqual([row["text"] for row in notes], ["Reviewed second", "Reviewed first"])
            self.assertTrue(all(row["notes_part"] for row in notes))
            with ZipFile(source) as before, ZipFile(output) as after:
                for name in ("ppt/slides/slide1.xml", "ppt/slides/slide2.xml", "docProps/custom.bin"):
                    self.assertEqual(after.read(name), before.read(name), name)
                self.assertIn("ppt/notesMasters/notesMaster1.xml", after.namelist())
                self.assertIn("ppt/notesSlides/notesSlide1.xml", after.namelist())
                self.assertIn("ppt/notesSlides/notesSlide2.xml", after.namelist())

    def test_authoritative_notes_bind_source_hash_and_exact_extracted_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            approved, wrong = root / "approved.pptx", root / "wrong.pptx"
            _presentation_fixture(approved, b"approved")
            _presentation_fixture(wrong, b"wrong-same-slide-count")
            document = {
                "source_mode": "existing-notes-authoritative",
                "source_pptx_sha256": hashlib.sha256(approved.read_bytes()).hexdigest(),
                "slides": [
                    {"physical_index": 1, "text": "Prior two\nOld two"},
                    {"physical_index": 2, "text": "Prior one\nOld one"},
                ],
            }
            with self.assertRaisesRegex(ValueError, "source_pptx_sha256"):
                validate_narration_source(document, wrong)
            changed = json.loads(json.dumps(document))
            changed["slides"][0]["text"] = "Silently edited text"
            with self.assertRaisesRegex(ValueError, "authoritative"):
                validate_narration_source(changed, approved)
            rewrite = json.loads(json.dumps(changed))
            rewrite["source_mode"] = "approved-rewrite"
            validate_narration_source(rewrite, approved)

    def test_tts_requires_source_pptx_for_source_bound_narration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            narration = root / "narration.json"
            narration.write_text(json.dumps({
                "reviewed": True,
                "review_basis": "Existing notes approved as-is.",
                "source_mode": "existing-notes-authoritative",
                "source_pptx_sha256": "not-used-without-source",
                "slides": [{"physical_index": 1, "text": "Approved note."}],
            }))
            with self.assertRaisesRegex(ValueError, "--source-pptx"):
                generate_tts(narration, root / "missing-model", root / "audio", "mlx", "ffmpeg", "ffprobe")

    def test_audio_cache_key_invalidates_for_text_engine_or_model_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "model"
            model.mkdir()
            weights = model / "model.safetensors"
            weights.write_bytes(b"weights-a")
            base = audio_cache_key("hello", model, "mlx", "Sohee", "Korean")
            self.assertNotEqual(base, audio_cache_key("hello!", model, "mlx", "Sohee", "Korean"))
            self.assertNotEqual(base, audio_cache_key("hello", model, "cpu", "Sohee", "Korean"))
            weights.write_bytes(b"weights-b")
            self.assertNotEqual(base, audio_cache_key("hello", model, "mlx", "Sohee", "Korean"))

    def test_audio_cache_checkpoints_duplicate_keys_and_resumes_after_interruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            slides = [
                {"physical_index": 1, "title": "A", "text": "same"},
                {"physical_index": 2, "title": "B", "text": "same"},
            ]
            calls = []

            def synthesize(row):
                calls.append(row["physical_index"])
                return row["text"].encode()

            def encode(generated, destination):
                destination.write_bytes(b"verified-" + generated)
                return {"seconds": 1.0, "file_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}

            def verify(path, record):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["file_sha256"])
                return record["seconds"]

            records = _materialize_audio_records(slides, "model-digest", "mlx", output,
                                                 synthesize, encode, verify)
            self.assertEqual(calls, [1])
            self.assertEqual(records[0]["key"], records[1]["key"])
            checkpoint = json.loads((output / "audio-checkpoint.json").read_text())
            self.assertIn(records[0]["key"], checkpoint["records"])

            interrupted = output / "interrupted"
            interrupted.mkdir()
            distinct = [
                {"physical_index": 1, "title": "A", "text": "first"},
                {"physical_index": 2, "title": "B", "text": "second"},
            ]

            def crash_on_second(row):
                if row["physical_index"] == 2:
                    raise RuntimeError("synthetic interruption")
                return row["text"].encode()

            with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                _materialize_audio_records(distinct, "model-digest", "mlx", interrupted,
                                           crash_on_second, encode, verify)
            resume_calls = []

            def resume(row):
                resume_calls.append(row["physical_index"])
                return row["text"].encode()

            resumed = _materialize_audio_records(distinct, "model-digest", "mlx", interrupted,
                                                  resume, encode, verify)
            self.assertEqual(resume_calls, [2])
            self.assertEqual(len(resumed), 2)

    def test_timeline_uses_actual_audio_duration_without_speed_target(self):
        rows = [
            {"physical_index": 1, "title": "A", "text": "one", "audio_seconds": 1.25},
            {"physical_index": 2, "title": "B", "text": "two", "audio_seconds": 2.5},
        ]
        timeline = build_timeline(rows, lead_seconds=0.25, tail_seconds=0.5)
        self.assertEqual(timeline[0]["start_seconds"], 0.0)
        self.assertEqual(timeline[0]["duration_seconds"], 2.0)
        self.assertEqual(timeline[1]["start_seconds"], 2.0)
        self.assertEqual(timeline[1]["duration_seconds"], 3.25)

    def test_local_backend_selection_prefers_mlx_and_has_explicit_cpu_fallback(self):
        self.assertEqual(select_backend("auto", {"mlx": True, "cpu": True}), "mlx")
        self.assertEqual(select_backend("auto", {"mlx": False, "cpu": True}), "cpu")
        with self.assertRaisesRegex(RuntimeError, "mlx.*unavailable"):
            select_backend("mlx", {"mlx": False, "cpu": True})
        with self.assertRaisesRegex(RuntimeError, "No local TTS backend"):
            select_backend("auto", {"mlx": False, "cpu": False})

    def test_transcript_comparison_normalizes_format_but_flags_mismatch(self):
        exact = compare_transcript("안녕하세요, 로컬 점검입니다.", "안녕하세요 로컬 점검입니다")
        mismatch = compare_transcript("안녕하세요, 로컬 점검입니다.", "전혀 다른 문장")
        self.assertEqual(exact["ratio"], 1.0)
        self.assertGreater(exact["ratio"], mismatch["ratio"])
        self.assertTrue(mismatch["review_required"])

    def test_output_protection_rejects_existing_paths_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "movie.mp4"
            ensure_new_path(target)
            target.write_bytes(b"existing")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                ensure_new_path(target)
            link = root / "linked.mp4"
            link.symlink_to(target)
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                ensure_new_path(link)

    def test_prepare_keeps_extracted_notes_in_an_unreviewed_separate_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pptx, output = root / "deck.pptx", root / "prepared"
            _presentation_fixture(pptx)
            prepare_workspace(pptx, output)
            draft = json.loads((output / "narration-draft.json").read_text())
            existing = json.loads((output / "existing-notes.json").read_text())
            self.assertIs(draft["reviewed"], False)
            self.assertEqual(draft["slides"][0]["text"], existing["slides"][0]["text"])
            self.assertEqual(draft["slides"][0]["text"], "Prior two\nOld two")
            self.assertNotIn("suggested", draft["slides"][0])
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                prepare_workspace(pptx, output)

    def test_whole_deck_review_basis_approves_source_without_per_slide_clicks(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "narration.json"
            source.write_text(json.dumps({
                "reviewed": True,
                "review_basis": "User explicitly approved existing notes as-is in this session.",
                "slides": [{"physical_index": 1, "title": "A", "text": "Approved note.", "reviewed": False}]
            }))
            self.assertEqual(_load_narration(source)["slides"][0]["text"], "Approved note.")
            source.write_text(json.dumps({
                "reviewed": True,
                "slides": [{"physical_index": 1, "title": "A", "text": "Approved note."}]
            }))
            with self.assertRaisesRegex(ValueError, "review_basis"):
                _load_narration(source)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
    def test_local_video_writes_srt_chapters_and_passes_full_decode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "slide.ppm"
            image.write_text("P3\n2 2\n255\n255 255 255  0 0 0\n0 0 0  255 255 255\n")
            audio = root / "tone.flac"
            subprocess.run([
                shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4",
                "-ac", "1", "-c:a", "flac", str(audio)
            ], check=True)
            digest = hashlib.sha256(audio.read_bytes()).hexdigest()
            audio_manifest = root / "audio-manifest.json"
            audio_manifest.write_text(json.dumps({"schema": 1, "slides": [{
                "physical_index": 1, "title": "Synthetic", "text": "Public synthetic tone.",
                "path": audio.name, "file_sha256": digest, "audio_seconds": 0.4
            }]}))
            render_manifest = root / "render.json"
            render_manifest.write_text(json.dumps({"slides": [{"physical_index": 1, "image": image.name}]}))
            movie = root / "movie.mp4"
            render_video(audio_manifest, movie, shutil.which("ffmpeg"), shutil.which("ffprobe"),
                         render_manifest=render_manifest, width=320, height=180, fps=10,
                         lead_seconds=0.1, tail_seconds=0.1)
            self.assertTrue(movie.is_file())
            self.assertIn("Public synthetic tone.", movie.with_suffix(".srt").read_text())
            self.assertIn("[CHAPTER]", movie.with_suffix(".chapters.ffmetadata").read_text())
            validation = json.loads(movie.with_suffix(".validation.json").read_text())
            self.assertEqual(validation["full_decode"], "passed")
            self.assertEqual(validation["static_fallback_slides"], [1])
            self.assertEqual(validation["output"]["filename"], "movie.mp4")
            self.assertEqual(validation["output"]["sha256"], hashlib.sha256(movie.read_bytes()).hexdigest())
            self.assertNotIn(str(root), json.dumps(validation))
            movie.unlink()
            movie.with_suffix(".srt").unlink()
            movie.with_suffix(".chapters.ffmetadata").unlink()
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                render_video(audio_manifest, movie, shutil.which("ffmpeg"), shutil.which("ffprobe"),
                             render_manifest=render_manifest, width=320, height=180, fps=10,
                             lead_seconds=0.1, tail_seconds=0.1)


if __name__ == "__main__":
    unittest.main()
