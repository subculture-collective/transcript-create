import { lazy, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import AppLayout from './routes/AppLayout';
import { AuthProvider, queryClient, ThemeProvider } from './services';
import { NotFoundPage, PageSuspense as Page, RouteErrorPage } from './routes/RouteStates';
import RootErrorBoundary from './components/RootErrorBoundary';

const HomePage = lazy(() => import('./routes/HomePage'));
const SearchPage = lazy(() => import('./routes/SearchPage'));
const ExplorePage = lazy(() => import('./routes/ExplorePage'));
const StreamsPage = lazy(() => import('./routes/StreamsPage'));
const TimelinePage = lazy(() => import('./routes/TimelinePage'));
const TopicPage = lazy(() => import('./routes/TopicPage'));
const VideoPage = lazy(() => import('./routes/VideoPage'));
const LoginPage = lazy(() => import('./routes/LoginPage'));
const AccountPage = lazy(() => import('./routes/AccountPage'));
const FavoritesPage = lazy(() => import('./routes/FavoritesPage'));
const AdminLayout = lazy(() => import('./routes/admin/AdminLayout'));
const AdminDashboard = lazy(() => import('./routes/admin/AdminDashboard'));
const AdminEvents = lazy(() => import('./routes/admin/AdminEvents'));
const AdminArchivePeriods = lazy(() => import('./routes/admin/AdminArchivePeriods'));
const AdminUsers = lazy(() => import('./routes/admin/AdminUsers'));
const AdminVideoMetadata = lazy(() => import('./routes/admin/AdminVideoMetadata'));
const AdminLabelIntelligence = lazy(() => import('./routes/admin/AdminLabelIntelligence'));

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        element: (
          <Page>
            <HomePage />
          </Page>
        ),
      },
      {
        path: 'search',
        element: (
          <Page>
            <SearchPage />
          </Page>
        ),
      },
      {
        path: 'explore',
        element: (
          <Page>
            <ExplorePage />
          </Page>
        ),
      },
      {
        path: 'episodes',
        element: (
          <Page>
            <StreamsPage />
          </Page>
        ),
      },
      {
        path: 'streams',
        element: (
          <Page>
            <StreamsPage />
          </Page>
        ),
      },
      {
        path: 'timeline',
        element: (
          <Page>
            <TimelinePage />
          </Page>
        ),
      },
      {
        path: 'topics/:query',
        element: (
          <Page>
            <TopicPage />
          </Page>
        ),
      },
      {
        path: 'v/:videoId',
        element: (
          <Page>
            <VideoPage />
          </Page>
        ),
      },
      {
        path: 'login',
        element: (
          <Page>
            <LoginPage />
          </Page>
        ),
      },
      {
        path: 'account',
        element: (
          <Page>
            <AccountPage />
          </Page>
        ),
      },
      {
        path: 'saved',
        element: (
          <Page>
            <FavoritesPage />
          </Page>
        ),
      },
      {
        path: 'favorites',
        element: (
          <Page>
            <FavoritesPage />
          </Page>
        ),
      },
      {
        path: 'admin',
        element: (
          <Page>
            <AdminLayout />
          </Page>
        ),
        children: [
          {
            path: 'dashboard',
            element: (
              <Page>
                <AdminDashboard />
              </Page>
            ),
          },
          {
            path: 'events',
            element: (
              <Page>
                <AdminEvents />
              </Page>
            ),
          },
          {
            path: 'periods',
            element: (
              <Page>
                <AdminArchivePeriods />
              </Page>
            ),
          },
          {
            path: 'metadata',
            element: (
              <Page>
                <AdminVideoMetadata />
              </Page>
            ),
          },
          {
            path: 'labels',
            element: (
              <Page>
                <AdminLabelIntelligence />
              </Page>
            ),
          },
          {
            path: 'users',
            element: (
              <Page>
                <AdminUsers />
              </Page>
            ),
          },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RootErrorBoundary>
            <RouterProvider router={router} />
          </RootErrorBoundary>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>
);
