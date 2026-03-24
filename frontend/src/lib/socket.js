/**
 * TravelSync Pro — SocketIO singleton
 * Import this module anywhere in the app to get the shared socket instance.
 * The socket does NOT auto-connect — Layout.jsx connects it when the user logs in.
 */
import { io } from 'socket.io-client'

// In dev mode Vite runs on :5173 and proxies /api to :3399.
// SocketIO is on the Flask server directly, so connect straight to :3399.
// In production everything is on the same origin.
const SOCKET_URL = import.meta.env.DEV
  ? 'http://localhost:3399'
  : window.location.origin

const socket = io(SOCKET_URL, {
  withCredentials: true,   // send session cookie so Flask can identify the user
  autoConnect: false,      // Layout controls when to connect
  reconnectionAttempts: 15,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 10000,
  randomizationFactor: 0.3,
  transports: ['websocket', 'polling'],
})

export default socket
