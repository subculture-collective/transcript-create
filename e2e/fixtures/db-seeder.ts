import { Pool } from 'pg';
import {
  testUsers,
  testJobs,
  testVideos,
  testTranscripts,
  testSegments,
  type TestUser,
  type TestJob,
  type TestVideo,
  type TestTranscript,
  type TestSegment,
} from './test-data';

/**
 * Database seeding utility for E2E tests
 */
export class DatabaseSeeder {
  private pool: Pool;

  constructor(connectionString: string) {
    this.pool = new Pool({ connectionString });
  }

  async connect() {
    try {
      await this.pool.query('SELECT 1');
      console.log('✅ Database connection successful');
    } catch (error) {
      console.error('❌ Database connection failed:', error);
      throw error;
    }
  }

  async cleanup() {
    console.log('🧹 Cleaning up test data...');
    await this.pool.query('DELETE FROM segments WHERE transcript_id IN (SELECT id FROM transcripts WHERE video_id IN (SELECT id FROM videos WHERE job_id IN (SELECT id FROM jobs WHERE user_id LIKE \'00000000-0000-0000-0000-%\')))');
    await this.pool.query('DELETE FROM transcripts WHERE video_id IN (SELECT id FROM videos WHERE job_id IN (SELECT id FROM jobs WHERE user_id LIKE \'00000000-0000-0000-0000-%\'))');
    await this.pool.query('DELETE FROM videos WHERE job_id IN (SELECT id FROM jobs WHERE user_id LIKE \'00000000-0000-0000-0000-%\')');
    await this.pool.query('DELETE FROM jobs WHERE user_id LIKE \'00000000-0000-0000-0000-%\'');
    await this.pool.query('DELETE FROM users WHERE id LIKE \'00000000-0000-0000-0000-%\'');
    console.log('✅ Test data cleaned up');
  }

  async seedUsers(users: TestUser[] = testUsers) {
    console.log(`📝 Seeding ${users.length} test users...`);
    for (const user of users) {
      await this.pool.query(
        `INSERT INTO users (id, email, name, plan, daily_search_count, created_at)
         VALUES ($1, $2, $3, $4, $5, COALESCE($6::timestamptz, NOW()))
         ON CONFLICT (id) DO UPDATE
         SET email = EXCLUDED.email,
             name = EXCLUDED.name,
             plan = EXCLUDED.plan,
             daily_search_count = EXCLUDED.daily_search_count`,
        [user.id, user.email, user.name, user.plan, user.daily_search_count || 0, user.created_at]
      );
    }
    console.log('✅ Test users seeded');
  }

  async seedJobs(jobs: TestJob[] = testJobs) {
    console.log(`📝 Seeding ${jobs.length} test jobs...`);
    for (const job of jobs) {
      await this.pool.query(
        `INSERT INTO jobs (id, user_id, url, kind, state, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5::job_state, COALESCE($6::timestamptz, NOW()), NOW())
         ON CONFLICT (id) DO UPDATE
         SET url = EXCLUDED.url,
             kind = EXCLUDED.kind,
             state = EXCLUDED.state`,
        [job.id, job.user_id, job.url, job.kind, job.state, job.created_at]
      );
    }
    console.log('✅ Test jobs seeded');
  }

  async seedVideos(videos: TestVideo[] = testVideos) {
    console.log(`📝 Seeding ${videos.length} test videos...`);
    for (const video of videos) {
      await this.pool.query(
        `INSERT INTO videos (id, job_id, youtube_id, title, duration_seconds, idx, state, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7::video_state, COALESCE($8::timestamptz, NOW()), NOW())
         ON CONFLICT (id) DO UPDATE
         SET youtube_id = EXCLUDED.youtube_id,
             title = EXCLUDED.title,
             duration_seconds = EXCLUDED.duration_seconds,
             state = EXCLUDED.state`,
        [video.id, video.job_id, video.youtube_id, video.title, video.duration_seconds, video.idx, video.state, video.created_at]
      );
    }
    console.log('✅ Test videos seeded');
  }

  async seedTranscripts(transcripts: TestTranscript[] = testTranscripts) {
    console.log(`📝 Seeding ${transcripts.length} test transcripts...`);
    for (const transcript of transcripts) {
      await this.pool.query(
        `INSERT INTO transcripts (id, video_id, model, language, created_at)
         VALUES ($1, $2, $3, $4, COALESCE($5::timestamptz, NOW()))
         ON CONFLICT (id) DO UPDATE
         SET model = EXCLUDED.model,
             language = EXCLUDED.language`,
        [transcript.id, transcript.video_id, transcript.model, transcript.language, transcript.created_at]
      );
    }
    console.log('✅ Test transcripts seeded');
  }

  async seedSegments(segments: TestSegment[] = testSegments) {
    console.log(`📝 Seeding ${segments.length} test segments...`);
    for (const segment of segments) {
      await this.pool.query(
        `INSERT INTO segments (id, transcript_id, start_ms, end_ms, text, speaker, speaker_label)
         VALUES ($1, $2, $3, $4, $5, $6, $7)
         ON CONFLICT (id) DO UPDATE
         SET start_ms = EXCLUDED.start_ms,
             end_ms = EXCLUDED.end_ms,
             text = EXCLUDED.text,
             speaker = EXCLUDED.speaker,
             speaker_label = EXCLUDED.speaker_label`,
        [segment.id, segment.transcript_id, segment.start_ms, segment.end_ms, segment.text, segment.speaker, segment.speaker_label]
      );
    }
    console.log('✅ Test segments seeded');
  }

  async seedAll() {
    console.log('🌱 Seeding all test data...');
    await this.cleanup();
    await this.seedUsers();
    await this.seedJobs();
    await this.seedVideos();
    await this.seedTranscripts();
    await this.seedSegments();
    console.log('✅ All test data seeded successfully');
  }

  async close() {
    await this.pool.end();
  }
}

/**
 * Helper function to seed test data before E2E tests
 */
export async function seedTestData(connectionString?: string) {
  const dbUrl = connectionString || process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5434/transcripts';
  const seeder = new DatabaseSeeder(dbUrl);
  
  try {
    await seeder.connect();
    await seeder.seedAll();
  } finally {
    await seeder.close();
  }
}

/**
 * Helper function to cleanup test data after E2E tests
 */
export async function cleanupTestData(connectionString?: string) {
  const dbUrl = connectionString || process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5434/transcripts';
  const seeder = new DatabaseSeeder(dbUrl);
  
  try {
    await seeder.connect();
    await seeder.cleanup();
  } finally {
    await seeder.close();
  }
}
