/**
 * Basic usage example
 */

import { TranscriptClient } from '../src';

async function main() {
  const videoUrl = process.argv[2];
  
  if (!videoUrl) {
    console.log('Usage: node basic-usage.js <youtube_url>');
    console.log('Example: node basic-usage.js https://youtube.com/watch?v=dQw4w9WgXcQ');
    process.exit(1);
  }

  const client = new TranscriptClient({
    baseUrl: 'http://localhost:8000',
  });

  console.log(`Creating job for: ${videoUrl}`);

  // Create job
  const job = await client.createJob(videoUrl, 'single');
  console.log(`✓ Job created: ${job.id}`);
  console.log(`  State: ${job.state}`);

  // Wait for completion
  console.log('\nWaiting for transcription to complete...');
  try {
    const completedJob = await client.waitForCompletion(job.id, {
      timeout: 3600000, // 1 hour
      pollInterval: 5000, // 5 seconds
    });

    console.log(`✓ Job completed: ${completedJob.state}`);

    if (completedJob.state === 'failed') {
      console.log(`✗ Job failed: ${completedJob.error}`);
      process.exit(1);
    }

    // Get transcript
    console.log('\nFetching transcript...');
    try {
      const transcript = await client.getTranscript(job.id);
      console.log(`✓ Transcript retrieved: ${transcript.segments.length} segments`);
      
      console.log('\nFirst 5 segments:');
      for (const segment of transcript.segments.slice(0, 5)) {
        const startSec = segment.start_ms / 1000;
        const endSec = segment.end_ms / 1000;
        const speaker = segment.speaker_label ? `[${segment.speaker_label}] ` : '';
        const text = segment.text.slice(0, 80);
        console.log(`  ${startSec.toFixed(1)}s - ${endSec.toFixed(1)}s: ${speaker}${text}...`);
      }
    } catch (error: any) {
      console.log(`Note: Could not fetch transcript - ${error.message}`);
      console.log("This is expected if the video hasn't been fully processed yet.");
    }

    console.log('\nExample completed successfully!');
  } catch (error: any) {
    console.log(`✗ Error: ${error.message}`);
    process.exit(1);
  }
}

main().catch(console.error);
