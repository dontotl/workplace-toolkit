# Authenticated local download

Use only for a request to save a local copy. Use the user's selected local destination and the exact verified source file.

1. Resolve the canonical SharePoint/OneDrive URL using connected search/metadata tools or a supplied link.
2. Discover an available authenticated browser tool and follow its own skill instructions. Open the exact file or verified parent folder. Use the visible Download command; for Office previews, select the file in the parent folder when needed.
3. Confirm the download finished. Before copying, inspect filename, type and nonzero size; a PPTX must be a readable ZIP with presentation parts and a PDF must have its expected header. A sign-in HTML page is not a successful document download.
4. If the destination exists, compare checksums. Reuse an identical file; for different bytes choose a new filename and report the conflict. Never silently overwrite an existing document.
5. Report local output, original source, modified date when available, size and verification result. Do not publish expiring URLs, cookies or access tokens.

Missing browser/connector: report the unavailable capability and let the user download through their normal authenticated browser; then continue local validation. Do not install arbitrary extensions, scrape session cookies, or make up connector names.

Access or download failure: report the actual blocker. A proxy/handoff 403 is not necessarily a SharePoint permission denial. Do not retry temporary runtime URLs through curl, bypass access controls, create public links or substitute an unverified copy. A different source requires user direction and provenance verification.
