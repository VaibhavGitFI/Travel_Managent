import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const useStore = create(
  persist(
    (set, get) => ({
      // ── Auth ──────────────────────────────────────────────
      auth: {
        user: null,
        isLoggedIn: false,
        loading: false,
      },

      setUser: (user) =>
        set((state) => ({
          auth: { ...state.auth, user, isLoggedIn: !!user, loading: false },
        })),

      setLoading: (loading) =>
        set((state) => ({
          auth: { ...state.auth, loading },
        })),

      logout: () =>
        set({
          auth: { user: null, isLoggedIn: false, loading: false },
        }),

      // ── Sidebar ──────────────────────────────────────────
      sidebar: {
        collapsed: false,
      },

      toggleSidebar: () =>
        set((state) => ({
          sidebar: { collapsed: !state.sidebar.collapsed },
        })),

      setSidebarCollapsed: (collapsed) =>
        set({ sidebar: { collapsed } }),

      // ── Notifications ────────────────────────────────────
      notifications: [],

      setNotifications: (notifications) => set({ notifications }),

      addNotification: (notification) =>
        set((state) => ({
          notifications: [
            { id: Date.now(), read: false, ...notification },
            ...state.notifications.filter((n) => n.id !== notification.id),
          ],
        })),

      markNotificationRead: (id) =>
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n
          ),
        })),

      markAllNotificationsRead: () =>
        set((state) => ({
          notifications: state.notifications.map((n) => ({ ...n, read: true })),
        })),

      // ── Health Status ────────────────────────────────────
      apiHealth: {
        status: 'unknown', // 'healthy' | 'degraded' | 'unknown'
        services: {},
        lastChecked: null,
      },

      setApiHealth: (health) => set({ apiHealth: health }),

      // ── Stale Data (for real-time refresh) ─────────────
      staleData: {
        requests: false,
        meetings: false,
        expenses: false,
        approvals: false,
        analytics: false,
      },

      markStale: (key) =>
        set((state) => ({
          staleData: { ...state.staleData, [key]: true },
        })),

      clearStale: (key) =>
        set((state) => ({
          staleData: { ...state.staleData, [key]: false },
        })),
    }),
    {
      name: 'travelsync-store',
      partialize: (state) => ({
        auth: state.auth,
        sidebar: state.sidebar,
      }),
    }
  )
)

export default useStore
