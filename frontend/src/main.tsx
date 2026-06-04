import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import AppLayout from './routes/AppLayout';
import HomePage from './routes/HomePage';
import SearchPage from './routes/SearchPage';
import StreamsPage from './routes/StreamsPage';
import VideoPage from './routes/VideoPage';
import LoginPage from './routes/LoginPage';
import FavoritesPage from './routes/FavoritesPage';
import Protected from './routes/Protected';
import AdminLayout from './routes/admin/AdminLayout';
import AdminDashboard from './routes/admin/AdminDashboard';
import AdminEvents from './routes/admin/AdminEvents';
import AdminUsers from './routes/admin/AdminUsers';
import { AuthProvider, ThemeProvider } from './services';
import TopicPage from './routes/TopicPage';
import TimelinePage from './routes/TimelinePage';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'episodes', element: <StreamsPage /> },
      { path: 'streams', element: <StreamsPage /> },
      { path: 'timeline', element: <TimelinePage /> },
      { path: 'topics/:query', element: <TopicPage /> },
      { path: 'v/:videoId', element: <VideoPage /> },
      { path: 'login', element: <LoginPage /> },
      {
        path: 'saved',
        element: (
          <Protected>
            <FavoritesPage />
          </Protected>
        ),
      },
      {
        path: 'favorites',
        element: (
          <Protected>
            <FavoritesPage />
          </Protected>
        ),
      },
      {
        path: 'admin',
        element: <AdminLayout />,
        children: [
          { path: 'dashboard', element: <AdminDashboard /> },
          { path: 'events', element: <AdminEvents /> },
          { path: 'users', element: <AdminUsers /> },
        ],
      },
    ],
  },
]);

// Clear older PWA caches/service workers so stale pre-HasAnAra shells cannot reappear.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.getRegistrations().then((registrations) => {
      registrations.forEach((registration) => void registration.unregister());
    });
    if ('caches' in window) {
      caches.keys().then((keys) => keys.forEach((key) => void caches.delete(key)));
    }
  });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  </StrictMode>
);
