# Provenance and licenses

This source is distributed through the access-controlled private repository `dontotl/workplace-toolkit`; it is not a public release or marketplace listing. The owner selected MIT on 2026-09-18 for the new code and skill instructions; see LICENSE.

- Research and reporting instructions were adapted from the user's existing workflow skills. Environment-specific endpoints, private source maps and user credentials were removed.
- The prior PPT translator is MIT-licensed (Copyright 2025 PPT Translator Contributors). Its separation of extraction and application informed this design. The new `ppt_bridge.py` is a separate OOXML text-patching implementation, not a copied provider client or bundled upstream repository. New code is MIT by the owner's explicit choice. Any later imported upstream source must carry its original notice.
- Presentation tooling generalizes the user's local narration work; model weights and proprietary presentation helpers are not redistributed.
- Runtime/development dependencies are installed separately under their respective licenses: lxml, python-pptx, Pillow, PyYAML, pytest, FFmpeg/LibreOffice, Qwen TTS and optional MLX/PyTorch/ASR stacks. Users must check model and dependency licenses for their intended use.
- No third-party `pptx`, `archify`, Oracle Facts or other installed skill is copied wholesale into this package.

Do not include company-owned source, branding, restricted guides or customer data in a public release without the appropriate rights review. The source scan is a safeguard, not proof of legal clearance.
