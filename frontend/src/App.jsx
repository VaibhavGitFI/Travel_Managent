import { useEffect, Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import useStore from './store/useStore'
import { getMe } from './api/auth'
import Layout from './components/layout/Layout'
import Spinner from './components/ui/Spinner'

// Lazy-load pages
const Login         = lazy(() => import('./pages/Login'))
const Dashboard     = lazy(() => import('./pages/Dashboard'))
const TripPlanner   = lazy(() => import('./pages/TripPlanner'))
const Accommodation = lazy(() => import('./pages/Accommodation'))
const Expenses      = lazy(() => import('./pages/Expenses'))
const Meetings      = lazy(() => import('./pages/Meetings'))
const Requests      = lazy(() => import('./pages/Requests'))
const Approvals     = lazy(() => import('./pages/Approvals'))
const Analytics     = lazy(() => import('./pages/Analytics'))
const Chat          = lazy(() => import('./pages/Chat'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full min-h-[300px]">
      <Spinner size="lg" color="accent" />
    </div>
  )
}

function ProtectedRoute({ children }) {
  const isLoggedIn = useStore((s) => s.auth.isLoggedIn)
  if (!isLoggedIn) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const { auth, setUser, setLoading } = useStore()

  // Re-validate session on mount
  useEffect(() => {
    if (!auth.isLoggedIn || auth.user) return
    setLoading(true)
    getMe()
      .then((data) => setUser(data.user || data))
      .catch(() => setUser(null))
  }, [auth.isLoggedIn, auth.user, setLoading, setUser])

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />

        {/* Root redirect */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Navigate to="/dashboard" replace />
            </ProtectedRoute>
          }
        />

        {/* Protected — wrapped in Layout */}
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route
            path="/dashboard"
            element={
              <Suspense fallback={<PageLoader />}>
                <Dashboard />
              </Suspense>
            }
          />
          <Route
            path="/planner"
            element={
              <Suspense fallback={<PageLoader />}>
                <TripPlanner />
              </Suspense>
            }
          />
          <Route
            path="/accommodation"
            element={
              <Suspense fallback={<PageLoader />}>
                <Accommodation />
              </Suspense>
            }
          />
          <Route
            path="/expenses"
            element={
              <Suspense fallback={<PageLoader />}>
                <Expenses />
              </Suspense>
            }
          />
          <Route
            path="/meetings"
            element={
              <Suspense fallback={<PageLoader />}>
                <Meetings />
              </Suspense>
            }
          />
          <Route
            path="/requests"
            element={
              <Suspense fallback={<PageLoader />}>
                <Requests />
              </Suspense>
            }
          />
          <Route
            path="/approvals"
            element={
              <Suspense fallback={<PageLoader />}>
                <Approvals />
              </Suspense>
            }
          />
          <Route
            path="/analytics"
            element={
              <Suspense fallback={<PageLoader />}>
                <Analytics />
              </Suspense>
            }
          />
          <Route
            path="/chat"
            element={
              <Suspense fallback={<PageLoader />}>
                <Chat />
              </Suspense>
            }
          />
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
