// src/store/useStore.ts
import { create } from 'zustand'

export interface Signal {
  id: number
  pair: string
  direction: 'BUY' | 'SELL'
  entry: number
  stop_loss: number
  take_profit: number
  score: number
  score_breakdown: Record<string, number>
  atr: number
  risk_reward: number
  pip_risk: number
  pip_reward: number
  deal_id?: string
  trade_size?: number
  status: 'PENDING' | 'WIN' | 'LOSS' | 'EXPIRED'
  created_at: string
  resolved_at?: string
}

export interface Stats {
  total: number
  wins: number
  losses: number
  pending: number
  win_rate: number
  by_pair: { pair: string; wins: number; losses: number; total: number }[]
}

export interface AccountInfo {
  balance:     number
  profit_loss: number
  available:   number
  currency:    string
}

export interface Position {
  deal_id:    string
  epic:       string
  direction:  'BUY' | 'SELL'
  size:       number
  open_level: number
  stop_loss?: number
  take_profit?: number
  profit:     number
  created_at?: string
}

interface ScannerStatus {
  message:   string
  scanning:  boolean
  last_scan?: string
}

interface Store {
  // Connection
  connected:         boolean
  setConnected:      (v: boolean) => void

  // Capital.com
  capitalConnected:  boolean
  setCapitalConnected: (v: boolean) => void
  capitalEnv:        string
  setCapitalEnv:     (v: string) => void
  autoTrade:         boolean
  setAutoTrade:      (v: boolean) => void

  // Account
  account:           AccountInfo | null
  setAccount:        (a: AccountInfo) => void
  positions:         Position[]
  setPositions:      (p: Position[]) => void

  // Scanner
  scannerActive:     boolean
  setScannerActive:  (v: boolean) => void
  scannerStatus:     ScannerStatus
  setScannerStatus:  (s: ScannerStatus) => void

  // Signals
  signals:           Signal[]
  setSignals:        (signals: Signal[]) => void
  addSignal:         (signal: Signal) => void
  updateSignal:      (id: number, patch: Partial<Signal>) => void

  // Stats
  stats:             Stats | null
  setStats:          (stats: Stats) => void

  // UI
  selectedSignalId:  number | null
  setSelectedSignalId: (id: number | null) => void
  activeTab:         'feed' | 'history'
  setActiveTab:      (t: 'feed' | 'history') => void

  // Notifications
  notifications:     { id: number; message: string; type: 'win' | 'loss' | 'trade' | 'info' }[]
  addNotification:   (msg: string, type: 'win' | 'loss' | 'trade' | 'info') => void
  removeNotification: (id: number) => void
}

let _notifId = 0

export const useStore = create<Store>((set) => ({
  connected:         false,
  setConnected:      (connected)         => set({ connected }),

  capitalConnected:  false,
  setCapitalConnected: (capitalConnected) => set({ capitalConnected }),
  capitalEnv:        'DEMO',
  setCapitalEnv:     (capitalEnv)        => set({ capitalEnv }),
  autoTrade:         true,
  setAutoTrade:      (autoTrade)         => set({ autoTrade }),

  account:           null,
  setAccount:        (account)           => set({ account }),
  positions:         [],
  setPositions:      (positions)         => set({ positions }),

  scannerActive:     false,
  setScannerActive:  (scannerActive)     => set({ scannerActive }),
  scannerStatus:     { message: 'Connecting...', scanning: false },
  setScannerStatus:  (scannerStatus)     => set({ scannerStatus }),

  signals:           [],
  setSignals:        (signals)           => set({ signals }),
  addSignal:         (signal)            => set((s) => ({
    signals: [signal, ...s.signals].slice(0, 200),
  })),
  updateSignal:      (id, patch)         => set((s) => ({
    signals: s.signals.map((sig) => sig.id === id ? { ...sig, ...patch } : sig),
  })),

  stats:             null,
  setStats:          (stats)             => set({ stats }),

  selectedSignalId:  null,
  setSelectedSignalId: (selectedSignalId) => set({ selectedSignalId }),
  activeTab:         'feed',
  setActiveTab:      (activeTab)         => set({ activeTab }),

  notifications:     [],
  addNotification:   (message, type)     => {
    const id = ++_notifId
    set((s) => ({
      notifications: [{ id, message, type }, ...s.notifications].slice(0, 5),
    }))
    // Auto-remove after 6 seconds
    setTimeout(() => {
      set((s) => ({
        notifications: s.notifications.filter((n) => n.id !== id),
      }))
    }, 6000)
  },
  removeNotification: (id) => set((s) => ({
    notifications: s.notifications.filter((n) => n.id !== id),
  })),
}))
