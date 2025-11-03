# Backfill Formatting Script

## Overview

The `backfill_formatting.py` script applies transcript formatting/cleanup to existing videos that were transcribed before the formatting feature was added or with an older formatting version.

## Features

- **Idempotency**: Automatically skips transcripts already formatted with the current version and configuration
- **Dry-run mode**: Preview changes without modifying the database
- **Flexible filtering**: Process specific videos, channels, or jobs
- **Safe batching**: Configurable batch sizes with transaction-per-batch for safe interruption
- **Resume capability**: Can be stopped and restarted without data loss
- **Force reprocessing**: Option to reprocess all transcripts regardless of version
- **Progress tracking**: Detailed structured logging with metrics
- **Error handling**: Gracefully handles per-video errors without stopping the batch

## Requirements

- Database migration `003_transcript_cleanup` must be applied
- Formatting module enabled in settings (`CLEANUP_ENABLED=true`)
- Database access via `DATABASE_URL` environment variable

## Usage

### Basic Usage

Process all unformatted transcripts in batches:
```bash
python scripts/backfill_formatting.py --batch 100 --until-empty
```

### Dry Run

Preview changes without committing to the database:
```bash
python scripts/backfill_formatting.py --dry-run --batch 10
```

### Filter by Specific Videos

Process only specific video UUIDs:
```bash
python scripts/backfill_formatting.py --video-ids UUID1,UUID2,UUID3
```

### Filter by Channel

Process all videos from a specific channel:
```bash
python scripts/backfill_formatting.py --channel-name "My Channel" --batch 50 --until-empty
```

### Filter by Job

Process all videos from a specific job:
```bash
python scripts/backfill_formatting.py --job-id JOB_UUID --batch 20
```

### Force Reprocessing

Reprocess all transcripts regardless of version:
```bash
python scripts/backfill_formatting.py --force --until-empty --batch 100
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--batch` | Number of videos to process per batch | 10 |
| `--until-empty` | Continue processing until no more videos need formatting | false |
| `--max-iterations` | Maximum number of iterations (safety cap with --until-empty) | unlimited |
| `--dry-run` | Preview changes without committing | false |
| `--force` | Force reprocessing even if already formatted | false |
| `--video-ids` | Comma-separated list of video UUIDs to process | all |
| `--channel-name` | Filter to videos from a specific channel | all |
| `--job-id` | Filter to videos from a specific job UUID | all |

## How It Works

### Version Tracking

The script uses a semantic version number (`FORMATTING_VERSION`) and a configuration hash to determine if a transcript needs reprocessing:

1. **Never formatted**: Transcripts without `cleanup_config` are processed
2. **Version changed**: Transcripts with an older version are reprocessed
3. **Config changed**: Transcripts with a different configuration hash are reprocessed
4. **Already current**: Transcripts matching current version and config are skipped

### Processing Flow

1. **Load configuration**: Reads current formatting settings from `app/settings.py`
2. **Compute config hash**: Creates a hash of the configuration for change detection
3. **Select batch**: Queries database for videos needing formatting based on filters
4. **Check each video**: Determines if transcript needs processing
5. **Apply formatting**: Runs formatter on segments and updates database
6. **Update metadata**: Records version, config hash, and timestamp in `transcripts.cleanup_config`
7. **Repeat**: Continues to next batch if `--until-empty` is enabled

### Database Updates

The script updates two tables:

**segments table:**
- `text_cleaned`: Stores the formatted text
- `cleanup_applied`: Set to `true` when formatted

**transcripts table:**
- `cleanup_config`: JSON with version, config hash, config, and timestamp
- `is_cleaned`: Set to `true` when formatted

## Examples

### Incremental Processing

Process in small batches, manually controlling when to continue:
```bash
# Process first batch
python scripts/backfill_formatting.py --batch 50

# Check results, then process next batch
python scripts/backfill_formatting.py --batch 50

# Repeat as needed
```

### Full Backfill with Safety Cap

Process all videos with a safety limit:
```bash
python scripts/backfill_formatting.py --until-empty --batch 100 --max-iterations 50
```

### Reformat After Config Change

Force reprocessing when you've changed formatting settings:
```bash
python scripts/backfill_formatting.py --force --until-empty --batch 100
```

### Test on Specific Videos First

Preview changes on a few test videos before full rollout:
```bash
# Dry run on test videos
python scripts/backfill_formatting.py --dry-run --video-ids TEST_UUID1,TEST_UUID2

# If satisfied, process for real
python scripts/backfill_formatting.py --video-ids TEST_UUID1,TEST_UUID2
```

## Monitoring

### Logs

The script outputs structured JSON logs (or text logs depending on `LOG_FORMAT` setting) with:
- Batch progress (iteration, videos processed, errors, skipped)
- Per-video results (segments processed, updated, status)
- Final summary (total processed, errors, skipped, iterations)

### Metrics

Key metrics reported:
- `processed`: Videos successfully formatted
- `skipped`: Videos already formatted or filtered out
- `errors`: Videos that failed formatting
- `iterations`: Number of batches processed
- `segments_processed`: Total segments formatted per video
- `segments_updated`: Total segments updated in database per video

## Troubleshooting

### No videos processed

**Cause**: All videos already formatted with current version
**Solution**: Use `--force` to reprocess, or change formatting configuration

### Script stops after partial batch

**Cause**: Fewer videos than batch size were found, triggering early completion
**Solution**: This is normal behavior when approaching completion. Use `--until-empty` to continue until truly empty.

### Database connection errors

**Cause**: `DATABASE_URL` not set or database not accessible
**Solution**: Ensure `.env` file has correct `DATABASE_URL` or set environment variable

### Formatting errors on specific videos

**Cause**: Corrupted segments or unexpected data format
**Solution**: Check logs for specific video IDs with errors; script continues processing other videos

### JSON serialization errors

**Cause**: Configuration contains non-serializable objects
**Solution**: Ensure `formatter.config` contains only JSON-serializable types (strings, numbers, booleans, lists, dicts)

## Performance

### Batch Size Recommendations

- **Small (10-50)**: For testing or when resources are limited
- **Medium (50-100)**: Good balance for most use cases
- **Large (100-500)**: For bulk processing with adequate resources

### Processing Speed

Depends on:
- Number of segments per video
- Complexity of formatting operations enabled
- Database and disk I/O performance
- Available CPU cores (formatting is CPU-bound)

Typical rates:
- ~5-10 videos per minute with default settings
- ~100-200 segments per second

### Resource Usage

- **Memory**: Minimal (<100MB for script, more for database connections)
- **CPU**: Moderate (formatting operations are CPU-intensive)
- **Disk I/O**: Low (only reading segments and updating database)
- **Database**: One transaction per video for safety

## Safety Features

### Transaction Per Video

Each video is processed in its own database transaction, ensuring:
- Partial batches can be rolled back
- Script can be interrupted without data corruption
- Failed videos don't affect other videos in the batch

### Idempotency

Running the script multiple times on the same videos:
- Does not duplicate work
- Does not corrupt data
- Only processes videos that need updating

### Error Isolation

Errors in one video don't stop the batch:
- Error is logged with details
- Script continues to next video
- Summary includes error count

## Best Practices

1. **Always dry-run first**: Use `--dry-run` to preview changes before actual processing
2. **Start with small batches**: Test with `--batch 10` before scaling up
3. **Test on specific videos**: Use `--video-ids` to test on a few known videos first
4. **Monitor logs**: Watch for errors or unexpected behavior
5. **Use max-iterations**: Set `--max-iterations` when using `--until-empty` as a safety cap
6. **Schedule during off-peak**: Run large backfills when system load is low
7. **Check database size**: Ensure adequate disk space for cleaned text storage

## Related Documentation

- [CLEANUP_EXAMPLES.md](CLEANUP_EXAMPLES.md) - Examples of formatting transformations
- [CLEANUP_PROFILES.md](CLEANUP_PROFILES.md) - Pre-configured formatting profiles
- [CLEANUP_QUICK_REFERENCE.md](CLEANUP_QUICK_REFERENCE.md) - Quick reference for settings
- [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) - Overview of advanced features

## Migration Path

For existing deployments:

1. **Deploy code**: Update to version with backfill script
2. **Run migration**: Apply `003_transcript_cleanup` migration
3. **Dry run**: Test on a few videos with `--dry-run`
4. **Pilot**: Process a small channel or job
5. **Monitor**: Check results and performance
6. **Scale**: Gradually increase batch size
7. **Full backfill**: Process remaining videos with `--until-empty`

## Support

For issues or questions:
- Check script logs for detailed error messages
- Review this documentation
- Check GitHub issues for similar problems
- Open a new issue with logs and reproduction steps
