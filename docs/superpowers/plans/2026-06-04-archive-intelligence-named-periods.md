# Archive Intelligence Named Periods Follow-Up

Goal: add curated and computed time periods alongside calendar months/weeks on `/explore`.

## Period Types

- **Calendar:** existing month/week buckets.
- **Event windows:** curated ranges such as `Election 2024`, `October 7`, major debates, protests, court decisions.
- **Specific dates:** recurring or one-off dates such as `9/11`, `8/21`, birthdays, anniversaries, holidays.
- **Campaign/story arcs:** multi-week spans like primaries, general election, Gaza escalation windows, labor strike windows.

## Proposed Tables

- `archive_named_periods`: `slug`, `label`, `kind`, `date_from`, `date_to`, `description`, `status`, `sort_order`.
- `archive_named_period_stats`: `named_period_id`, `video_count`, `duration`, `top_topics`, `evidence`, `summary`, `calculated_at`.

## Explore UX

- Add a Timeline mode toggle: `Calendar` / `Events` / `Dates`.
- Event cards should use the same citation rules as topic cards: visible evidence must contain the displayed topic or event term.
- Event windows are editable by admins; public users only see published named periods.

## Initial Seeds

- `Election 2024`: 2024-01-01 to 2024-11-06.
- `October 7`: annual date window around 10-07.
- `9/11`: annual date window around 09-11.
- `8/21`: annual date window around 08-21.
- Later: add Hasan/community-specific recurring dates once verified.
