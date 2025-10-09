import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import AppLayout from './routes/AppLayout'
import SearchPage from './routes/SearchPage'
import VideoPage from './routes/VideoPage'
import LoginPage from './routes/LoginPage'
import FavoritesPage from './routes/FavoritesPage'
import Protected from './routes/Protected'
import AdminLayout from './routes/admin/AdminLayout'
import AdminEvents from './routes/admin/AdminEvents'
import AdminUsers from './routes/admin/AdminUsers'
import { AuthProvider } from './services/auth'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <SearchPage /> },
      { path: 'v/:videoId', element: <VideoPage /> },
      { path: 'login', element: <LoginPage /> },
  { path: 'favorites', element: <Protected><FavoritesPage /></Protected> },
      {
        path: 'admin',
        element: <AdminLayout />,
        children: [
          { path: 'events', element: <AdminEvents /> },
          { path: 'users', element: <AdminUsers /> },
        ],
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </StrictMode>,
)
