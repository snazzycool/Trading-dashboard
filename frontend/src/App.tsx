// src/App.tsx
import { useEffect, useState, useCallback } from 'react'
import {
  Activity, Play, Square, Wifi, WifiOff,
  BarChart2, Clock, List, TrendingUp, TrendingDown,
  Bell, BellOff, ChevronUp,
} from 'lucide-react'
import { useStore } from './store/useStore'
import { useWebSocket } from './hooks/useWebSocket'
import { useNotifications } from './hooks/useNotifications'
import { SignalCard } from './components/signals/SignalCard'
import { SignalDetail } from './components/signals/SignalDetail'
import { StatsPanel } from './components/signals/StatsPanel'

export default function App() {
  const {
    connected, scannerActive, scannerStatus,
    signals, stats, selectedSignalId,
    activeTab, setActiveTab,
  } = useStore()

  const { startScanner, stopScanner } = useWebSocket()
  const { requestPermission, sendNotification, isSupported, isGranted } = useNotifications()

  const [notifEnabled, setNotifEnabled] = useState(isGranted)
  const [showScrollTop, setShowScrollTop] = useState(false)

  const selectedSignal = signals.find(s => s.id === selectedSignalId)
  const pendingCount   = signals.filter(s => s.status === 'PENDING').length
  const winCount       = signals.filter(s => s.status === 'WIN').length
  const lossCount      = signals.filter(s => s.status === 'LOSS').length
  const liveSignals    = signals.filter(s => s.status === 'PENDING')
  const historySignals = signals.filter(s => s.status !== 'PENDING')

  // Send notification on new signal
  useEffect(() => {
    if (!notifEnabled || signals.length === 0) return
    const newest = signals[0]
    if (newest.status !== 'PENDING') return
    const age = Date.now() - new Date(newest.created_at + 'Z').getTime()
    if (age > 60000) return // ignore signals older than 1 minute
    sendNotification(
      `${newest.direction} Signal — ${newest.pair}`,
      `Score ${newest.score}/8 | Entry: ${newest.entry} | RR 1:${newest.risk_reward}`,
      `signal-${newest.id}`
    )
  }, [signals[0]?.id])

  // Send notification on WIN/LOSS resolution
  useEffect(() => {
    if (!notifEnabled) return
    const recent = signals.find(s => s.status === 'WIN' || s.status === 'LOSS')
    if (!recent || !recent.resolved_at) return
    const age = Date.now() - new Date(recent.resolved_at + 'Z').getTime()
    if (age > 120000) return
    const icon = recent.status === 'WIN' ? '✅' : '❌'
    sendNotification(
      `${icon} ${recent.status} — ${recent.pair}`,
      `${recent.direction} signal closed as ${recent.status}`,
      `result-${recent.id}`
    )
  }, [signals.find(s => s.status === 'WIN' || s.status === 'LOSS')?.status])

  const handleNotifToggle = useCallback(async () => {
    if (!notifEnabled) {
      const granted = await requestPermission()
      setNotifEnabled(granted)
      if (granted) {
        sendNotification('Notifications enabled ✅', 'You will be alerted on new signals and results')
      }
    } else {
      setNotifEnabled(false)
    }
  }, [notifEnabled, requestPermission, sendNotification])

  useEffect(() => {
    const onScroll = () => setShowScrollTop(window.scrollY > 300)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">

      {/* ── Header ────────────────────────────────────────────────────── */}
      <header className="bg-[#0f0f1a] border-b border-white/5 sticky top-0 z-30 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between gap-3">

          {/* Logo */}
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-blue-700 rounded-lg flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Activity size={15} className="text-white" />
            </div>
            <div className="hidden sm:block">
              <p className="text-white font-bold text-sm leading-none">Signal Dashboard</p>
              <p className="text-gray-500 text-xs mt-0.5">Algorithmic Trading</p>
            </div>
          </div>

          {/* Stats pills */}
          <div className="hidden md:flex items-center gap-2">
            {[
              { icon: Clock,       value: pendingCount, label: 'Live',   color: 'text-yellow-400', bg: 'bg-yellow-400/10 border-yellow-400/20' },
              { icon: TrendingUp,  value: winCount,     label: 'Wins',   color: 'text-green-400',  bg: 'bg-green-400/10  border-green-400/20' },
              { icon: TrendingDown,value: lossCount,    label: 'Losses', color: 'text-red-400',    bg: 'bg-red-400/10    border-red-400/20' },
            ].map(({ icon: Icon, value, label, color, bg }) => (
              <div key={label} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium ${bg} ${color}`}>
                <Icon size={12} />
                <span className="font-bold">{value}</span>
                <span className="opacity-70">{label}</span>
              </div>
            ))}
            {stats && stats.total > 0 && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium bg-blue-400/10 border-blue-400/20 text-blue-400">
                <BarChart2 size={12} />
                <span className="font-bold">{stats.win_rate}%</span>
                <span className="opacity-70">Win Rate</span>
              </div>
            )}
          </div>

          {/* Right controls */}
          <div className="flex items-center gap-2 shrink-0">

            {/* Notification bell */}
            {isSupported && (
              <button
                onClick={handleNotifToggle}
                title={notifEnabled ? 'Disable notifications' : 'Enable notifications'}
                className={`p-2 rounded-lg border transition-all ${
                  notifEnabled
                    ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                    : 'bg-white/5 border-white/10 text-gray-500 hover:text-gray-300'
                }`}
              >
                {notifEnabled ? <Bell size={15} /> : <BellOff size={15} />}
              </button>
            )}

            {/* Scanner toggle */}
            <button
              onClick={scannerActive ? stopScanner : startScanner}
              disabled={!connected}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                scannerActive
                  ? 'bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25'
                  : 'bg-green-500/15 text-green-400 border border-green-500/30 hover:bg-green-500/25'
              }`}
            >
              {scannerActive
                ? <><Square size={13} className="fill-current" /> Stop</>
                : <><Play  size={13} className="fill-current" /> Start</>
              }
            </button>

            {/* Connection dot */}
            <div className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-full border ${
              connected
                ? 'bg-green-400/10 border-green-400/20 text-green-400'
                : 'bg-red-400/10 border-red-400/20 text-red-400'
            }`}>
              {connected ? <Wifi size={12} /> : <WifiOff size={12} />}
              <span className="hidden sm:block font-medium">{connected ? 'Live' : 'Offline'}</span>
            </div>
          </div>
        </div>

        {/* Scanner status bar */}
        {(scannerActive || scannerStatus.scanning) && (
          <div className="border-t border-white/5 bg-blue-500/5">
            <div className="max-w-7xl mx-auto px-4 py-1.5 flex items-center gap-2">
              {scannerStatus.scanning && (
                <div className="flex gap-0.5">
                  {[0,1,2].map(i => (
                    <div key={i} className="w-1 h-3 bg-blue-400 rounded-full animate-bounce opacity-70"
                      style={{ animationDelay: `${i*150}ms` }} />
                  ))}
                </div>
              )}
              <p className="text-blue-300/70 text-xs">{scannerStatus.message}</p>
              {scannerStatus.last_scan && (
                <p className="text-gray-600 text-xs ml-auto">
                  {new Date(scannerStatus.last_scan + 'Z').toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        )}
      </header>

      {/* ── Body ──────────────────────────────────────────────────────── */}
      <div className="flex-1 max-w-7xl mx-auto w-full px-4 py-5 flex flex-col lg:flex-row gap-5">

        {/* ── Left: signal list ──────────────────────────────────────── */}
        <div className="w-full lg:w-[380px] flex flex-col gap-3 shrink-0">

          {/* Tabs */}
          <div className="flex bg-white/5 border border-white/8 rounded-xl p-1 gap-1">
            {([
              { key: 'feed',    label: 'Live Feed', icon: Activity, count: pendingCount },
              { key: 'history', label: 'History',   icon: List,     count: historySignals.length },
            ] as const).map(({ key, label, icon: Icon, count }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  activeTab === key
                    ? 'bg-white/10 text-white shadow-sm'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                <Icon size={14} />
                {label}
                {count > 0 && (
                  <span className={`text-xs rounded-full px-1.5 py-0.5 font-bold ${
                    activeTab === key
                      ? key === 'feed' ? 'bg-blue-500 text-white' : 'bg-white/20 text-white'
                      : 'bg-white/10 text-gray-400'
                  }`}>
                    {count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Signal cards */}
          <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 200px)' }}>
            {activeTab === 'feed' && (
              liveSignals.length === 0
                ? <EmptyState active={scannerActive} connected={connected} onStart={startScanner} />
                : liveSignals.map(s => <SignalCard key={s.id} signal={s} />)
            )}
            {activeTab === 'history' && (
              historySignals.length === 0
                ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <List size={36} className="text-white/10 mb-3" />
                    <p className="text-gray-500 text-sm">No resolved signals yet</p>
                  </div>
                )
                : historySignals.map(s => <SignalCard key={s.id} signal={s} />)
            )}
          </div>
        </div>

        {/* ── Right: detail + stats ──────────────────────────────────── */}
        <div className="flex-1 flex flex-col gap-5 min-w-0">

          {/* Signal detail */}
          {selectedSignal ? (
            <SignalDetail signal={selectedSignal} />
          ) : (
            <div className="bg-white/3 border border-white/6 border-dashed rounded-2xl flex flex-col items-center justify-center py-16 text-center min-h-[280px]">
              <div className="w-14 h-14 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
                <BarChart2 size={26} className="text-white/20" />
              </div>
              <p className="text-gray-400 font-medium">Select a signal to view chart</p>
              <p className="text-gray-600 text-sm mt-1.5 max-w-xs leading-relaxed">
                Click any signal card to see its TradingView chart, entry/SL/TP levels and score breakdown
              </p>
            </div>
          )}

          {/* Performance */}
          <div className="bg-[#0f0f1a] border border-white/6 rounded-2xl p-5">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-7 h-7 rounded-lg bg-blue-500/15 flex items-center justify-center">
                <BarChart2 size={14} className="text-blue-400" />
              </div>
              <h2 className="text-white font-semibold">Performance</h2>
              {stats && stats.total > 0 && (
                <span className="ml-auto text-xs text-gray-500">
                  {stats.total} total signal{stats.total !== 1 ? 's' : ''}
                </span>
              )}
            </div>
            <StatsPanel />
          </div>
        </div>
      </div>

      {/* Scroll to top */}
      {showScrollTop && (
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="fixed bottom-6 right-6 w-10 h-10 bg-blue-600 hover:bg-blue-500 text-white rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/25 transition-all z-50"
        >
          <ChevronUp size={18} />
        </button>
      )}
    </div>
  )
}

function EmptyState({ active, connected, onStart }: {
  active: boolean; connected: boolean; onStart: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className={`w-16 h-16 rounded-2xl flex items-center justify-center mb-4 transition-all ${
        active ? 'bg-blue-500/10' : 'bg-white/5'
      }`}>
        <Activity size={28} className={active ? 'text-blue-400 animate-pulse' : 'text-white/15'} />
      </div>
      {!connected ? (
        <>
          <p className="text-gray-400 font-medium">Connecting to server…</p>
          <p className="text-gray-600 text-sm mt-1">Please wait</p>
        </>
      ) : !active ? (
        <>
          <p className="text-gray-300 font-semibold">Scanner is off</p>
          <p className="text-gray-600 text-sm mt-1 mb-5">Start scanning to receive signals</p>
          <button
            onClick={onStart}
            className="flex items-center gap-2 bg-green-500/15 hover:bg-green-500/25 text-green-400 border border-green-500/30 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all"
          >
            <Play size={14} className="fill-current" /> Start Scanner
          </button>
        </>
      ) : (
        <>
          <p className="text-gray-300 font-semibold">Scanning markets…</p>
          <p className="text-gray-600 text-sm mt-1">High-probability setups appear here</p>
          <div className="flex gap-1.5 mt-5">
            {[0,1,2].map(i => (
              <div key={i} className="w-2 h-2 rounded-full bg-blue-400 animate-bounce"
                style={{ animationDelay: `${i*150}ms` }} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
