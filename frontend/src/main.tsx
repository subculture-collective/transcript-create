import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import AppLayout from './routes/AppLayout'
import SearchPage from './routes/SearchPage'
import VideoPage from './routes/VideoPage'
import LoginPage from './routes/LoginPage'
import FavoritesPage from './routes/FavoritesPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <SearchPage /> },
      { path: 'v/:videoId', element: <VideoPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'favorites', element: <FavoritesPage /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
