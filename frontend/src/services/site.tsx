import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { http } from './api';

export type SiteConfig = {
  schema_version?: 1;
  tagline?: string;
  operator_name?: string;
  operator_url?: string;
  project_notice?: string;
  logo_url?: string;
  favicon_url?: string;
  social_image_url?: string;
  theme?: {
    font?: 'system' | 'editorial' | 'mono' | null;
    dark?: Record<string, string>;
    light?: Record<string, string>;
  };
  name: string;
  description: string;
  creator_name: string;
  public_passages_enabled: boolean;
  clip_exports_enabled?: boolean;
  atproto_enabled?: boolean;
  community_enabled: boolean;
};
const defaults: SiteConfig = {
  name: 'Transcript Archive',
  description: 'Search the archive, share a passage, and keep its context.',
  creator_name: 'the creators',
  public_passages_enabled: true,
  community_enabled: false,
  schema_version: 1,
  tagline: 'Broadcast archive',
  operator_name: 'Archive team',
  operator_url: '',
  project_notice: 'Source recordings and trademarks belong to their respective owners.',
  logo_url: '/icon.svg',
  favicon_url: '/icon.svg',
  social_image_url: '/social-card.svg',
};
const SiteContext = createContext<SiteConfig>(defaults);

export function SiteProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState(defaults);
  useEffect(() => {
    let active = true;
    http
      .get('site')
      .json<SiteConfig>()
      .then((next) => {
        if (
          active &&
          (next.schema_version === undefined || next.schema_version === 1) &&
          typeof next.name === 'string' &&
          typeof next.creator_name === 'string' &&
          typeof next.description === 'string' &&
          typeof next.public_passages_enabled === 'boolean' &&
          typeof next.community_enabled === 'boolean'
        )
          setConfig({ ...defaults, ...next });
      })
      .catch(() => {
        // Preserve the existing archive if configuration cannot be fetched;
        // opt-in community features remain off.
      });
    return () => {
      active = false;
    };
  }, []);
  return <SiteContext.Provider value={config}>{children}</SiteContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSite() {
  return useContext(SiteContext);
}
