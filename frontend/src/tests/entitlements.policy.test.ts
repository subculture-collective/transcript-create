import { describe, expect, it } from 'vitest';
import { canExportFormat } from '../features/entitlements/policy';

describe('entitlement policy', () => {
  it('allows txt export for anonymous users', () => {
    expect(canExportFormat({ plan: null, format: 'txt' })).toBe(true);
  });

  it('allows pdf export for all users', () => {
    expect(canExportFormat({ plan: 'free', format: 'pdf' })).toBe(true);
    expect(canExportFormat({ plan: 'pro', format: 'pdf' })).toBe(true);
  });
});
