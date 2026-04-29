// src/hooks/useNotifications.ts
import { useEffect, useRef, useCallback } from 'react'

export function useNotifications() {
  const permissionRef = useRef<NotificationPermission>('default')
  const swRef = useRef<ServiceWorkerRegistration | null>(null)

  useEffect(() => {
    // Register service worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js')
        .then(reg => {
          swRef.current = reg
          console.log('[SW] Registered')
        })
        .catch(err => console.warn('[SW] Registration failed:', err))
    }

    // Check existing permission
    if ('Notification' in window) {
      permissionRef.current = Notification.permission
    }
  }, [])

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!('Notification' in window)) {
      console.warn('Notifications not supported')
      return false
    }
    if (Notification.permission === 'granted') {
      permissionRef.current = 'granted'
      return true
    }
    const result = await Notification.requestPermission()
    permissionRef.current = result
    return result === 'granted'
  }, [])

  const sendNotification = useCallback((
    title: string,
    body: string,
    tag?: string
  ) => {
    if (permissionRef.current !== 'granted') return

    // Use service worker notification if available (works in background)
    if (swRef.current && swRef.current.active) {
      swRef.current.showNotification(title, {
        body,
        tag: tag || 'signal',
        requireInteraction: true,
        icon: '/icon-192.png',
      })
    } else {
      // Fallback to basic notification
      new Notification(title, { body, tag: tag || 'signal' })
    }
  }, [])

  const isSupported = 'Notification' in window && 'serviceWorker' in navigator
  const isGranted = permissionRef.current === 'granted'

  return { requestPermission, sendNotification, isSupported, isGranted }
}
