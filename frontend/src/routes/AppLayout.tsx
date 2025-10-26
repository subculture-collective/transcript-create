import { Link, Outlet } from 'react-router-dom';
import { useAuth, useTheme } from '../services';
import { useState } from 'react';

export default function AppLayout() {
  const { user, loading, login, loginTwitch, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950 text-stone-900 dark:text-stone-100 font-serif transition-colors">
      {/* Skip to main content link for keyboard navigation */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-blue-600 focus:text-white focus:px-4 focus:py-2 focus:m-2"
      >
        Skip to main content
      </a>

      <header className="border-b border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900" role="banner">
        <div className="mx-auto flex max-w-7xl items-center justify-between p-4">
          <Link to="/" className="font-semibold tracking-tight text-lg" aria-label="Home - Transcript Search">
            Transcript Search
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-4" aria-label="Main navigation">
            <Link to="/" className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors">
              Search
            </Link>
            <Link to="/favorites" className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors">
              Favorites
            </Link>
            <Link to="/pricing" className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors">
              Pricing
            </Link>
            
            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="p-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
              aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              title={theme === 'light' ? 'Dark mode' : 'Light mode'}
            >
              {theme === 'light' ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              )}
            </button>

            {loading ? (
              <span className="text-stone-500 dark:text-stone-500" aria-live="polite" aria-label="Loading user information">…</span>
            ) : user ? (
              <div className="flex items-center gap-3">
                {user.avatar_url && (
                  <img src={user.avatar_url} alt={`${user.name || user.email} avatar`} className="h-8 w-8 rounded-full" />
                )}
                <span className="text-stone-700 dark:text-stone-300 hidden lg:inline">{user.name || user.email}</span>
                {user.plan === 'pro' && (
                  <>
                    <span className="rounded bg-emerald-100 dark:bg-emerald-900 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300" aria-label="Pro plan member">
                      Pro
                    </span>
                    <a href="/api/billing/portal" className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors">
                      Manage billing
                    </a>
                  </>
                )}
                <button onClick={logout} className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors" aria-label="Logout">
                  Logout
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <button onClick={login} className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors" aria-label="Login with Google">
                  Login with Google
                </button>
                <span className="text-stone-400 dark:text-stone-600" aria-hidden="true">|</span>
                <button onClick={loginTwitch} className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors" aria-label="Login with Twitch">
                  Login with Twitch
                </button>
              </div>
            )}
          </nav>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden p-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-menu"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile Navigation Menu */}
        {mobileMenuOpen && (
          <nav id="mobile-menu" className="md:hidden border-t border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900" aria-label="Mobile navigation">
            <div className="px-4 py-3 space-y-3">
              <Link 
                to="/" 
                className="block py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Search
              </Link>
              <Link 
                to="/favorites" 
                className="block py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Favorites
              </Link>
              <Link 
                to="/pricing" 
                className="block py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Pricing
              </Link>
              
              {/* Mobile Theme Toggle */}
              <button
                onClick={toggleTheme}
                className="flex items-center gap-2 py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              >
                {theme === 'light' ? (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                    Dark mode
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                    Light mode
                  </>
                )}
              </button>

              {loading ? (
                <span className="block py-2 text-stone-500 dark:text-stone-500" aria-live="polite">Loading…</span>
              ) : user ? (
                <>
                  <div className="flex items-center gap-2 py-2">
                    {user.avatar_url && (
                      <img src={user.avatar_url} alt={`${user.name || user.email} avatar`} className="h-8 w-8 rounded-full" />
                    )}
                    <span className="text-stone-700 dark:text-stone-300">{user.name || user.email}</span>
                    {user.plan === 'pro' && (
                      <span className="rounded bg-emerald-100 dark:bg-emerald-900 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                        Pro
                      </span>
                    )}
                  </div>
                  {user.plan === 'pro' && (
                    <a href="/api/billing/portal" className="block py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors">
                      Manage billing
                    </a>
                  )}
                  <button 
                    onClick={() => { logout(); setMobileMenuOpen(false); }} 
                    className="block w-full text-left py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <button 
                    onClick={() => { login(); setMobileMenuOpen(false); }} 
                    className="block w-full text-left py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                  >
                    Login with Google
                  </button>
                  <button 
                    onClick={() => { loginTwitch(); setMobileMenuOpen(false); }} 
                    className="block w-full text-left py-2 text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100 transition-colors"
                  >
                    Login with Twitch
                  </button>
                </>
              )}
            </div>
          </nav>
        )}
      </header>

      <main id="main-content" className="mx-auto max-w-7xl p-4" role="main">
        <Outlet />
      </main>

      <footer className="border-t border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 mt-12" role="contentinfo">
        <div className="mx-auto max-w-7xl px-4 py-6 text-center text-sm text-stone-600 dark:text-stone-400">
          <p>&copy; {new Date().getFullYear()} Transcript Search. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
