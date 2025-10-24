/**
 * Test fixtures for database seeding
 */

export interface TestUser {
  id: string;
  email: string;
  name: string;
  plan: 'free' | 'pro';
  daily_search_count?: number;
  created_at?: string;
}

export interface TestJob {
  id: string;
  user_id: string;
  url: string;
  kind: 'single' | 'channel';
  state: 'pending' | 'expanded' | 'completed' | 'failed';
  created_at?: string;
}

export interface TestVideo {
  id: string;
  job_id: string;
  youtube_id: string;
  title: string;
  duration_seconds: number;
  idx: number;
  state: 'pending' | 'downloading' | 'transcoding' | 'transcribing' | 'completed' | 'failed';
  created_at?: string;
}

export interface TestTranscript {
  id: string;
  video_id: string;
  model: string;
  language: string;
  created_at?: string;
}

export interface TestSegment {
  id: string;
  transcript_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
  speaker?: string | null;
  speaker_label?: string | null;
}

/**
 * Sample test users
 */
export const testUsers: TestUser[] = [
  {
    id: '00000000-0000-0000-0000-000000000001',
    email: 'free-user@example.com',
    name: 'Free User',
    plan: 'free',
    daily_search_count: 0,
  },
  {
    id: '00000000-0000-0000-0000-000000000002',
    email: 'pro-user@example.com',
    name: 'Pro User',
    plan: 'pro',
    daily_search_count: 0,
  },
  {
    id: '00000000-0000-0000-0000-000000000003',
    email: 'quota-reached-user@example.com',
    name: 'Quota Reached User',
    plan: 'free',
    daily_search_count: 5, // Free tier limit
  },
];

/**
 * Sample test jobs
 */
export const testJobs: TestJob[] = [
  {
    id: '00000000-0000-0000-0000-000000000101',
    user_id: '00000000-0000-0000-0000-000000000001',
    url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    kind: 'single',
    state: 'completed',
  },
  {
    id: '00000000-0000-0000-0000-000000000102',
    user_id: '00000000-0000-0000-0000-000000000002',
    url: 'https://www.youtube.com/watch?v=jNQXAC9IVRw',
    kind: 'single',
    state: 'completed',
  },
];

/**
 * Sample test videos
 */
export const testVideos: TestVideo[] = [
  {
    id: '00000000-0000-0000-0000-000000000201',
    job_id: '00000000-0000-0000-0000-000000000101',
    youtube_id: 'dQw4w9WgXcQ',
    title: 'Rick Astley - Never Gonna Give You Up',
    duration_seconds: 212,
    idx: 0,
    state: 'completed',
  },
  {
    id: '00000000-0000-0000-0000-000000000202',
    job_id: '00000000-0000-0000-0000-000000000102',
    youtube_id: 'jNQXAC9IVRw',
    title: 'Me at the zoo',
    duration_seconds: 19,
    idx: 0,
    state: 'completed',
  },
];

/**
 * Sample test transcripts
 */
export const testTranscripts: TestTranscript[] = [
  {
    id: '00000000-0000-0000-0000-000000000301',
    video_id: '00000000-0000-0000-0000-000000000201',
    model: 'base',
    language: 'en',
  },
  {
    id: '00000000-0000-0000-0000-000000000302',
    video_id: '00000000-0000-0000-0000-000000000202',
    model: 'base',
    language: 'en',
  },
];

/**
 * Sample test segments
 */
export const testSegments: TestSegment[] = [
  {
    id: '00000000-0000-0000-0000-000000000401',
    transcript_id: '00000000-0000-0000-0000-000000000301',
    start_ms: 0,
    end_ms: 5000,
    text: "We're no strangers to love",
    speaker: null,
    speaker_label: null,
  },
  {
    id: '00000000-0000-0000-0000-000000000402',
    transcript_id: '00000000-0000-0000-0000-000000000301',
    start_ms: 5000,
    end_ms: 10000,
    text: 'You know the rules and so do I',
    speaker: null,
    speaker_label: null,
  },
  {
    id: '00000000-0000-0000-0000-000000000403',
    transcript_id: '00000000-0000-0000-0000-000000000302',
    start_ms: 0,
    end_ms: 3000,
    text: 'All right, so here we are in front of the elephants',
    speaker: null,
    speaker_label: null,
  },
  {
    id: '00000000-0000-0000-0000-000000000404',
    transcript_id: '00000000-0000-0000-0000-000000000302',
    start_ms: 3000,
    end_ms: 6000,
    text: 'The cool thing about these guys is that they have really, really, really long trunks',
    speaker: null,
    speaker_label: null,
  },
];
