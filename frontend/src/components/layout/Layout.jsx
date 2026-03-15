import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import clsx from 'clsx'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import useStore from '../../store/useStore'
import client from '../../api/client'

export default function Layout() {
  const { setApiHealth, setSidebarCollapsed, sidebar } = useStore()

  // Poll health every 60 s
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const { data } = await client.get('/health')
        const rawServices = data.services || {}
        const services = Object.keys(rawServices).length
          ? rawServices
          : Object.fromEntries(
              Object.entries(data || {}).filter(([k]) => !['status', 'version', 'timestamp', 'error'].includes(k))
            )

        const allOk = Object.keys(services).length > 0
          && Object.values(services).every((s) => s === true || s?.status === 'ok' || s?.configured === true || s === 'ok')

        setApiHealth({
          status:      allOk ? 'healthy' : 'degraded',
          services,
          lastChecked: new Date().toISOString(),
        })
      } catch {
        setApiHealth({ status: 'degraded', services: {}, lastChecked: new Date().toISOString() })
      }
    }

    checkHealth()
    const id = setInterval(checkHealth, 60_000)
    return () => clearInterval(id)
  }, [setApiHealth])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1023px)')

    const onBreakpointChange = (event) => {
      if (event.matches) {
        setSidebarCollapsed(true)
      }
    }

    if (media.matches) {
      setSidebarCollapsed(true)
    }

    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', onBreakpointChange)
      return () => media.removeEventListener('change', onBreakpointChange)
    }

    media.addListener(onBreakpointChange)
    return () => media.removeListener(onBreakpointChange)
  }, [setSidebarCollapsed])

  return (
    <div className="relative flex h-dvh min-h-screen w-full overflow-hidden bg-gray-50">
      <Sidebar />

      <button
        type="button"
        aria-label="Close sidebar"
        onClick={() => setSidebarCollapsed(true)}
        className={clsx(
          'fixed inset-0 z-30 bg-slate-950/40 backdrop-blur-[1px] transition-opacity duration-300 lg:hidden',
          sidebar.collapsed ? 'pointer-events-none opacity-0' : 'opacity-100'
        )}
      />

      {/* Main content */}
      <div className="flex flex-1 min-h-0 min-w-0 flex-col overflow-hidden">
        <Topbar />

        <main className="flex-1 min-h-0 overflow-x-hidden overflow-y-auto">
          <div className="page-enter min-h-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
