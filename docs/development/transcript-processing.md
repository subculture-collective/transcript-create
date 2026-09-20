# Transcript processing

**Status:** shipped implementation guide (2026-09-19).

The native worker stores the source transcript and then applies deterministic formatting
through `worker/formatter.py`. Formatting operates on copies of the input segments; it
does not replace the downloaded source material.

The formatter can normalize Unicode and whitespace, remove configured sound-event
tokens and conservative filler words, detect common Whisper artifacts, add rule-based
sentence punctuation, repair capitalization, split or merge segments, and retain speaker
labels. Each transformation is controlled by the `CLEANUP_*` settings in
`app/settings.py`. Set `CLEANUP_ENABLED=false` to return the input segments unchanged.

`CLEANUP_PUNCTUATION_MODE=rule-based` is the implemented punctuation mode. A model name
setting exists for deployment compatibility, but selecting a model does not install or
invoke a punctuation model. Test a client-specific configuration against representative
recordings before changing production defaults because filler removal and segmentation
can alter citation boundaries.

Worker file cleanup is a separate concern. `CLEANUP_AFTER_PROCESS` and the
`CLEANUP_DELETE_*` settings control removal of local audio and chunk artifacts after a
successful pipeline run. They do not alter stored transcripts. See the
[deployment troubleshooting guide](../deployment/troubleshooting.md) for those settings.

Focused verification:

```bash
.venv/bin/python -m pytest tests/worker/test_formatter.py tests/worker/test_pipeline_stages.py
```
