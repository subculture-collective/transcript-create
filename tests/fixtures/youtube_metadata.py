"""Sample YouTube video metadata for testing."""

SAMPLE_VIDEO_METADATA = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
    "duration": 212,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "description": "Rick Astley's official music video for Never Gonna Give You Up",
    "uploader": "Rick Astley",
    "uploader_id": "RickAstleyYT",
    "upload_date": "20091024",
    "view_count": 1000000,
}

SAMPLE_CHANNEL_METADATA = {
    "id": "UC38IQsAvIsxxjztdMZQtwHA",
    "title": "Rick Astley",
    "description": "Official Rick Astley YouTube Channel",
    "entries": [
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "duration": 212,
        },
        {
            "id": "yPYZpwSpKmA",
            "title": "Together Forever",
            "duration": 201,
        },
        {
            "id": "AC3Ejf7vPEY",
            "title": "Whenever You Need Somebody",
            "duration": 234,
        },
    ],
}

SAMPLE_SHORT_VIDEO = {
    "id": "short123",
    "title": "Short Test Video",
    "duration": 60,
}

SAMPLE_LONG_VIDEO = {
    "id": "long456",
    "title": "Long Test Video (1 hour)",
    "duration": 3600,
}

# Mock yt-dlp JSON output for single video
YT_DLP_SINGLE_VIDEO_JSON = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
    "duration": 212,
    "ext": "mp4",
    "format": "best",
    "formats": [
        {
            "format_id": "140",
            "ext": "m4a",
            "acodec": "mp4a.40.2",
        }
    ],
}

# Mock yt-dlp JSON output for channel (flat playlist)
YT_DLP_CHANNEL_JSON = {
    "_type": "playlist",
    "id": "UC38IQsAvIsxxjztdMZQtwHA",
    "title": "Rick Astley - Videos",
    "entries": [
        {"id": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up", "duration": 212},
        {"id": "yPYZpwSpKmA", "title": "Together Forever", "duration": 201},
        {"id": "AC3Ejf7vPEY", "title": "Whenever You Need Somebody", "duration": 234},
    ],
}
