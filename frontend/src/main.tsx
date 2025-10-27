import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import AppLayout from './routes/AppLayout';
import SearchPage from './routes/SearchPage';
import VideoPage from './routes/VideoPage';
import LoginPage from './routes/LoginPage';
import FavoritesPage from './routes/FavoritesPage';
import Protected from './routes/Protected';
import AdminLayout from './routes/admin/AdminLayout';
import AdminDashboard from './routes/admin/AdminDashboard';
import AdminEvents from './routes/admin/AdminEvents';
import AdminUsers from './routes/admin/AdminUsers';
import { AuthProvider, ThemeProvider } from './services';
import PricingPage from './routes/PricingPage';
import UpgradePage from './routes/UpgradePage';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <SearchPage /> },
      { path: 'v/:videoId', element: <VideoPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'pricing', element: <PricingPage /> },
      { path: 'upgrade', element: <UpgradePage /> },
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

// Register Service Worker for PWA support
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        console.log('Service Worker registered:', registration);
      })
      .catch((error) => {
        console.log('Service Worker registration failed:', error);
      });
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
