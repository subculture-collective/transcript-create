import { useEffect, useState } from 'react';
import { http } from '../../services/api';

type DashboardMetrics = {
  jobs: {
    total: number;
    today: number;
    this_week: number;
    pending: number;
    in_progress: number;
  };
  videos: {
    total: number;
    completed: number;
    failed: number;
  };
  users: {
    total: number;
    free: number;
    pro: number;
    signups_today: number;
    signups_this_week: number;
  };
  sessions: {
    active: number;
  };
  searches: {
    today: number;
    this_week: number;
  };
  exports: {
    today: number;
    this_week: number;
  };
};

type SystemHealth = {
  database: {
    status: string;
    total_size_mb: number;
    connections: number;
  };
  workers: {
    active_jobs: number;
    avg_processing_time_seconds: number;
    error_rate_percent: number;
  };
  queue: {
    pending: number;
    oldest_pending_minutes: number;
  };
};

type ChartData = {
  labels: string[];
  data: number[];
};

type SearchAnalytics = {
  popular_terms: Array<{ term: string; count: number }>;
  zero_result_searches: number;
  avg_results_per_query: number;
  avg_query_time_ms: number;
};

function MetricCard({
  title,
  value,
  subtitle,
  trend,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: string;
}) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm text-stone-500">{title}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {subtitle && <div className="mt-1 text-xs text-stone-600">{subtitle}</div>}
      {trend && <div className="mt-1 text-xs text-green-600">{trend}</div>}
    </div>
  );
}

function SimpleBarChart({ data, labels }: { data: number[]; labels: string[] }) {
  const maxValue = Math.max(...data, 1);

  return (
    <div className="space-y-2">
      {data.map((value, idx) => {
        const percentage = (value / maxValue) * 100;
        return (
          <div key={idx} className="flex items-center gap-2">
            <div className="w-24 truncate text-sm text-stone-700" title={labels[idx]}>
              {labels[idx]}
            </div>
            <div className="flex-1">
              <div className="h-6 w-full rounded bg-stone-100">
                <div
                  className="h-full rounded bg-blue-500"
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
            <div className="w-12 text-right text-sm font-medium">{value}</div>
          </div>
        );
      })}
    </div>
  );
}

function SimplePieChart({ data, labels }: { data: number[]; labels: string[] }) {
  const total = data.reduce((sum, val) => sum + val, 0);

  return (
    <div className="space-y-1">
      {data.map((value, idx) => {
        const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
        return (
          <div key={idx} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <div
                className="h-3 w-3 rounded"
                style={{
                  backgroundColor: `hsl(${(idx * 360) / data.length}, 70%, 50%)`,
                }}
              />
              <span>{labels[idx]}</span>
            </div>
            <div className="font-medium">
              {value} ({percentage}%)
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SimpleLineChart({ data, labels }: { data: number[]; labels: string[] }) {
  const maxValue = Math.max(...data, 1);
  const chartHeight = 120;
  const chartWidth = 400;
  const padding = 10;

  const points = data
    .map((value, idx) => {
      const x = padding + (idx * (chartWidth - 2 * padding)) / (data.length - 1 || 1);
      const y = chartHeight - padding - ((value / maxValue) * (chartHeight - 2 * padding));
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <div className="overflow-x-auto">
      <svg width={chartWidth} height={chartHeight} className="border-b border-l border-stone-200">
        <polyline
          points={points}
          fill="none"
          stroke="#3b82f6"
          strokeWidth="2"
        />
        {data.map((value, idx) => {
          const x = padding + (idx * (chartWidth - 2 * padding)) / (data.length - 1 || 1);
          const y = chartHeight - padding - ((value / maxValue) * (chartHeight - 2 * padding));
          return (
            <circle
              key={idx}
              cx={x}
              cy={y}
              r="3"
              fill="#3b82f6"
            >
              <title>{labels[idx]}: {value}</title>
            </circle>
          );
        })}
      </svg>
      <div className="mt-1 flex justify-between text-xs text-stone-500">
        <span>{labels[0]}</span>
        <span>{labels[labels.length - 1]}</span>
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [jobsOverTime, setJobsOverTime] = useState<ChartData | null>(null);
  const [jobStatusBreakdown, setJobStatusBreakdown] = useState<ChartData | null>(null);
  const [exportBreakdown, setExportBreakdown] = useState<ChartData | null>(null);
  const [searchAnalytics, setSearchAnalytics] = useState<SearchAnalytics | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  async function fetchData() {
    try {
      const [metricsRes, healthRes, jobsRes, statusRes, exportRes, searchRes] = await Promise.all([
        http.get('admin/dashboard/metrics').json<DashboardMetrics>(),
        http.get('admin/dashboard/system-health').json<SystemHealth>(),
        http.get('admin/dashboard/charts/jobs-over-time?days=30').json<ChartData>(),
        http.get('admin/dashboard/charts/job-status-breakdown').json<ChartData>(),
        http.get('admin/dashboard/charts/export-format-breakdown?days=30').json<ChartData>(),
        http.get('admin/dashboard/search-analytics?days=30').json<SearchAnalytics>(),
      ]);

      setMetrics(metricsRes);
      setHealth(healthRes);
      setJobsOverTime(jobsRes);
      setJobStatusBreakdown(statusRes);
      setExportBreakdown(exportRes);
      setSearchAnalytics(searchRes);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    }
  }

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchData();
    }, 10000); // Auto-refresh every 10 seconds

    return () => clearInterval(interval);
  }, [autoRefresh]);

  if (!metrics || !health) {
    return <div className="p-6">Loading dashboard...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Admin Dashboard</h1>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (10s)
          </label>
          <button onClick={fetchData} className="btn">
            Refresh Now
          </button>
          <div className="text-xs text-stone-500">
            Last update: {lastUpdate.toLocaleTimeString()}
          </div>
        </div>
      </div>

      {/* Key Metrics */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Key Metrics</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            title="Total Jobs"
            value={metrics.jobs.total.toLocaleString()}
            subtitle={`${metrics.jobs.today} today, ${metrics.jobs.this_week} this week`}
          />
          <MetricCard
            title="Videos Transcribed"
            value={metrics.videos.completed.toLocaleString()}
            subtitle={`${metrics.videos.failed} failed`}
          />
          <MetricCard
            title="Total Users"
            value={metrics.users.total.toLocaleString()}
            subtitle={`${metrics.users.pro} pro, ${metrics.users.free} free`}
          />
          <MetricCard
            title="Active Sessions"
            value={metrics.sessions.active.toLocaleString()}
          />
          <MetricCard
            title="Searches Today"
            value={metrics.searches.today.toLocaleString()}
            subtitle={`${metrics.searches.this_week} this week`}
          />
          <MetricCard
            title="Exports Today"
            value={metrics.exports.today.toLocaleString()}
            subtitle={`${metrics.exports.this_week} this week`}
          />
          <MetricCard
            title="Queue Status"
            value={metrics.jobs.pending.toLocaleString()}
            subtitle={`${metrics.jobs.in_progress} in progress`}
          />
          <MetricCard
            title="New Signups"
            value={metrics.users.signups_today.toLocaleString()}
            subtitle={`${metrics.users.signups_this_week} this week`}
          />
        </div>
      </section>

      {/* System Health */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">System Health</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg border bg-white p-4 shadow-sm">
            <h3 className="mb-2 font-semibold">Database</h3>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span>Status:</span>
                <span
                  className={
                    health.database.status === 'healthy'
                      ? 'font-medium text-green-600'
                      : 'font-medium text-red-600'
                  }
                >
                  {health.database.status}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Size:</span>
                <span>{health.database.total_size_mb} MB</span>
              </div>
              <div className="flex justify-between">
                <span>Connections:</span>
                <span>{health.database.connections}</span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border bg-white p-4 shadow-sm">
            <h3 className="mb-2 font-semibold">Workers</h3>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span>Active Jobs:</span>
                <span>{health.workers.active_jobs}</span>
              </div>
              <div className="flex justify-between">
                <span>Avg Time:</span>
                <span>{Math.round(health.workers.avg_processing_time_seconds / 60)}m</span>
              </div>
              <div className="flex justify-between">
                <span>Error Rate:</span>
                <span
                  className={
                    health.workers.error_rate_percent > 10
                      ? 'text-red-600'
                      : health.workers.error_rate_percent > 5
                        ? 'text-yellow-600'
                        : 'text-green-600'
                  }
                >
                  {health.workers.error_rate_percent}%
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border bg-white p-4 shadow-sm">
            <h3 className="mb-2 font-semibold">Queue</h3>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span>Pending:</span>
                <span>{health.queue.pending}</span>
              </div>
              <div className="flex justify-between">
                <span>Oldest:</span>
                <span>{health.queue.oldest_pending_minutes}m ago</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Charts */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Analytics Charts</h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Jobs Over Time */}
          {jobsOverTime && jobsOverTime.data.length > 0 && (
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <h3 className="mb-3 font-semibold">Jobs Over Time (Last 30 Days)</h3>
              <SimpleLineChart data={jobsOverTime.data} labels={jobsOverTime.labels} />
            </div>
          )}

          {/* Job Status Breakdown */}
          {jobStatusBreakdown && jobStatusBreakdown.data.length > 0 && (
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <h3 className="mb-3 font-semibold">Job Status Breakdown</h3>
              <SimplePieChart
                data={jobStatusBreakdown.data}
                labels={jobStatusBreakdown.labels}
              />
            </div>
          )}

          {/* Export Format Breakdown */}
          {exportBreakdown && exportBreakdown.data.length > 0 && (
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <h3 className="mb-3 font-semibold">Export Formats (Last 30 Days)</h3>
              <SimpleBarChart data={exportBreakdown.data} labels={exportBreakdown.labels} />
            </div>
          )}

          {/* Search Analytics */}
          {searchAnalytics && (
            <div className="rounded-lg border bg-white p-4 shadow-sm">
              <h3 className="mb-3 font-semibold">Search Analytics (Last 30 Days)</h3>
              <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
                <div>
                  <div className="text-stone-500">Zero Results</div>
                  <div className="font-semibold">{searchAnalytics.zero_result_searches}</div>
                </div>
                <div>
                  <div className="text-stone-500">Avg Results</div>
                  <div className="font-semibold">{searchAnalytics.avg_results_per_query}</div>
                </div>
                <div>
                  <div className="text-stone-500">Avg Time</div>
                  <div className="font-semibold">{searchAnalytics.avg_query_time_ms}ms</div>
                </div>
              </div>
              {searchAnalytics.popular_terms.length > 0 && (
                <>
                  <h4 className="mb-2 text-sm font-medium">Popular Search Terms</h4>
                  <div className="space-y-1">
                    {searchAnalytics.popular_terms.slice(0, 10).map((term) => (
                      <div key={term.term} className="flex justify-between text-sm">
                        <span className="truncate">{term.term}</span>
                        <span className="font-medium">{term.count}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
