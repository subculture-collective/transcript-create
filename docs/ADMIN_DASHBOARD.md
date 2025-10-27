# Admin Analytics Dashboard

![Admin Dashboard Screenshot](https://github.com/user-attachments/assets/af0265e1-6d1a-4bd9-a0ec-948adfec886a)

## Overview

The admin analytics dashboard provides comprehensive monitoring and insights into the Transcript Create system's health, usage, and business metrics.

## Accessing the Dashboard

1. **Authentication Required**: You must be logged in as an admin user (email in `ADMIN_EMAILS` environment variable)
2. **URL**: Navigate to `/admin/dashboard` in the web interface
3. **Navigation**: Click "Dashboard" in the admin navigation menu

## Features

### Key Metrics Cards

The dashboard displays at-a-glance metrics:

- **Total Jobs**: All-time jobs, today's jobs, this week's jobs
- **Videos Transcribed**: Completed and failed video counts
- **Total Users**: Total users, pro vs free breakdown
- **Active Sessions**: Currently active user sessions
- **Searches Today**: Search queries today and this week
- **Exports Today**: Export requests today and this week
- **Queue Status**: Pending jobs and jobs in progress
- **New Signups**: User signups today and this week

### System Health

Real-time monitoring of system components:

**Database:**
- Status indicator (healthy/error)
- Total database size in MB
- Active connection count

**Workers:**
- Active transcription jobs
- Average processing time per video
- Error rate percentage (color-coded: green <5%, yellow 5-10%, red >10%)

**Queue:**
- Number of pending jobs
- Age of oldest pending job

### Analytics Charts

Visual representations of system trends:

**Jobs Over Time**
- Line chart showing job creation over the last 30 days
- Helps identify usage patterns and growth trends

**Job Status Breakdown**
- Pie chart showing distribution of job statuses
- Shows completed, pending, failed, and in-progress jobs

**Export Formats**
- Bar chart showing popular export formats (SRT, VTT, JSON, PDF)
- Based on last 30 days of export events

**Search Analytics**
- Popular search terms with usage counts
- Zero-result searches count
- Average results per query
- Average query time in milliseconds

## Auto-Refresh

The dashboard automatically refreshes every 10 seconds to show the latest data.

- **Toggle Auto-Refresh**: Use the checkbox in the header
- **Manual Refresh**: Click "Refresh Now" button
- **Last Update**: Timestamp shown in the header

## API Endpoints

The dashboard consumes these API endpoints (all require admin authentication):

- `GET /admin/dashboard/metrics` - Key metrics
- `GET /admin/dashboard/system-health` - System health data
- `GET /admin/dashboard/charts/jobs-over-time?days=30&period=daily` - Jobs time series
- `GET /admin/dashboard/charts/job-status-breakdown` - Job status distribution
- `GET /admin/dashboard/charts/export-format-breakdown?days=30` - Export formats
- `GET /admin/dashboard/search-analytics?days=30` - Search analytics

## Best Practices

1. **Monitor Error Rates**: Keep an eye on the worker error rate. Investigate if it exceeds 10%
2. **Queue Management**: If the queue has jobs pending for >1 hour, check worker health
3. **Database Size**: Monitor database growth to plan for scaling
4. **Search Performance**: High zero-result searches may indicate poor search quality
5. **User Growth**: Track signups to understand business growth

## Troubleshooting

**Dashboard won't load:**
- Ensure you're logged in as an admin user
- Check that your email is in the `ADMIN_EMAILS` environment variable
- Verify the API server is running and accessible

**Missing data in charts:**
- Some charts require event tracking to be enabled
- Ensure events are being logged to the `events` table
- Check that the database has historical data

**Slow performance:**
- The dashboard makes multiple API calls on load
- Consider increasing database connection pool if needed
- Queries are optimized but may be slow with millions of rows

## Privacy & Security

- Only admin users can access this dashboard
- All endpoints are protected by admin role requirement
- No sensitive user data is exposed (emails are not shown)
- Database connection details are not exposed

## Future Enhancements

Potential additions (not currently implemented):
- WebSocket/SSE for real-time updates
- Alerts for critical thresholds
- Billing and revenue analytics
- Error tracking integration
- User activity drill-down
- Bulk job management actions
- CSV export of all analytics
- Email reports
