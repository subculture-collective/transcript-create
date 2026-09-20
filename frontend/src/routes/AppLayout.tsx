import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigationType } from 'react-router-dom';
import { useSite } from '../services/site';
import { useAuth, useTheme } from '../services';

const baseNavItems = [
  { to: '/', label: 'Home' },
  { to: '/search', label: 'Search' },
  { to: '/explore', label: 'Explore' },
  { to: '/timeline', label: 'Timeline' },
  { to: '/episodes', label: 'VODs' },
  { to: '/saved', label: 'Saved' },
  { to: '/support', label: 'Support' },
];

const routeMeta: Array<{ match: RegExp; title: string; description: string }> = [
  {
    match: /^\/$/,
    title: '{name} — Broadcast archive',
    description: 'Search and watch the public {creator} broadcast archive.',
  },
  {
    match: /^\/search/,
    title: 'Search transcripts — {name}',
    description: 'Find timestamped, citation-backed moments across the archive.',
  },
  {
    match: /^\/explore/,
    title: 'Explore topics — {name}',
    description: 'Explore public archive topics, periods, and evidence.',
  },
  {
    match: /^\/(episodes|streams)/,
    title: 'Watch the archive — {name}',
    description: 'Browse the latest VODs, topics, and cited transcript moments.',
  },
  {
    match: /^\/timeline/,
    title: 'Archive timeline — {name}',
    description: 'Browse broadcasts chronologically.',
  },
  {
    match: /^\/topics\//,
    title: 'Topic evidence — {name}',
    description: 'Review a topic through timestamped transcript evidence.',
  },
  {
    match: /^\/v\//,
    title: 'Episode transcript — {name}',
    description: 'Watch a source VOD with its interactive transcript.',
  },
  {
    match: /^\/saved/,
    title: 'Saved moments — {name}',
    description: 'Return to saved searches and transcript moments.',
  },
  {
    match: /^\/account/,
    title: 'Account — {name}',
    description: 'Manage your {name} account.',
  },
  {
    match: /^\/support/,
    title: 'Support the archive — {name}',
    description: 'Help keep {name} public, searchable, and independently maintained.',
  },
  {
    match: /^\/about/,
    title: 'About the archive — {name}',
    description: 'How {name} turns public broadcasts into a searchable, cited record.',
  },
  {
    match: /^\/(privacy|terms)/,
    title: 'Project policies — {name}',
    description: 'Privacy and terms for the {name} public archive.',
  },
  {
    match: /^\/admin/,
    title: 'Archive administration — {name}',
    description: 'Operate the {name} archive.',
  },
];

function RouteTransitionManager() {
  const site = useSite();
  const location = useLocation();
  const navigationType = useNavigationType();
  const previousPath = useRef(location.pathname);
  const positions = useRef(new Map<string, number>());
  const [announcement, setAnnouncement] = useState('');

  useEffect(() => {
    const meta = routeMeta.find((item) => item.match.test(location.pathname)) ?? {
      title: '{name}',
      description: 'Public broadcast archive.',
    };
    document.title = meta.title.replaceAll('{name}', site.name);
    let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!description) {
      description = document.createElement('meta');
      description.name = 'description';
      document.head.appendChild(description);
    }
    description.content =
      location.pathname === '/'
        ? site.description
        : meta.description
            .replaceAll('{name}', site.name)
            .replaceAll('{creator}', site.creator_name);

    for (const link of document.querySelectorAll<HTMLLinkElement>('link[rel="icon"]')) {
      link.href = site.favicon_url || '/icon.svg';
      link.removeAttribute('type');
    }
    const social = document.querySelector<HTMLMetaElement>('meta[property="og:image"]');
    if (social) social.content = site.social_image_url || '/social-card.svg';

    const pathChanged = previousPath.current !== location.pathname;
    if (!pathChanged) return;
    positions.current.set(previousPath.current, window.scrollY);
    previousPath.current = location.pathname;
    window.requestAnimationFrame(() => {
      if (navigationType === 'POP') {
        window.scrollTo({ top: positions.current.get(location.pathname) ?? 0 });
      } else {
        window.scrollTo({ top: 0 });
        const target = document.querySelector<HTMLElement>('main h1');
        const active = document.activeElement;
        const userMovedFocus =
          active instanceof HTMLElement &&
          active !== document.body &&
          active !== document.documentElement;
        if (target && !userMovedFocus) {
          target.tabIndex = -1;
          target.focus({ preventScroll: true });
        }
      }
      setAnnouncement(meta.title.replace(' — {name}', '').replaceAll('{name}', site.name));
    });
  }, [location.pathname, navigationType, site]);

  return (
    <span className="sr-only" aria-live="polite">
      {announcement}
    </span>
  );
}

export default function AppLayout() {
  const site = useSite();
  const navItems = site.community_enabled
    ? [...baseNavItems, { to: '/community', label: 'Community' }]
    : baseNavItems;
  const { user, loading, error: authError, login, loginTwitch, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const location = useLocation();

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [mobileMenuOpen]);

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink transition-colors">
      <RouteTransitionManager />
      <a
        href="#main-content"
        onClick={() =>
          window.requestAnimationFrame(() => document.getElementById('main-content')?.focus())
        }
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:min-h-[44px] focus:bg-accent focus:px-4 focus:py-2 focus:text-accent-contrast"
      >
        Skip to main content
      </a>

      <header
        className="sticky top-0 z-40 border-b border-border/80 bg-canvas/85 backdrop-blur-2xl"
        role="banner"
      >
        <div className="mx-auto flex max-w-[100rem] items-center justify-between gap-4 px-4 py-3 lg:px-6">
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="group flex items-center gap-3"
              aria-label={`Home - ${site.name}`}
            >
              <img
                src={site.logo_url || '/icon.svg'}
                alt=""
                width="40"
                height="40"
                className="h-10 w-10 rounded-lg border border-border bg-surface object-cover"
              />
              <span>
                <span className="block text-xl font-semibold leading-none tracking-[-0.04em] text-ink group-hover:text-accent">
                  {site.name}
                </span>
                <span className="mt-1 hidden text-[8px] font-bold uppercase tracking-[0.24em] text-subtle sm:block">
                  {site.tagline || 'Broadcast archive'}
                </span>
              </span>
            </Link>
          </div>

          <nav className="hidden items-center gap-1 lg:flex" aria-label="Main navigation">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `nav-link ${isActive ? 'bg-surface-muted text-ink' : ''}`
                }
              >
                {item.label}
              </NavLink>
            ))}
            {user && (
              <NavLink
                to="/account"
                className={({ isActive }) =>
                  `nav-link ${isActive ? 'bg-surface-muted text-ink' : ''}`
                }
              >
                Account
              </NavLink>
            )}
            <button
              type="button"
              onClick={toggleTheme}
              className="icon-button ml-2"
              aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              title={theme === 'light' ? 'Dark mode' : 'Light mode'}
            >
              {theme === 'light' ? (
                <svg
                  className="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                  />
                </svg>
              ) : (
                <svg
                  className="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                  />
                </svg>
              )}
            </button>

            <div className="ml-2 flex items-center gap-3 border-l border-border pl-4">
              {loading ? (
                <span className="text-subtle" aria-live="polite">
                  Loading…
                </span>
              ) : user ? (
                <>
                  <div className="hidden items-center gap-2 lg:flex">
                    {user.avatar_url && (
                      <img
                        src={user.avatar_url}
                        alt={`${user.name || user.email} avatar`}
                        width="32"
                        height="32"
                        className="h-8 w-8 rounded-full border border-border"
                      />
                    )}
                    <span className="max-w-[10rem] truncate text-sm text-muted">
                      {user.name || user.email}
                    </span>
                  </div>
                  <button type="button" onClick={logout} className="nav-link">
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <button type="button" onClick={login} className="nav-link">
                    Google
                  </button>
                  <button type="button" onClick={loginTwitch} className="nav-link">
                    Twitch
                  </button>
                </>
              )}
            </div>
          </nav>

          <button
            ref={menuButtonRef}
            type="button"
            className="icon-button lg:hidden"
            onClick={() => setMobileMenuOpen((current) => !current)}
            aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-menu"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              {mobileMenuOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
        </div>

        {mobileMenuOpen && (
          <nav
            id="mobile-menu"
            className="border-t border-border/80 bg-canvas/95 px-4 backdrop-blur-2xl lg:hidden"
            aria-label="Mobile navigation"
          >
            <div className="mx-auto flex max-w-[100rem] flex-col gap-2 py-4">
              <div className="archive-eyebrow mb-2 self-start">Navigation deck</div>
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `nav-link block ${isActive ? 'bg-surface-muted text-ink' : ''}`
                  }
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.label}
                </NavLink>
              ))}
              {user && (
                <NavLink
                  to="/account"
                  className={({ isActive }) =>
                    `nav-link block ${isActive ? 'bg-surface-muted text-ink' : ''}`
                  }
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Account
                </NavLink>
              )}

              <div className="mt-3 border-t border-border pt-3">
                <button
                  type="button"
                  onClick={toggleTheme}
                  className="nav-link flex w-full items-center gap-2 text-left"
                >
                  {theme === 'light' ? (
                    <>
                      <svg
                        className="h-5 w-5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                        />
                      </svg>
                      Dark mode
                    </>
                  ) : (
                    <>
                      <svg
                        className="h-5 w-5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                        />
                      </svg>
                      Light mode
                    </>
                  )}
                </button>

                {loading ? (
                  <span className="block py-2 text-subtle" aria-live="polite">
                    Loading…
                  </span>
                ) : user ? (
                  <>
                    <div className="flex items-center gap-3 py-2">
                      {user.avatar_url && (
                        <img
                          src={user.avatar_url}
                          alt={`${user.name || user.email} avatar`}
                          width="32"
                          height="32"
                          className="h-8 w-8 rounded-full border border-border"
                        />
                      )}
                      <span className="text-muted">{user.name || user.email}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        logout();
                        setMobileMenuOpen(false);
                      }}
                      className="nav-link block w-full text-left"
                    >
                      Logout
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        login();
                        setMobileMenuOpen(false);
                      }}
                      className="nav-link block w-full text-left"
                    >
                      Google
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        loginTwitch();
                        setMobileMenuOpen(false);
                      }}
                      className="nav-link block w-full text-left"
                    >
                      Twitch
                    </button>
                  </>
                )}
              </div>
            </div>
          </nav>
        )}
        {authError && (
          <div
            className="border-t border-warning/30 bg-warning-soft px-4 py-2 text-center text-sm text-warning"
            role="alert"
          >
            {authError}
          </div>
        )}
      </header>

      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto min-h-[calc(100vh-3.5rem)] w-full max-w-[100rem] flex-1 px-4 py-6 lg:px-6 lg:py-8"
        role="main"
      >
        <Outlet />
      </main>

      <footer
        className="border-t border-border/80 bg-canvas/80 backdrop-blur-xl"
        role="contentinfo"
      >
        <div className="mx-auto grid max-w-[100rem] gap-5 px-4 py-7 text-sm text-muted sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center lg:px-6">
          <p>
            &copy; {new Date().getFullYear()} {site.name}.{' '}
            {site.operator_url ? (
              <a href={site.operator_url} className="action-link underline underline-offset-2">
                {site.operator_name}
              </a>
            ) : (
              site.operator_name
            )}
          </p>
          <nav
            aria-label="Project and legal"
            className="flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-[0.18em] text-subtle sm:justify-end"
          >
            <Link to="/about" className="action-link">
              About
            </Link>
            <Link to="/privacy" className="action-link">
              Privacy
            </Link>
            <Link to="/terms" className="action-link">
              Terms
            </Link>
            <Link to="/support" className="action-link text-accent">
              Support
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
