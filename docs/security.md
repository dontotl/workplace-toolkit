# Processing and distribution boundaries

- Enterprise Codex: language work uses the current approved session, not a copied API key. A successful `codex login status` does not prove an Enterprise workspace or approval for every data classification. Verify workspace and company policy before business content is read.
- Local-only: scripts may process files locally, but showing raw text/screenshots to a remotely hosted agent is still model processing. Use a local agent or manually prepared translation/narration files. Never silently switch to a cloud model.
- Translation bridge and media commands do not require authentication secrets. Installed scripts never mine another project's .env or auth cache. Setup may download dependencies/models only as an explicit user setup action; runtime stays local.
- Research requires existing authorized connectors/browser tools. No borrowed author sessions, credentials, private source maps or object storage are shipped. No permission bypass, automatic sharing or public links.
- Source archives allowlist text/code files, reject symlinks and suspicious private-path/key/endpoint patterns, and exclude generated media, customer materials, model weights, virtual environments and local settings. Review the manifest manually before wider sharing or public publication; scanning is not exhaustive DLP.
- The source is distributed through the access-controlled private repository `dontotl/workplace-toolkit`; collaborators need explicit repository access. This is not a public release, public link or marketplace listing.
- Release approval, licensing and company IP review are separate from passing tests. Private repository access must not be treated as approval to redistribute the source publicly.
