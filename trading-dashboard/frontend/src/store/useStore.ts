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

interface ScannerStatus {
  message: string
  scanning: boolean
  last_scan?: string
}

interface Store {
  // Connection
  connected: boolean
  setConnected: (v: boolean) => void

  // Scanner
  scannerActive: boolean
  setScannerActive: (v: boolean) => void
  scannerStatus: ScannerStatus
  setScannerStatus: (s: ScannerStatus) => void

  // Signals
  signals: Signal[]
  setSignals: (signals: Signal[]) => void
  addSignal: (signal: Signal) => void
  updateSignal: (id: number, patch: Partial<Signal>) => void

  // Stats
  stats: Stats | null
  setStats: (stats: Stats) => void

  // Selected signal for detail view
  selectedSignalId: number | null
  setSelectedSignalId: (id: number | null) => void

  // Active tab
  activeTab: 'feed' | 'history'
  setActiveTab: (t: 'feed' | 'history') => void
}

export const useStore = create<Store>((set) => ({
  connected: false,
  setConnected: (connected) => set({ connected }),

  scannerActive: false,
  setScannerActive: (scannerActive) => set({ scannerActive }),
  scannerStatus: { message: 'Connecting…', scanning: false },
  setScannerStatus: (scannerStatus) => set({ scannerStatus }),

  signals: [],
  setSignals: (signals) => set({ signals }),
  addSignal: (signal) => set((s) => ({
    signals: [signal, ...s.signals].slice(0, 200),
  })),
  updateSignal: (id, patch) => set((s) => ({
    signals: s.signals.map((sig) =>
      sig.id === id ? { ...sig, ...patch } : sig
    ),
  })),

  stats: null,
  setStats: (stats) => set({ stats }),

  selectedSignalId: null,
  setSelectedSignalId: (selectedSignalId) => set({ selectedSignalId }),

  activeTab: 'feed',
  setActiveTab: (activeTab) => set({ activeTab }),
}))
