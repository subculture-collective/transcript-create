import { useState } from 'react';
import { Link, Outlet } from 'react-router-dom';
import { useAuth, useTheme } from '../services';

const navItems = [
  { to: '/', label: 'Home' },
  { to: '/search', label: 'Search' },
  { to: '/explore', label: 'Explore' },
  { to: '/episodes', label: 'VODs' },
  { to: '/saved', label: 'Saved' },
];

export default function AppLayout() {
  const { user, loading, login, loginTwitch, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink transition-colors">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:min-h-[44px] focus:bg-accent focus:px-4 focus:py-2 focus:text-[#101014]"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-40 border-b border-border/80 bg-canvas/85 backdrop-blur-2xl" role="banner">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 lg:px-6">
          <div className="flex items-center gap-4">
            <Link to="/" className="group flex items-center gap-3" aria-label="Home - HasAnAra">
              <img src="/icon.svg" alt="" className="h-10 w-10 rounded-lg border border-border bg-surface object-cover" />
              <span className="block text-xl font-semibold tracking-[-0.04em] text-ink group-hover:text-accent">HasAnAra</span>
            </Link>
          </div>

          <nav className="hidden items-center gap-1 lg:flex" aria-label="Main navigation">
            {navItems.map((item) => (
              <Link key={item.to} to={item.to} className="nav-link">
                {item.label}
              </Link>
            ))}
            <button
              type="button"
              onClick={toggleTheme}
              className="icon-button ml-2"
              aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              title={theme === 'light' ? 'Dark mode' : 'Light mode'}
            >
              {theme === 'light' ? (
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              ) : (
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              )}
            </button>

            <div className="ml-2 flex items-center gap-3 border-l border-border pl-4">
              {loading ? (
                <span className="text-subtle" aria-live="polite">Loading…</span>
              ) : user ? (
                <>
                  <div className="hidden items-center gap-2 lg:flex">
                    {user.avatar_url && (
                      <img src={user.avatar_url} alt={`${user.name || user.email} avatar`} className="h-8 w-8 rounded-full border border-border" />
                    )}
                    <span className="max-w-[10rem] truncate text-sm text-muted">{user.name || user.email}</span>
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
            type="button"
            className="icon-button lg:hidden"
            onClick={() => setMobileMenuOpen((current) => !current)}
            aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-menu"
          >
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        <nav
          id="mobile-menu"
          className={`border-t border-border/80 bg-canvas/95 px-4 backdrop-blur-2xl transition-all duration-300 ease-out lg:hidden ${mobileMenuOpen ? 'max-h-[36rem] opacity-100' : 'max-h-0 overflow-hidden opacity-0'}`}
          aria-label="Mobile navigation"
          aria-hidden={!mobileMenuOpen}
        >
          <div className="mx-auto flex max-w-7xl flex-col gap-2 py-4">
            <div className="archive-eyebrow mb-2 self-start">Navigation deck</div>
            {navItems.map((item) => (
              <Link key={item.to} to={item.to} className="nav-link block" onClick={() => setMobileMenuOpen(false)}>
                {item.label}
              </Link>
            ))}

            <div className="mt-3 border-t border-border pt-3">
              <button type="button" onClick={toggleTheme} className="nav-link flex w-full items-center gap-2 text-left">
                {theme === 'light' ? (
                  <>
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                    Dark mode
                  </>
                ) : (
                  <>
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                    Light mode
                  </>
                )}
              </button>

              {loading ? (
                <span className="block py-2 text-subtle" aria-live="polite">Loading…</span>
              ) : user ? (
                <>
                  <div className="flex items-center gap-3 py-2">
                    {user.avatar_url && <img src={user.avatar_url} alt={`${user.name || user.email} avatar`} className="h-8 w-8 rounded-full border border-border" />}
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
      </header>

      <main id="main-content" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6" role="main">
        <Outlet />
      </main>

      <footer className="border-t border-border/80 bg-canvas/80 backdrop-blur-xl" role="contentinfo">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between lg:px-6">
          <p>&copy; {new Date().getFullYear()} HasAnAra. A <a href="https://subcult.tv" className="action-link">Subcult</a> project.</p>
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-subtle"><a href="https://www.patreon.com/cw/subcult" className="action-link">Support Subcult on Patreon</a></p>
        </div>
      </footer>
    </div>
  );
}
