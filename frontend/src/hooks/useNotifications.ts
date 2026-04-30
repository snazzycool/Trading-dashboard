// src/hooks/useNotifications.ts
import { useEffect, useRef, useCallback } from 'react'

export function useNotifications() {
  const swRef = useRef<ServiceWorkerRegistration | null>(null)
  const grantedRef = useRef(
    typeof Notification !== 'undefined' && Notification.permission === 'granted'
  )

  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js')
        .then(reg => { swRef.current = reg })
        .catch(err => console.warn('[SW] Failed:', err))
    }
  }, [])

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!('Notification' in window)) return false
    if (Notification.permission === 'granted') {
      grantedRef.current = true
      return true
    }
    const result = await Notification.requestPermission()
    grantedRef.current = result === 'granted'
    return grantedRef.current
  }, [])

  const sendNotification = useCallback((title: string, body: string, tag?: string) => {
    if (!grantedRef.current) return
    const opts: NotificationOptions = { body, tag: tag || 'signal', requireInteraction: true }
    if (swRef.current) {
      swRef.current.showNotification(title, opts)
    } else {
      new Notification(title, opts)
    }
  }, [])

  return {
    requestPermission,
    sendNotification,
    isSupported: typeof Notification !== 'undefined' && 'serviceWorker' in navigator,
    isGranted: grantedRef.current,
  }
}
