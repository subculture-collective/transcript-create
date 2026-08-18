from __future__ import annotations

import json
from pathlib import Path

import nbformat
from nbclient import NotebookClient


OUTPUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = OUTPUT_DIR.parents[1]
summary = json.loads((OUTPUT_DIR / "summary.json").read_text(encoding="utf-8"))

notebook = nbformat.v4.new_notebook(
    metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    }
)
notebook.cells = [
    nbformat.v4.new_markdown_cell(
        f"""# Transcript Sampling Audit

## tl;dr

- Sampled **{summary['sampled_sections']} one-minute sections** from **{summary['sampled_videos']} videos** spanning **{summary['minimum_uploaded_date']} to {summary['maximum_uploaded_date']}**.
- Flagged **{summary['flagged_sections']} sections ({summary['flagged_share']:.1%})** for manual listening.
- Extracted **{summary['name_rows']} proper-name candidates** and **{summary['possible_name_mistranscriptions']} possible spelling/alias mismatches**.
- These are screening results. YouTube captions are a comparison source, not ground truth.
"""
    ),
    nbformat.v4.new_markdown_cell(
        """## Context & Methods

The audit deterministically selects one video from each of 40 chronological buckets among completed videos that have both native Whisper segments and YouTube captions. Each selected video contributes windows at approximately 5%, 27%, 50%, 73%, and 95% of its duration.

### Key Assumptions

- Low agreement identifies sections worth listening to; it does not establish which transcript is correct.
- Timing drift, censorship tokens, music labels, and caption omissions can lower agreement without a Whisper error.
- Proper-name extraction is intentionally broad. Low-confidence capitalized phrases remain candidates until manually checked.
"""
    ),
    nbformat.v4.new_code_cell(
        """from pathlib import Path
import csv, json, statistics

AUDIT_DIR = Path('output/transcript-audit-2026-08-11')

def read_csv(name):
    with (AUDIT_DIR / name).open(encoding='utf-8') as handle:
        return list(csv.DictReader(handle))

summary = json.loads((AUDIT_DIR / 'summary.json').read_text(encoding='utf-8'))
samples = read_csv('sampled_sections.csv')
flags = read_csv('flagged_sections.csv')
names = read_csv('name_candidates.csv')
name_leads = read_csv('possible_name_mistranscriptions.csv')
issue_counts = read_csv('issue_counts.csv')
summary"""
    ),
    nbformat.v4.new_markdown_cell("## Data\n\nThe sampled row grain is one 60-second window per video-position pair. Exact SQL is saved in `sampling_query.sql`; full rows are retained in `sampled_sections.csv`."),
    nbformat.v4.new_code_cell(
        """print('Sampled rows:', len(samples))
print('Distinct videos:', len({row['youtube_id'] for row in samples}))
print('Positions:', sorted({row['sample_position'] for row in samples}))
print('Date range:', min(row['uploaded_date'] for row in samples), 'to', max(row['uploaded_date'] for row in samples))"""
    ),
    nbformat.v4.new_markdown_cell("## Results\n\n### Manual-review volume by screening signal"),
    nbformat.v4.new_code_cell(
        """for row in issue_counts:
    print(f\"{row['issue_type']:<34} {int(row['flagged_sections']):>3} sections ({float(row['share']):.1%})\")"""
    ),
    nbformat.v4.new_markdown_cell("### Highest-priority timestamp checks"),
    nbformat.v4.new_code_cell(
        """for row in flags[:15]:
    print(f\"[{row['review_priority']}] {row['uploaded_date']} {row['timestamp']} — {row['video_title']}\")
    print('Reason:', row['issues'])
    print('Possible differences:', row['possible_word_or_name_differences'] or '(alignment unavailable)')
    print('URL:', row['youtube_url'])
    print()"""
    ),
    nbformat.v4.new_markdown_cell("### Possible name spellings and aliases to verify"),
    nbformat.v4.new_code_cell(
        """for row in name_leads:
    print(f\"{row['observed_form']} -> {row['possible_correction']} ({row['similarity']})\")
    print(f\"  {row['timestamp']} | {row['video_title']}\")
    print(f\"  {row['youtube_url']}\")"""
    ),
    nbformat.v4.new_markdown_cell("### Name-candidate confidence profile"),
    nbformat.v4.new_code_cell(
        """from collections import Counter
print(Counter(row['confidence'] for row in names))
print('Top recurring candidates:')
for row in names[:20]:
    print(row['sample_occurrences'], row['confidence'], row['canonical_or_candidate'], row['first_timestamp'])"""
    ),
    nbformat.v4.new_markdown_cell(
        """## Takeaways

- Begin manual review with the highest-priority disagreement and repetition rows, then work down the complete flagged-section CSV.
- Treat fuzzy name suggestions as hypotheses. Several are likely genuine (`Emma Vigland`, `Bradley Martin`, `Carl Marx`, `Aiden Ross`), while generic phrase matches can be false positives.
- Use verified corrections to expand the decoder prompt and contextual replacement list; do not automatically rewrite the archive from this screening output.
"""
    ),
]

client = NotebookClient(notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(REPO_ROOT)}})
client.execute()
nbformat.write(notebook, OUTPUT_DIR / "transcript_sampling_audit.ipynb")
print(OUTPUT_DIR / "transcript_sampling_audit.ipynb")
