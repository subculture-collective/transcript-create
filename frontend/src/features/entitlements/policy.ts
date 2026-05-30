export type Plan = 'free' | 'pro' | 'admin' | null | undefined;
export type ExportFormat = 'txt' | 'srt' | 'vtt' | 'json' | 'pdf';

const PRO_EXPORT_FORMATS = new Set<ExportFormat>(['pdf']);

export function canExportFormat({ plan, format }: { plan: Plan; format: ExportFormat }): boolean {
  if (!PRO_EXPORT_FORMATS.has(format)) return true;
  return plan === 'pro' || plan === 'admin';
}
