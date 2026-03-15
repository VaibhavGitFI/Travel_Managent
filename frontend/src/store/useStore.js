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

      addNotification: (notification) =>
        set((state) => ({
          notifications: [
            { id: Date.now(), read: false, ...notification },
            ...state.notifications,
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
