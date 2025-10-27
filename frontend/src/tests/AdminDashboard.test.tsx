import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import AdminDashboard from '../routes/admin/AdminDashboard';

// Mock the http service
vi.mock('../services/api', () => ({
  http: {
    get: vi.fn(),
  },
}));

import { http } from '../services/api';

describe('AdminDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    // Mock the API responses with promises that don't resolve immediately
    vi.mocked(http.get).mockReturnValue({
      json: () => new Promise(() => {}), // Never resolves
    } as any);

    render(
      <BrowserRouter>
        <AdminDashboard />
      </BrowserRouter>
    );

    expect(screen.getByText('Loading dashboard...')).toBeInTheDocument();
  });

  it('fetches and displays dashboard data', async () => {
    // Mock successful API responses
    const mockMetrics = {
      jobs: { total: 100, today: 5, this_week: 25, pending: 3, in_progress: 1 },
      videos: { total: 200, completed: 190, failed: 10 },
      users: { total: 50, free: 45, pro: 5, signups_today: 2, signups_this_week: 10 },
      sessions: { active: 15 },
      searches: { today: 30, this_week: 150 },
      exports: { today: 10, this_week: 60 },
    };

    const mockHealth = {
      database: { status: 'healthy', total_size_mb: 1024, connections: 12 },
      workers: { active_jobs: 1, avg_processing_time_seconds: 245, error_rate_percent: 2.5 },
      queue: { pending: 3, oldest_pending_minutes: 15 },
    };

    const mockJobsOverTime = {
      labels: ['2025-10-20', '2025-10-21', '2025-10-22'],
      data: [15, 23, 18],
    };

    const mockJobStatusBreakdown = {
      labels: ['completed', 'pending', 'failed'],
      data: [190, 3, 10],
    };

    const mockExportBreakdown = {
      labels: ['srt', 'vtt', 'json', 'pdf'],
      data: [25, 20, 10, 5],
    };

    const mockSearchAnalytics = {
      popular_terms: [
        { term: 'python tutorial', count: 45 },
        { term: 'react hooks', count: 32 },
      ],
      zero_result_searches: 12,
      avg_results_per_query: 8.5,
      avg_query_time_ms: 145,
    };

    // Mock http.get to return different responses based on the URL
    vi.mocked(http.get).mockImplementation((url: string) => {
      let response: any;
      if (url === 'admin/dashboard/metrics') {
        response = mockMetrics;
      } else if (url === 'admin/dashboard/system-health') {
        response = mockHealth;
      } else if (url.includes('jobs-over-time')) {
        response = mockJobsOverTime;
      } else if (url.includes('job-status-breakdown')) {
        response = mockJobStatusBreakdown;
      } else if (url.includes('export-format-breakdown')) {
        response = mockExportBreakdown;
      } else if (url.includes('search-analytics')) {
        response = mockSearchAnalytics;
      }
      return {
        json: () => Promise.resolve(response),
      } as any;
    });

    render(
      <BrowserRouter>
        <AdminDashboard />
      </BrowserRouter>
    );

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Admin Dashboard')).toBeInTheDocument();
    });

    // Check that key metrics are displayed
    await waitFor(() => {
      expect(screen.getByText('Total Jobs')).toBeInTheDocument();
      expect(screen.getByText('100')).toBeInTheDocument();
      expect(screen.getByText('Videos Transcribed')).toBeInTheDocument();
      expect(screen.getByText('190')).toBeInTheDocument();
    });

    // Check system health section
    expect(screen.getByText('System Health')).toBeInTheDocument();
    expect(screen.getByText('Database')).toBeInTheDocument();
    expect(screen.getByText('healthy')).toBeInTheDocument();

    // Check that refresh button exists
    expect(screen.getByText('Refresh Now')).toBeInTheDocument();
  });

  it('handles API errors gracefully', async () => {
    // Mock API to reject
    vi.mocked(http.get).mockReturnValue({
      json: () => Promise.reject(new Error('API Error')),
    } as any);

    // Suppress console.error for this test
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <AdminDashboard />
      </BrowserRouter>
    );

    // Should show loading state and then stay there (no crash)
    expect(screen.getByText('Loading dashboard...')).toBeInTheDocument();

    // Wait a bit to ensure it doesn't crash
    await waitFor(
      () => {
        expect(consoleErrorSpy).toHaveBeenCalled();
      },
      { timeout: 2000 }
    );

    consoleErrorSpy.mockRestore();
  });
});
