export type Plan = 'free' | 'pro' | 'admin' | null | undefined;
export type ExportFormat = 'txt' | 'srt' | 'vtt' | 'json' | 'pdf';

export function canExportFormat(_args: { plan: Plan; format: ExportFormat }): boolean {
  return true;
}
