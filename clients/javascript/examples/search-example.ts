/**
 * Search example
 */

import { TranscriptClient } from '../src';

async function main() {
  const query = process.argv[2];
  
  if (!query) {
    console.log('Usage: node search-example.js <search_query>');
    console.log('Example: node search-example.js "machine learning"');
    process.exit(1);
  }

  const client = new TranscriptClient({
    baseUrl: 'http://localhost:8000',
  });

  console.log(`Searching for: ${query}`);

  try {
    const results = await client.search({
      query,
      source: 'native',
      limit: 10,
    });

    console.log(`\n✓ Found ${results.total || results.hits.length} results`);
    if (results.query_time_ms) {
      console.log(`  Query time: ${results.query_time_ms}ms`);
    }

    console.log('\nTop results:');
    for (let i = 0; i < results.hits.slice(0, 10).length; i++) {
      const hit = results.hits[i];
      const startSec = hit.start_ms / 1000;
      const endSec = hit.end_ms / 1000;
      console.log(`\n${i + 1}. Video: ${hit.video_id}`);
      console.log(`   Time: ${startSec.toFixed(1)}s - ${endSec.toFixed(1)}s`);
      console.log(`   ${hit.snippet}`);
    }

    console.log('\n✓ Example completed successfully!');
  } catch (error: any) {
    console.log(`✗ Search failed: ${error.message}`);
    process.exit(1);
  }
}

main().catch(console.error);
