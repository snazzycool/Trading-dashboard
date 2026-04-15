// src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback } from 'react'
import { useStore } from '../store/useStore'

const WS_URL = import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()

  const {
    setConnected, setScannerActive, setScannerStatus,
    setSignals, addSignal, updateSignal, setStats,
  } = useStore()

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return

    const socket = new WebSocket(WS_URL)
    ws.current = socket

    socket.onopen = () => {
      setConnected(true)
      setScannerStatus({ message: 'Connected', scanning: false })
      clearTimeout(reconnectTimer.current)
    }

    socket.onmessage = (e) => {
      try {
        const { event, data } = JSON.parse(e.data)

        switch (event) {
          case 'init':
            setScannerActive(data.scanner_active)
            setSignals(data.signals || [])
            if (data.stats) setStats(data.stats)
            setScannerStatus({ message: 'Ready', scanning: false })
            break

          case 'new_signal':
            addSignal(data)
            // Also refresh stats
            send({ action: 'get_stats' })
            break

          case 'signal_update':
            updateSignal(data.id, {
              status:      data.status,
              resolved_at: data.resolved_at,
            })
            send({ action: 'get_stats' })
            break

          case 'scanner_toggled':
            setScannerActive(data.active)
            break

          case 'scanner_status':
            setScannerStatus({
              message:   data.message,
              scanning:  data.scanning ?? false,
              last_scan: data.last_scan,
            })
            break

          case 'stats_update':
            setStats(data)
            break
        }
      } catch { /* ignore malformed */ }
    }

    socket.onclose = () => {
      setConnected(false)
      setScannerStatus({ message: 'Disconnected — reconnecting…', scanning: false })
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    socket.onerror = () => socket.close()
  }, [])

  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [connect])

  const startScanner = () => send({ action: 'start_scanner' })
  const stopScanner  = () => send({ action: 'stop_scanner' })

  return { send, startScanner, stopScanner }
}
