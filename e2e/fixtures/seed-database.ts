#!/usr/bin/env tsx
/**
 * Database seeding script for E2E tests
 * Usage: npm run seed-db
 */

import { seedTestData, cleanupTestData } from './db-seeder.js';

const command = process.argv[2] || 'seed';

async function main() {
  try {
    if (command === 'clean') {
      console.log('🧹 Cleaning test data...');
      await cleanupTestData();
      console.log('✅ Test data cleaned successfully');
    } else if (command === 'seed') {
      console.log('🌱 Seeding test data...');
      await seedTestData();
      console.log('✅ Test data seeded successfully');
    } else {
      console.error('❌ Unknown command. Use "seed" or "clean"');
      process.exit(1);
    }
  } catch (error) {
    console.error('❌ Error:', error);
    process.exit(1);
  }
}

main();
