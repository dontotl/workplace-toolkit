#!/usr/bin/env python3
"""Local-only presentation narration preparation, notes, TTS, and video CLI."""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZipFile


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"p": P, "a": A, "r": R}
RID = f"{{{R}}}id"
BEGIN = "[[PRESENTATION-STUDIO:NARRATION:BEGIN]]"
END = "[[PRESENTATION-STUDIO:NARRATION:END]]"
KOREAN_LABEL = r"(?:발표\s*스크립트(?:\s*(?:시작|끝|종료))?|스크립트\s*(?:시작|끝|종료))"
MANAGED_LABEL = r"\[\[PRESENTATION-STUDIO:NARRATION:(?:BEGIN|END)\]\]"
WRAPPED_LABEL = rf"[\[【<]\s*{KOREAN_LABEL}\s*[\]】>]"

ET.register_namespace("p", P)
ET.register_namespace("a", A)
ET.register_namespace("r", R)


def ensure_new_path(path: Path | str) -> Path:
    """Reject any existing destination, including a broken or valid symlink."""
    result = Path(path)
    if result.exists() or result.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing path: {result}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def clean_control_labels(text: str) -> str:
    """Remove recognized control labels while leaving narration characters untouched."""
    kept: list[str] = []
    for original in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = original.strip()
        if re.fullmatch(rf"(?:{WRAPPED_LABEL}|{KOREAN_LABEL}|{MANAGED_LABEL})\s*[:：]?", stripped):
            continue
        replaced = re.sub(rf"^\s*(?:{WRAPPED_LABEL}|{KOREAN_LABEL})\s*[:：]\s*", "", original, count=1)
        kept.append(replaced)
    while kept and kept[0] == "":
        kept.pop(0)
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept)


def _rels(archive: ZipFile, part: str) -> dict[str, dict[str, Any]]:
    rel_name = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    try:
        root = ET.fromstring(archive.read(rel_name))
    except KeyError:
        return {}
    return {
        node.attrib["Id"]: {
            "target": posixpath.normpath(posixpath.join(posixpath.dirname(part), node.attrib["Target"])),
            "type": node.attrib.get("Type", "").rsplit("/", 1)[-1],
            "external": node.attrib.get("TargetMode") == "External",
        }
        for node in root
    }


def _ordered_slides(archive: ZipFile) -> list[dict[str, Any]]:
    root = ET.fromstring(archive.read("ppt/presentation.xml"))
    relations = _rels(archive, "ppt/presentation.xml")
    rows: list[dict[str, Any]] = []
    for index, node in enumerate(root.findall("p:sldIdLst/p:sldId", NS), 1):
        relation = relations.get(node.attrib[RID])
        if not relation or relation["external"] or relation["type"] != "slide":
            raise ValueError(f"invalid slide relationship at physical slide {index}")
        rows.append({"physical_index": index, "slide_part": relation["target"]})
    if not rows:
        raise ValueError("presentation has no physical slides")
    return rows


def _shape_text(shape: ET.Element) -> str:
    paragraphs = []
    for paragraph in shape.findall(".//a:p", NS):
        paragraphs.append("".join(node.text or "" for node in paragraph.findall(".//a:t", NS)))
    return "\n".join(paragraphs)


def _title(archive: ZipFile, slide_part: str) -> str:
    root = ET.fromstring(archive.read(slide_part))
    for shape in root.findall(".//p:sp", NS):
        placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if placeholder is not None and placeholder.attrib.get("type") in {"title", "ctrTitle"}:
            return _shape_text(shape).strip()
    return ""


def _notes_part(archive: ZipFile, slide_part: str) -> str | None:
    matches = [value["target"] for value in _rels(archive, slide_part).values()
               if not value["external"] and value["type"] == "notesSlide"]
    if len(matches) > 1:
        raise ValueError(f"multiple notes parts on {slide_part}")
    return matches[0] if matches else None


def _notes_body(root: ET.Element) -> ET.Element | None:
    for shape in root.findall(".//p:sp", NS):
        placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if placeholder is not None and placeholder.attrib.get("type") == "body":
            return shape.find("p:txBody", NS)
    return None


def inventory_pptx(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
        size = root.find("p:sldSz", NS)
        slides = []
        for row in _ordered_slides(archive):
            notes_part = _notes_part(archive, row["slide_part"])
            slides.append({**row, "title": _title(archive, row["slide_part"]),
                           "notes_part": notes_part, "has_notes": notes_part is not None})
    return {
        "schema": 1,
        "source": str(path),
        "source_sha256": _sha256(path),
        "slide_count": len(slides),
        "width_emu": int(size.attrib["cx"]) if size is not None else None,
        "height_emu": int(size.attrib["cy"]) if size is not None else None,
        "slides": slides,
    }


def extract_existing_notes(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []
    with ZipFile(path) as archive:
        for slide in _ordered_slides(archive):
            notes_part = _notes_part(archive, slide["slide_part"])
            text = ""
            if notes_part:
                root = ET.fromstring(archive.read(notes_part))
                body = _notes_body(root)
                if body is not None:
                    text = clean_control_labels(_shape_text(body))
            rows.append({**slide, "title": _title(archive, slide["slide_part"]),
                         "notes_part": notes_part, "text": text})
    return rows


def _paragraph(text: str) -> ET.Element:
    paragraph = ET.Element(f"{{{A}}}p")
    run = ET.SubElement(paragraph, f"{{{A}}}r")
    value = ET.SubElement(run, f"{{{A}}}t")
    if text.startswith(" ") or text.endswith(" "):
        value.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    value.text = text
    return paragraph


def _replace_managed_block(xml: bytes, narration: str) -> bytes:
    root = ET.fromstring(xml)
    body = _notes_body(root)
    if body is None:
        raise ValueError("notes part has no body placeholder; repair it in PowerPoint or LibreOffice first")
    paragraphs = list(body.findall("a:p", NS))
    values = ["".join(node.text or "" for node in p.findall(".//a:t", NS)) for p in paragraphs]
    begins = [i for i, value in enumerate(values) if value == BEGIN]
    ends = [i for i, value in enumerate(values) if value == END]
    if begins or ends:
        if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
            raise ValueError("malformed presentation-studio managed notes block")
        for paragraph in paragraphs[begins[0]:ends[0] + 1]:
            body.remove(paragraph)
    for line in [BEGIN, *narration.replace("\r\n", "\n").replace("\r", "\n").split("\n"), END]:
        body.append(_paragraph(line))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _next_rid(root: ET.Element) -> str:
    used = {node.attrib.get("Id", "") for node in root}
    number = 1
    while f"rId{number}" in used:
        number += 1
    return f"rId{number}"


def _add_override(root: ET.Element, part: str, content_type: str) -> None:
    part_name = "/" + part
    for node in root:
        if node.attrib.get("PartName") == part_name:
            if node.attrib.get("ContentType") != content_type:
                raise ValueError(f"conflicting content type for {part}")
            return
    ET.SubElement(root, f"{{{CT}}}Override", PartName=part_name, ContentType=content_type)


def _new_notes_slide(narration: str) -> bytes:
    root = ET.Element(f"{{{P}}}notes")
    common = ET.SubElement(root, f"{{{P}}}cSld")
    tree = ET.SubElement(common, f"{{{P}}}spTree")
    nonvisual = ET.SubElement(tree, f"{{{P}}}nvGrpSpPr")
    ET.SubElement(nonvisual, f"{{{P}}}cNvPr", id="1", name="")
    ET.SubElement(nonvisual, f"{{{P}}}cNvGrpSpPr")
    ET.SubElement(nonvisual, f"{{{P}}}nvPr")
    group = ET.SubElement(tree, f"{{{P}}}grpSpPr")
    transform = ET.SubElement(group, f"{{{A}}}xfrm")
    for tag in ("off", "ext", "chOff", "chExt"):
        attrs = {"x": "0", "y": "0"} if "Off" in tag or tag == "off" else {"cx": "0", "cy": "0"}
        ET.SubElement(transform, f"{{{A}}}{tag}", **attrs)
    shape = ET.SubElement(tree, f"{{{P}}}sp")
    nv_shape = ET.SubElement(shape, f"{{{P}}}nvSpPr")
    ET.SubElement(nv_shape, f"{{{P}}}cNvPr", id="2", name="Notes Placeholder 1")
    ET.SubElement(nv_shape, f"{{{P}}}cNvSpPr")
    nv_properties = ET.SubElement(nv_shape, f"{{{P}}}nvPr")
    ET.SubElement(nv_properties, f"{{{P}}}ph", type="body", idx="1")
    ET.SubElement(shape, f"{{{P}}}spPr")
    body = ET.SubElement(shape, f"{{{P}}}txBody")
    ET.SubElement(body, f"{{{A}}}bodyPr")
    ET.SubElement(body, f"{{{A}}}lstStyle")
    for line in [BEGIN, *narration.replace("\r\n", "\n").replace("\r", "\n").split("\n"), END]:
        body.append(_paragraph(line))
    override = ET.SubElement(root, f"{{{P}}}clrMapOvr")
    ET.SubElement(override, f"{{{A}}}masterClrMapping")
    return _xml(root)


def _new_notes_master() -> bytes:
    root = ET.Element(f"{{{P}}}notesMaster")
    common = ET.SubElement(root, f"{{{P}}}cSld")
    tree = ET.SubElement(common, f"{{{P}}}spTree")
    nonvisual = ET.SubElement(tree, f"{{{P}}}nvGrpSpPr")
    ET.SubElement(nonvisual, f"{{{P}}}cNvPr", id="1", name="")
    ET.SubElement(nonvisual, f"{{{P}}}cNvGrpSpPr")
    ET.SubElement(nonvisual, f"{{{P}}}nvPr")
    group = ET.SubElement(tree, f"{{{P}}}grpSpPr")
    transform = ET.SubElement(group, f"{{{A}}}xfrm")
    ET.SubElement(transform, f"{{{A}}}off", x="0", y="0")
    ET.SubElement(transform, f"{{{A}}}ext", cx="0", cy="0")
    ET.SubElement(transform, f"{{{A}}}chOff", x="0", y="0")
    ET.SubElement(transform, f"{{{A}}}chExt", cx="0", cy="0")
    ET.SubElement(root, f"{{{P}}}clrMap", bg1="lt1", tx1="dk1", bg2="lt2", tx2="dk2",
                  accent1="accent1", accent2="accent2", accent3="accent3", accent4="accent4",
                  accent5="accent5", accent6="accent6", hlink="hlink", folHlink="folHlink")
    return _xml(root)


def _new_relationships(rows: list[tuple[str, str, str]]) -> bytes:
    root = ET.Element(f"{{{PR}}}Relationships")
    for rid, relation_type, target in rows:
        ET.SubElement(root, f"{{{PR}}}Relationship", Id=rid, Type=f"{R}/{relation_type}", Target=target)
    return _xml(root)


def write_managed_notes(source: Path | str, destination: Path | str, narrations: dict[int, str]) -> None:
    source, destination = Path(source), ensure_new_path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("in-place PPTX editing is disabled")
    with ZipFile(source) as archive:
        slides = _ordered_slides(archive)
        expected = set(range(1, len(slides) + 1))
        if set(narrations) != expected:
            raise ValueError(f"narration indexes must exactly cover physical slides 1..{len(slides)}")
        replacements: dict[str, bytes] = {}
        additions: dict[str, bytes] = {}
        missing = [slide for slide in slides if _notes_part(archive, slide["slide_part"]) is None]
        master_relations = [(rid, value) for rid, value in _rels(archive, "ppt/presentation.xml").items()
                            if not value["external"] and value["type"] == "notesMaster"]
        content_types = ET.fromstring(archive.read("[Content_Types].xml"))
        if missing:
            if len(master_relations) > 1:
                raise ValueError("presentation has multiple notes masters")
            if master_relations:
                master_rid, master_relation = master_relations[0]
                master_part = master_relation["target"]
            else:
                used = set(archive.namelist())
                master_number = 1
                while f"ppt/notesMasters/notesMaster{master_number}.xml" in used:
                    master_number += 1
                master_part = f"ppt/notesMasters/notesMaster{master_number}.xml"
                presentation_rels_name = "ppt/_rels/presentation.xml.rels"
                presentation_rels = ET.fromstring(archive.read(presentation_rels_name))
                master_rid = _next_rid(presentation_rels)
                ET.SubElement(presentation_rels, f"{{{PR}}}Relationship", Id=master_rid,
                              Type=f"{R}/notesMaster", Target=posixpath.relpath(master_part, "ppt"))
                replacements[presentation_rels_name] = _xml(presentation_rels)
                presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
                master_list = presentation.find("p:notesMasterIdLst", NS)
                if master_list is None:
                    master_list = ET.Element(f"{{{P}}}notesMasterIdLst")
                    slide_list = presentation.find("p:sldIdLst", NS)
                    index = list(presentation).index(slide_list) if slide_list is not None else len(presentation)
                    presentation.insert(index, master_list)
                ET.SubElement(master_list, f"{{{P}}}notesMasterId", {RID: master_rid})
                replacements["ppt/presentation.xml"] = _xml(presentation)
                additions[master_part] = _new_notes_master()
                master_rels_name = posixpath.join(posixpath.dirname(master_part), "_rels", posixpath.basename(master_part) + ".rels")
                theme_parts = sorted(name for name in archive.namelist()
                                     if name.startswith("ppt/theme/") and name.endswith(".xml"))
                master_rels = [] if not theme_parts else [
                    ("rId1", "theme", posixpath.relpath(theme_parts[0], posixpath.dirname(master_part)))
                ]
                additions[master_rels_name] = _new_relationships(master_rels)
                _add_override(content_types, master_part,
                              "application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml")
            existing_names = set(archive.namelist()) | set(additions)
            next_note_number = 1
            for slide in missing:
                while f"ppt/notesSlides/notesSlide{next_note_number}.xml" in existing_names:
                    next_note_number += 1
                notes_part = f"ppt/notesSlides/notesSlide{next_note_number}.xml"
                existing_names.add(notes_part)
                next_note_number += 1
                slide["created_notes_part"] = notes_part
                slide_rels_name = posixpath.join(posixpath.dirname(slide["slide_part"]), "_rels",
                                                 posixpath.basename(slide["slide_part"]) + ".rels")
                if slide_rels_name in archive.namelist():
                    slide_rels = ET.fromstring(archive.read(slide_rels_name))
                else:
                    slide_rels = ET.Element(f"{{{PR}}}Relationships")
                notes_rid = _next_rid(slide_rels)
                ET.SubElement(slide_rels, f"{{{PR}}}Relationship", Id=notes_rid, Type=f"{R}/notesSlide",
                              Target=posixpath.relpath(notes_part, posixpath.dirname(slide["slide_part"])))
                if slide_rels_name in archive.namelist():
                    replacements[slide_rels_name] = _xml(slide_rels)
                else:
                    additions[slide_rels_name] = _xml(slide_rels)
                note_rels_name = posixpath.join(posixpath.dirname(notes_part), "_rels", posixpath.basename(notes_part) + ".rels")
                additions[note_rels_name] = _new_relationships([
                    ("rId1", "notesMaster", posixpath.relpath(master_part, posixpath.dirname(notes_part))),
                    ("rId2", "slide", posixpath.relpath(slide["slide_part"], posixpath.dirname(notes_part))),
                ])
                _add_override(content_types, notes_part,
                              "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml")
            replacements["[Content_Types].xml"] = _xml(content_types)
        for slide in slides:
            text = narrations[slide["physical_index"]]
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"missing reviewed narration for slide {slide['physical_index']}")
            notes_part = _notes_part(archive, slide["slide_part"])
            if notes_part:
                replacements[notes_part] = _replace_managed_block(archive.read(notes_part), text)
            else:
                additions[slide["created_notes_part"]] = _new_notes_slide(text)
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            with ZipFile(temporary, "w") as output:
                for info in archive.infolist():
                    output.writestr(info, replacements.get(info.filename, archive.read(info.filename)))
                for name, data in additions.items():
                    output.writestr(name, data)
            with ZipFile(temporary) as verification:
                if verification.testzip() is not None:
                    raise ValueError("written PPTX failed ZIP integrity validation")
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()


def _model_digest(model_dir: Path) -> str:
    if not model_dir.is_dir():
        raise ValueError(f"local model directory does not exist: {model_dir}")
    files = sorted(path for path in model_dir.rglob("*") if path.is_file())
    if not files or not any(path.suffix == ".safetensors" for path in files):
        raise ValueError("local Qwen3-TTS model must contain .safetensors weights")
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(model_dir)).encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def _audio_cache_key(text: str, model_sha256: str, backend: str, speaker: str, language: str) -> str:
    identity = {"schema": 1, "text": text, "model_sha256": model_sha256,
                "backend": backend, "speaker": speaker, "language": language}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def audio_cache_key(text: str, model_dir: Path | str, backend: str, speaker: str, language: str) -> str:
    return _audio_cache_key(text, _model_digest(Path(model_dir)), backend, speaker, language)


def select_backend(requested: str, availability: dict[str, bool]) -> str:
    if requested not in {"auto", "mlx", "cpu"}:
        raise ValueError("backend must be auto, mlx, or cpu")
    if requested == "auto":
        for candidate in ("mlx", "cpu"):
            if availability.get(candidate, False):
                return candidate
        raise RuntimeError("No local TTS backend is available; install dependencies outside this run")
    if not availability.get(requested, False):
        raise RuntimeError(f"{requested} backend is unavailable; no cloud fallback is permitted")
    return requested


def _backend_availability() -> dict[str, bool]:
    mlx_ok = all(importlib.util.find_spec(name) is not None for name in ("mlx", "mlx_audio", "numpy"))
    if mlx_ok:
        try:
            import mlx.core as mx
            mlx_ok = bool(mx.metal.is_available())
        except Exception:
            mlx_ok = False
    cpu_ok = all(importlib.util.find_spec(name) is not None for name in ("torch", "qwen_tts", "numpy"))
    return {"mlx": mlx_ok, "cpu": cpu_ok}


def build_timeline(rows: list[dict[str, Any]], lead_seconds: float = .35,
                   tail_seconds: float = .65) -> list[dict[str, Any]]:
    if lead_seconds < 0 or tail_seconds < 0:
        raise ValueError("lead and tail must be non-negative")
    result: list[dict[str, Any]] = []
    cursor = 0.0
    for row in rows:
        audio_seconds = float(row["audio_seconds"])
        if audio_seconds <= 0:
            raise ValueError(f"invalid audio duration on slide {row.get('physical_index')}")
        duration = lead_seconds + audio_seconds + tail_seconds
        result.append({**row, "start_seconds": round(cursor, 9), "duration_seconds": round(duration, 9),
                       "speech_start_seconds": round(cursor + lead_seconds, 9), "tempo": 1.0})
        cursor += duration
    return result


def compare_transcript(expected: str, recognized: str, threshold: float = .82) -> dict[str, Any]:
    def canonical(value: str) -> str:
        return re.sub(r"[^0-9a-z가-힣]", "", unicodedata.normalize("NFC", value).lower())
    wanted, actual = canonical(expected), canonical(recognized)
    ratio = SequenceMatcher(None, wanted, actual, autojunk=False).ratio() if wanted else 0.0
    return {"ratio": round(ratio, 4), "review_required": ratio < threshold or len(actual) < len(wanted) * .7,
            "expected_characters": len(wanted), "recognized_characters": len(actual)}


def _load_narration(path: Path, require_reviewed: bool = True) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if require_reviewed and document.get("reviewed") is not True:
        raise ValueError("narration draft is not approved; set reviewed=true only after human review")
    if require_reviewed and not str(document.get("review_basis", "")).strip():
        raise ValueError("review_basis must record the explicit whole-deck source or draft approval")
    slides = document.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("narration must contain a non-empty slides list")
    indexes = [row.get("physical_index") for row in slides]
    if indexes != list(range(1, len(slides) + 1)):
        raise ValueError("narration slides must be in complete physical order")
    for row in slides:
        if not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError(f"slide {row['physical_index']} has no narration; missing text is never invented")
    return document


def validate_narration_source(document: dict[str, Any], pptx: Path | str) -> None:
    """Bind reviewed narration to its exact PPTX and authoritative extracted notes."""
    pptx = Path(pptx)
    expected_hash = document.get("source_pptx_sha256")
    if not isinstance(expected_hash, str) or expected_hash != _sha256(pptx):
        raise ValueError("source_pptx_sha256 does not match the supplied PPTX")
    mode = document.get("source_mode")
    if mode not in {"existing-notes-authoritative", "approved-rewrite"}:
        raise ValueError("source_mode must be existing-notes-authoritative or approved-rewrite")
    if mode == "existing-notes-authoritative":
        extracted = extract_existing_notes(pptx)
        expected = [(row["physical_index"], row["text"]) for row in extracted]
        actual = [(row.get("physical_index"), row.get("text")) for row in document.get("slides", [])]
        if actual != expected:
            raise ValueError("authoritative narration must exactly match cleaned existing notes")


def prepare_workspace(pptx: Path, output: Path) -> None:
    ensure_new_path(output)
    output.mkdir(parents=True)
    try:
        inventory = inventory_pptx(pptx)
        notes = extract_existing_notes(pptx)
        _atomic_json(output / "inventory.json", inventory)
        _atomic_json(output / "existing-notes.json", {"schema": 1, "source_pptx_sha256": inventory["source_sha256"], "slides": notes})
        draft_slides = [{"physical_index": row["physical_index"], "title": row["title"], "role": "",
                         "text": row["text"], "reviewed": False} for row in notes]
        _atomic_json(output / "narration-draft.json", {"schema": 1, "source_pptx_sha256": inventory["source_sha256"],
                                                       "source_mode": "existing-notes-authoritative",
                                                       "reviewed": False, "review_basis": "", "slides": draft_slides})
        story = ["# Presentation story review", "", "This file is a planning aid. It does not supply narration.", "",
                 "## Global thesis", "", "- Audience decision:", "- One-sentence thesis:", "- Closing action:", "",
                 "## Chapter themes", "", "- Chapter 1:", "- Chapter 2:", "- Chapter 3:", "",
                 "## Timing plan", "", "- Planning target: 45 minutes for body slides only.",
                 "- Mark title and agenda roles; exclude them from the body target.",
                 "- Do not time-stretch generated speech to force the target.", ""]
        for row in inventory["slides"]:
            story += [f"## Slide {row['physical_index']}: {row['title'] or '(untitled)'}", "", "- Purpose:", "- Evidence:", "- Transition:", ""]
        (output / "story-template.md").write_text("\n".join(story), encoding="utf-8")
    except Exception:
        shutil.rmtree(output)
        raise


def _probe_audio(path: Path, ffprobe: str) -> dict[str, Any]:
    command = [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
               "stream=codec_name,channels,sample_rate,duration:format=duration", "-of", "json", str(path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    if not data.get("streams"):
        raise RuntimeError(f"no audio stream in {path}")
    duration = float(data["streams"][0].get("duration") or data.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise RuntimeError(f"invalid duration in {path}")
    data["duration_seconds"] = duration
    return data


def _validate_decode(path: Path, ffmpeg: str) -> None:
    result = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-nostdin", "-i", str(path), "-f", "null", "-"],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"full decode failed for {path}: {result.stderr.strip()}")


def _write_flac(audio: Any, sample_rate: int, destination: Path, ffmpeg: str, ffprobe: str) -> dict[str, Any]:
    import numpy as np
    values = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not len(values) or not np.isfinite(values).all() or float(np.max(np.abs(values))) < .0001:
        raise RuntimeError("TTS returned empty or invalid audio")
    pcm = np.clip(np.rint(values * 32768), -32768, 32767).astype("<i2").tobytes()
    ensure_new_path(destination)
    temporary = destination.with_name(destination.name + ".tmp.flac")
    ensure_new_path(temporary)
    try:
        result = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-f", "s16le", "-ar", str(sample_rate),
                                 "-ac", "1", "-i", "pipe:0", "-c:a", "flac", "-compression_level", "8", str(temporary)],
                                input=pcm, capture_output=True)
        if result.returncode:
            raise RuntimeError(f"ffmpeg FLAC encode failed: {result.stderr.decode(errors='replace')}")
        _validate_decode(temporary, ffmpeg)
        info = _probe_audio(temporary, ffprobe)
        temporary.replace(destination)
        return {"sample_rate": sample_rate, "frames": len(values), "seconds": len(values) / sample_rate,
                "pcm_sha256": hashlib.sha256(pcm).hexdigest(), "file_sha256": _sha256(destination),
                "codec": info["streams"][0]["codec_name"]}
    finally:
        if temporary.exists():
            temporary.unlink()


def _materialize_audio_records(slides: list[dict[str, Any]], model_sha256: str, backend: str,
                               output: Path, synthesize: Any, encode: Any, verify: Any) -> list[dict[str, Any]]:
    """Materialize content-addressed audio with an atomic per-key resume checkpoint."""
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "audio-checkpoint.json"
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("model_sha256") != model_sha256 or checkpoint.get("backend") != backend:
            raise ValueError("audio checkpoint belongs to different model or backend inputs")
    else:
        checkpoint = {"schema": 1, "model_sha256": model_sha256, "backend": backend, "records": {}}
        previous_manifest = output / "audio-manifest.json"
        if previous_manifest.exists():
            previous = json.loads(previous_manifest.read_text(encoding="utf-8"))
            if previous.get("model_sha256") != model_sha256 or previous.get("backend") != backend:
                raise ValueError("audio manifest belongs to different model or backend inputs")
            for row in previous.get("slides", []):
                if row.get("key"):
                    checkpoint["records"][row["key"]] = {
                        "key": row["key"], "file_sha256": row.get("file_sha256"),
                        "seconds": row.get("audio_seconds"),
                    }
            _atomic_json(checkpoint_path, checkpoint)
    cache = checkpoint["records"]
    records = []
    for row in slides:
        key = _audio_cache_key(row["text"], model_sha256, backend, "Sohee", "Korean")
        destination = output / f"{key}.flac"
        cached = cache.get(key)
        if destination.exists():
            if not cached or cached.get("file_sha256") != _sha256(destination):
                raise RuntimeError(f"existing FLAC has no matching cache record or changed content: {destination}")
            seconds = float(verify(destination, cached))
        else:
            if cached:
                raise RuntimeError(f"checkpointed FLAC is missing: {destination}")
            generated = synthesize(row)
            storage = encode(generated, destination)
            if not destination.is_file() or storage.get("file_sha256") != _sha256(destination):
                raise RuntimeError("audio encoder did not publish the verified content it reported")
            seconds = float(verify(destination, storage))
            cached = {"key": key, **storage, "seconds": seconds}
            cache[key] = cached
            _atomic_json(checkpoint_path, checkpoint)
        records.append({"physical_index": row["physical_index"], "title": row.get("title", ""), "text": row["text"],
                        "key": key, "path": destination.name, "audio_seconds": seconds,
                        "file_sha256": cached["file_sha256"]})
    return records


def generate_tts(narration_path: Path, model_dir: Path, output: Path, backend_request: str,
                 ffmpeg: str, ffprobe: str, source_pptx: Path | None = None) -> None:
    document = _load_narration(narration_path)
    if document.get("source_mode"):
        if source_pptx is None:
            raise ValueError("--source-pptx is required for source-bound narration")
        validate_narration_source(document, source_pptx)
    if not Path(ffmpeg).is_file() and shutil.which(ffmpeg) is None:
        raise RuntimeError(f"required local ffmpeg executable not found: {ffmpeg}")
    if not Path(ffprobe).is_file() and shutil.which(ffprobe) is None:
        raise RuntimeError(f"required local ffprobe executable not found: {ffprobe}")
    backend = select_backend(backend_request, _backend_availability())
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      TOKENIZERS_PARALLELISM="false")
    output.mkdir(parents=True, exist_ok=True)
    model_sha256 = _model_digest(model_dir)
    runtime: dict[str, Any] = {}

    def synthesize(row: dict[str, Any]) -> tuple[Any, int]:
        import numpy as np
        seed = 20260918 + row["physical_index"]
        if backend == "mlx":
            if "model" not in runtime:
                import mlx.core as mx
                from mlx_audio.tts.utils import load_model
                runtime.update(model=load_model(model_dir), mx=mx)
            runtime["mx"].random.seed(seed)
            chunks = runtime["model"].generate_custom_voice(text=row["text"], speaker="Sohee", language="Korean",
                                                               max_tokens=1536, stream=True, streaming_interval=2.0)
            arrays, sample_rate = [], None
            for chunk in chunks:
                if sample_rate is not None and chunk.sample_rate != sample_rate:
                    raise RuntimeError("sample rate changed within one slide")
                sample_rate = chunk.sample_rate
                arrays.append(np.asarray(chunk.audio, dtype=np.float32).reshape(-1))
            if not arrays or sample_rate is None:
                raise RuntimeError("MLX Qwen3-TTS returned no audio")
            audio = np.concatenate(arrays)
            runtime["mx"].clear_cache()
            return audio, int(sample_rate)
        if "model" not in runtime:
            import torch
            from qwen_tts import Qwen3TTSModel
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
            runtime.update(torch=torch, model=Qwen3TTSModel.from_pretrained(
                str(model_dir), device_map="cpu", dtype=torch.float32,
                attn_implementation="sdpa", local_files_only=True))
        runtime["torch"].manual_seed(seed)
        with runtime["torch"].inference_mode():
            waves, sample_rate = runtime["model"].generate_custom_voice(
                text=row["text"], speaker="Sohee", language="Korean", max_new_tokens=1536)
        return np.asarray(waves[0], dtype=np.float32).reshape(-1), int(sample_rate)

    def encode(generated: tuple[Any, int], destination: Path) -> dict[str, Any]:
        audio, sample_rate = generated
        return _write_flac(audio, sample_rate, destination, ffmpeg, ffprobe)

    def verify(path: Path, record: dict[str, Any]) -> float:
        _validate_decode(path, ffmpeg)
        return _probe_audio(path, ffprobe)["duration_seconds"]

    records = _materialize_audio_records(document["slides"], model_sha256, backend, output,
                                         synthesize, encode, verify)
    _atomic_json(output / "audio-manifest.json", {"schema": 1, "backend": backend, "speaker": "Sohee",
                                                   "language": "Korean", "model_sha256": model_sha256,
                                                   "slides": records})


def _srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _ffmetadata_escape(text: str) -> str:
    return re.sub(r"([\\=;#])", r"\\\1", text.replace("\n", " "))


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed: {result.stderr[-4000:]}")


def _manifest_path(value: str, manifest: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (manifest.parent / path).resolve()


def _resolve_render_rows(manifest_path: Path | None, slides_dir: Path | None,
                         count: int) -> list[dict[str, Any]]:
    if manifest_path:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = data.get("slides", data)
        if not isinstance(rows, list):
            raise ValueError("render manifest must contain a slides list")
        mapping = {int(row["physical_index"]): row for row in rows}
    else:
        if not slides_dir:
            raise ValueError("provide --render-manifest or --slides-dir")
        mapping = {}
        for index in range(1, count + 1):
            matches = [path for path in (slides_dir / f"slide-{index}.png", slides_dir / f"slide-{index:02}.png") if path.is_file()]
            if len(matches) != 1:
                raise ValueError(f"expected one rendered PNG for physical slide {index}")
            mapping[index] = {"physical_index": index, "image": str(matches[0])}
    if set(mapping) != set(range(1, count + 1)):
        raise ValueError(f"render inputs must exactly cover physical slides 1..{count}")
    result = []
    for index in range(1, count + 1):
        row = mapping[index]
        image = _manifest_path(row["image"], manifest_path) if manifest_path else Path(row["image"])
        if not image.is_file():
            raise ValueError(f"missing local slide image: {image}")
        media = _manifest_path(row["media"], manifest_path) if manifest_path and row.get("media") else (Path(row["media"]) if row.get("media") else None)
        if media and not media.is_file():
            raise ValueError(f"missing explicit per-slide media: {media}")
        result.append({"physical_index": index, "image": image, "media": media})
    return result


def render_video(audio_manifest_path: Path, output: Path, ffmpeg: str, ffprobe: str,
                 render_manifest: Path | None = None, slides_dir: Path | None = None,
                 width: int = 1920, height: int = 1080, fps: int = 30,
                 lead_seconds: float = .35, tail_seconds: float = .65) -> None:
    output = ensure_new_path(output)
    srt = ensure_new_path(output.with_suffix(".srt"))
    chapters_file = ensure_new_path(output.with_suffix(".chapters.ffmetadata"))
    validation_file = ensure_new_path(output.with_suffix(".validation.json"))
    if width < 2 or height < 2 or fps < 1:
        raise ValueError("invalid render dimensions or frame rate")
    audio_manifest = json.loads(audio_manifest_path.read_text(encoding="utf-8"))
    audio_rows = audio_manifest.get("slides", [])
    if not audio_rows:
        raise ValueError("audio manifest has no slides")
    render_rows = _resolve_render_rows(render_manifest, slides_dir, len(audio_rows))
    audio_paths: dict[int, Path] = {}
    public_audio_rows = []
    for expected, row in enumerate(audio_rows, 1):
        if row.get("physical_index") != expected:
            raise ValueError("audio manifest is not in complete physical order")
        audio = _manifest_path(row["path"], audio_manifest_path)
        if not audio.is_file() or _sha256(audio) != row.get("file_sha256"):
            raise ValueError(f"audio cache missing or changed on physical slide {expected}")
        audio_paths[expected] = audio
        public_audio_rows.append({**row, "path": Path(row["path"]).name,
                                  "audio_seconds": _probe_audio(audio, ffprobe)["duration_seconds"]})
    timeline = build_timeline(public_audio_rows, lead_seconds, tail_seconds)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="presentation-studio-", dir=output.parent) as temporary_name:
        temporary = Path(temporary_name)
        parts = []
        static_fallback = []
        for row, visual in zip(timeline, render_rows):
            part = temporary / f"slide-{row['physical_index']:04}.mp4"
            audio = audio_paths[row["physical_index"]]
            duration = row["duration_seconds"]
            video_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v]"
            delay = round(lead_seconds * 1000)
            audio_filter = f"[1:a]adelay={delay},apad=pad_dur={tail_seconds:.9f}[a]"
            if visual["media"]:
                command = [ffmpeg, "-v", "error", "-nostdin", "-stream_loop", "-1", "-i", str(visual["media"]), "-i", str(audio)]
            else:
                command = [ffmpeg, "-v", "error", "-nostdin", "-loop", "1", "-framerate", str(fps), "-i", str(visual["image"]), "-i", str(audio)]
                static_fallback.append(row["physical_index"])
            _run(command + ["-filter_complex", f"[0:v]{video_filter};{audio_filter}", "-map", "[v]", "-map", "[a]",
                            "-t", f"{duration:.9f}", "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(part)])
            parts.append(part)
        concat = temporary / "concat.txt"
        concat.write_text("\n".join("file '" + str(path.resolve()).replace("'", "'\\''") + "'" for path in parts) + "\n", encoding="utf-8")
        staged_srt = temporary / "subtitles.srt"
        staged_srt.write_text("\n\n".join(f"{index}\n{_srt_time(row['speech_start_seconds'])} --> {_srt_time(row['speech_start_seconds'] + row['audio_seconds'])}\n{row['text']}"
                                                  for index, row in enumerate(timeline, 1)) + "\n", encoding="utf-8")
        chapters = [";FFMETADATA1"]
        for row in timeline:
            chapters += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(row['start_seconds'] * 1000)}",
                         f"END={round((row['start_seconds'] + row['duration_seconds']) * 1000)}",
                         f"title={_ffmetadata_escape(str(row['physical_index']) + '. ' + row.get('title', ''))}"]
        staged_chapters = temporary / "chapters.ffmetadata"
        staged_chapters.write_text("\n".join(chapters) + "\n", encoding="utf-8")
        building = temporary / "building.mp4"
        _run([ffmpeg, "-v", "error", "-nostdin", "-f", "concat", "-safe", "0", "-i", str(concat),
              "-i", str(staged_srt), "-i", str(staged_chapters), "-map", "0:v:0", "-map", "0:a:0", "-map", "1:0",
              "-map_metadata", "2", "-map_chapters", "2", "-c", "copy", "-c:s", "mov_text",
              "-metadata:s:s:0", "language=kor", "-movflags", "+faststart", str(building)])
        _validate_decode(building, ffmpeg)
        probe = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_chapters", "-show_format", "-of", "json", str(building)],
                               capture_output=True, text=True)
        if probe.returncode:
            raise RuntimeError(f"ffprobe failed on final MP4: {probe.stderr}")
        info = json.loads(probe.stdout)
        types = {stream.get("codec_type") for stream in info.get("streams", [])}
        if not {"video", "audio", "subtitle"}.issubset(types):
            raise RuntimeError("final MP4 is missing video, audio, or subtitle streams")
        staged_srt.replace(srt)
        staged_chapters.replace(chapters_file)
        building.replace(output)
        _validate_decode(output, ffmpeg)
        final_probe = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_chapters", "-show_format",
                                      "-of", "json", str(output)], capture_output=True, text=True)
        if final_probe.returncode:
            raise RuntimeError(f"ffprobe failed on published MP4: {final_probe.stderr}")
        final_info = json.loads(final_probe.stdout)
        if isinstance(final_info.get("format"), dict) and "filename" in final_info["format"]:
            final_info["format"]["filename"] = output.name
        staged_validation = temporary / "validation.json"
        _atomic_json(staged_validation, {"schema": 1, "full_decode": "passed",
                                         "output": {"filename": output.name, "bytes": output.stat().st_size,
                                                    "sha256": _sha256(output)},
                                         "probe": final_info, "timeline": timeline,
                                         "static_fallback_slides": static_fallback,
                                         "explicit_media_slides": [row["physical_index"] for row in render_rows if row["media"]]})
        staged_validation.replace(validation_file)


def audit_audio(audio_manifest_path: Path, asr_model: Path, output: Path,
                threshold: float = .82) -> dict[str, Any]:
    output = ensure_new_path(output)
    if not asr_model.is_dir() or not (asr_model / "model.bin").is_file():
        raise ValueError("--asr-model must be a local faster-whisper/CTranslate2 directory containing model.bin")
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("faster-whisper is unavailable in this Python; no remote fallback is permitted") from error
    manifest = json.loads(audio_manifest_path.read_text(encoding="utf-8"))
    slides = manifest.get("slides", [])
    if not slides:
        raise ValueError("audio manifest has no slides")
    model = WhisperModel(str(asr_model), device="cpu", compute_type="int8", local_files_only=True)
    records = []
    for expected_index, row in enumerate(slides, 1):
        if row.get("physical_index") != expected_index:
            raise ValueError("audio manifest is not in complete physical order")
        audio = _manifest_path(row["path"], audio_manifest_path)
        if not audio.is_file() or _sha256(audio) != row.get("file_sha256"):
            raise ValueError(f"audio cache missing or changed on physical slide {expected_index}")
        segments, info = model.transcribe(str(audio), language="ko", beam_size=5, vad_filter=True)
        transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        comparison = compare_transcript(row["text"], transcript, threshold)
        records.append({"physical_index": expected_index, "key": row.get("key"), "expected": row["text"],
                        "recognized": transcript, **comparison,
                        "detected_language": getattr(info, "language", None)})
    report = {"schema": 1, "provider": "local-faster-whisper-cpu-int8", "threshold": threshold,
              "slides": records, "checked": len(records),
              "review_required": sum(bool(row["review_required"]) for row in records)}
    _atomic_json(output, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="inventory a PPTX and create non-invented review templates")
    prepare.add_argument("--pptx", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    extract = sub.add_parser("existing-notes", help="extract current notes in physical slide order")
    extract.add_argument("--pptx", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    notes = sub.add_parser("notes", help="write a reviewed narration as a managed notes block")
    notes.add_argument("--pptx", type=Path, required=True)
    notes.add_argument("--narration", type=Path, required=True)
    notes.add_argument("--output", type=Path, required=True)
    tts = sub.add_parser("tts", help="generate cached local Qwen3-TTS Sohee FLAC files")
    tts.add_argument("--narration", type=Path, required=True)
    tts.add_argument("--model", type=Path, required=True)
    tts.add_argument("--output", type=Path, required=True)
    tts.add_argument("--source-pptx", type=Path,
                     help="exact source PPTX required when narration has source_mode")
    tts.add_argument("--backend", choices=("auto", "mlx", "cpu"), default="auto")
    tts.add_argument("--python", type=Path, help="local Python interpreter containing the selected TTS backend")
    tts.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    tts.add_argument("--ffprobe", default=shutil.which("ffprobe") or "ffprobe")
    video = sub.add_parser("video", help="render local PNG/media inputs and FLAC narration to MP4/SRT")
    video.add_argument("--audio-manifest", type=Path, required=True)
    visuals = video.add_mutually_exclusive_group(required=True)
    visuals.add_argument("--render-manifest", type=Path)
    visuals.add_argument("--slides-dir", type=Path)
    video.add_argument("--output", type=Path, required=True)
    video.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    video.add_argument("--ffprobe", default=shutil.which("ffprobe") or "ffprobe")
    video.add_argument("--width", type=int, default=1920)
    video.add_argument("--height", type=int, default=1080)
    video.add_argument("--fps", type=int, default=30)
    video.add_argument("--lead-seconds", type=float, default=.35)
    video.add_argument("--tail-seconds", type=float, default=.65)
    audit = sub.add_parser("audit", help="compare FLAC narration with a local faster-whisper transcript")
    audit.add_argument("--audio-manifest", type=Path, required=True)
    audit.add_argument("--asr-model", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    audit.add_argument("--python", type=Path, help="local Python interpreter containing faster-whisper")
    audit.add_argument("--threshold", type=float, default=.82)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        prepare_workspace(args.pptx, args.output)
    elif args.command == "existing-notes":
        output = ensure_new_path(args.output)
        _atomic_json(output, {"schema": 1, "slides": extract_existing_notes(args.pptx)})
    elif args.command == "notes":
        document = _load_narration(args.narration)
        validate_narration_source(document, args.pptx)
        if document["source_mode"] == "existing-notes-authoritative":
            output = ensure_new_path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
            os.close(handle)
            temporary = Path(temporary_name)
            try:
                shutil.copyfile(args.pptx, temporary)
                if _sha256(temporary) != document["source_pptx_sha256"]:
                    raise RuntimeError("source changed while publishing authoritative notes-as-is output")
                temporary.replace(output)
            finally:
                if temporary.exists():
                    temporary.unlink()
        else:
            write_managed_notes(args.pptx, args.output,
                                {row["physical_index"]: row["text"] for row in document["slides"]})
    elif args.command == "tts":
        requested_python = args.python.resolve() if args.python else Path(sys.executable).resolve()
        if not requested_python.is_file():
            raise RuntimeError(f"local Python interpreter not found: {requested_python}")
        if requested_python != Path(sys.executable).resolve():
            command = [str(requested_python), str(Path(__file__).resolve()), "tts", "--narration", str(args.narration),
                       "--model", str(args.model), "--output", str(args.output), "--backend", args.backend,
                       "--ffmpeg", args.ffmpeg, "--ffprobe", args.ffprobe]
            if args.source_pptx:
                command += ["--source-pptx", str(args.source_pptx)]
            return subprocess.run(command).returncode
        generate_tts(args.narration, args.model, args.output, args.backend, args.ffmpeg, args.ffprobe,
                     args.source_pptx)
    elif args.command == "video":
        render_video(args.audio_manifest, args.output, args.ffmpeg, args.ffprobe, args.render_manifest,
                     args.slides_dir, args.width, args.height, args.fps, args.lead_seconds, args.tail_seconds)
    elif args.command == "audit":
        requested_python = args.python.resolve() if args.python else Path(sys.executable).resolve()
        if not requested_python.is_file():
            raise RuntimeError(f"local Python interpreter not found: {requested_python}")
        if requested_python != Path(sys.executable).resolve():
            command = [str(requested_python), str(Path(__file__).resolve()), "audit", "--audio-manifest", str(args.audio_manifest),
                       "--asr-model", str(args.asr_model), "--output", str(args.output), "--threshold", str(args.threshold)]
            return subprocess.run(command).returncode
        report = audit_audio(args.audio_manifest, args.asr_model, args.output, args.threshold)
        print(json.dumps({"checked": report["checked"], "review_required": report["review_required"],
                          "provider": report["provider"]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
