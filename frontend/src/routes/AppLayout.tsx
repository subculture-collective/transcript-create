import { Link, Outlet } from 'react-router-dom';
import { useAuth } from '../services';
import { useState } from 'react';

export default function AppLayout() {
  const { user, loading, login, loginTwitch, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 font-serif">
      {/* Skip to main content link for keyboard navigation */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-blue-600 focus:text-white focus:px-4 focus:py-2 focus:m-2"
      >
        Skip to main content
      </a>

      <header className="border-b bg-white" role="banner">
        <div className="mx-auto flex max-w-7xl items-center justify-between p-4">
          <Link to="/" className="font-semibold tracking-tight text-lg" aria-label="Home - Transcript Search">
            Transcript Search
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-4" aria-label="Main navigation">
            <Link to="/" className="text-stone-600 hover:text-stone-900 transition-colors">
              Search
            </Link>
            <Link to="/favorites" className="text-stone-600 hover:text-stone-900 transition-colors">
              Favorites
            </Link>
            <Link to="/pricing" className="text-stone-600 hover:text-stone-900 transition-colors">
              Pricing
            </Link>
            {loading ? (
              <span className="text-stone-500" aria-live="polite" aria-label="Loading user information">…</span>
            ) : user ? (
              <div className="flex items-center gap-3">
                {user.avatar_url && (
                  <img src={user.avatar_url} alt={`${user.name || user.email} avatar`} className="h-8 w-8 rounded-full" />
                )}
                <span className="text-stone-700 hidden lg:inline">{user.name || user.email}</span>
                {user.plan === 'pro' && (
                  <>
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700" aria-label="Pro plan member">
                      Pro
                    </span>
                    <a href="/api/billing/portal" className="text-stone-600 hover:text-stone-900 transition-colors">
                      Manage billing
                    </a>
                  </>
                )}
                <button onClick={logout} className="text-stone-600 hover:text-stone-900 transition-colors" aria-label="Logout">
                  Logout
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <button onClick={login} className="text-stone-600 hover:text-stone-900 transition-colors" aria-label="Login with Google">
                  Login with Google
                </button>
                <span className="text-stone-400" aria-hidden="true">|</span>
                <button onClick={loginTwitch} className="text-stone-600 hover:text-stone-900 transition-colors" aria-label="Login with Twitch">
                  Login with Twitch
                </button>
              </div>
            )}
          </nav>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden p-2 text-stone-600 hover:text-stone-900"
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
          <nav id="mobile-menu" className="md:hidden border-t bg-white" aria-label="Mobile navigation">
            <div className="px-4 py-3 space-y-3">
              <Link 
                to="/" 
                className="block py-2 text-stone-600 hover:text-stone-900 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Search
              </Link>
              <Link 
                to="/favorites" 
                className="block py-2 text-stone-600 hover:text-stone-900 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Favorites
              </Link>
              <Link 
                to="/pricing" 
                className="block py-2 text-stone-600 hover:text-stone-900 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Pricing
              </Link>
              {loading ? (
                <span className="block py-2 text-stone-500" aria-live="polite">Loading…</span>
              ) : user ? (
                <>
                  <div className="flex items-center gap-2 py-2">
                    {user.avatar_url && (
                      <img src={user.avatar_url} alt={`${user.name || user.email} avatar`} className="h-8 w-8 rounded-full" />
                    )}
                    <span className="text-stone-700">{user.name || user.email}</span>
                    {user.plan === 'pro' && (
                      <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                        Pro
                      </span>
                    )}
                  </div>
                  {user.plan === 'pro' && (
                    <a href="/api/billing/portal" className="block py-2 text-stone-600 hover:text-stone-900 transition-colors">
                      Manage billing
                    </a>
                  )}
                  <button 
                    onClick={() => { logout(); setMobileMenuOpen(false); }} 
                    className="block w-full text-left py-2 text-stone-600 hover:text-stone-900 transition-colors"
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <button 
                    onClick={() => { login(); setMobileMenuOpen(false); }} 
                    className="block w-full text-left py-2 text-stone-600 hover:text-stone-900 transition-colors"
                  >
                    Login with Google
                  </button>
                  <button 
                    onClick={() => { loginTwitch(); setMobileMenuOpen(false); }} 
                    className="block w-full text-left py-2 text-stone-600 hover:text-stone-900 transition-colors"
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

      <footer className="border-t bg-white mt-12" role="contentinfo">
        <div className="mx-auto max-w-7xl px-4 py-6 text-center text-sm text-stone-600">
          <p>&copy; {new Date().getFullYear()} Transcript Search. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
