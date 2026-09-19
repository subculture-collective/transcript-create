import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { http } from './api';

export type SiteConfig = {
  name: string;
  description: string;
  creator_name: string;
  public_passages_enabled: boolean;
  community_enabled: boolean;
};
const defaults: SiteConfig = {
  name: 'HasanAra',
  description: 'Search the archive, share a passage, and keep its context.',
  creator_name: 'HasanAbi',
  public_passages_enabled: true,
  community_enabled: false,
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
          typeof next.name === 'string' &&
          typeof next.creator_name === 'string' &&
          typeof next.description === 'string' &&
          typeof next.public_passages_enabled === 'boolean' &&
          typeof next.community_enabled === 'boolean'
        )
          setConfig(next);
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
