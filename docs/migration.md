# Migration from existing skills

| Old | New |
|---|---|
| oracle-demo-research | workplace-research with optional Oracle reference |
| sharepoint-browser-download | workplace-research download-only route |
| ppt-translator (provider API) | ppt-translator (current Codex session + local bridge) |
| visit-call-report (fixed report site) | visit-call-report (selected local history/configured site) |
| project-specific narration scripts | presentation-studio |

Keep the old directories until the new samples and tests pass. The installer refuses to overwrite them. Make an explicit backup outside Codex skill discovery locations, then remove/disable the old active entry only when ready. Do not leave two active directories with the same skill name: Codex may expose both, not merge them. Do not simply rename the directory inside the discovery root as a backup.

No script in this package edits the user's Codex configuration. Migration does not transfer the author's accounts, report server URL, private Oracle source map or TTS model paths. Supply those locally and do not commit them.
