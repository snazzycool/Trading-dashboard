// src/App.tsx — Main dashboard layout
import { useEffect } from 'react'
import {
  Activity, Play, Square, Wifi, WifiOff,
  BarChart2, Clock, List, TrendingUp, TrendingDown,
} from 'lucide-react'
import { useStore } from './store/useStore'
import { useWebSocket } from './hooks/useWebSocket'
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

  const selectedSignal = signals.find(s => s.id === selectedSignalId)

  const pendingCount = signals.filter(s => s.status === 'PENDING').length
  const winCount     = signals.filter(s => s.status === 'WIN').length
  const lossCount    = signals.filter(s => s.status === 'LOSS').length

  const liveSignals    = signals.filter(s => s.status === 'PENDING')
  const historySignals = signals.filter(s => s.status !== 'PENDING')

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">

      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">

          {/* Logo */}
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
              <Activity size={14} className="text-white" />
            </div>
            <span className="text-white font-bold hidden sm:block">Signal Dashboard</span>
          </div>

          {/* Quick stats */}
          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-4 text-sm">
              <div className="flex items-center gap-1.5 text-yellow-400">
                <Clock size={13} />
                <span className="font-medium">{pendingCount}</span>
                <span className="text-gray-500">pending</span>
              </div>
              <div className="flex items-center gap-1.5 text-green-400">
                <TrendingUp size={13} />
                <span className="font-medium">{winCount}</span>
                <span className="text-gray-500">wins</span>
              </div>
              <div className="flex items-center gap-1.5 text-red-400">
                <TrendingDown size={13} />
                <span className="font-medium">{lossCount}</span>
                <span className="text-gray-500">losses</span>
              </div>
              {stats && stats.total > 0 && (
                <div className="flex items-center gap-1.5 text-blue-400">
                  <BarChart2 size={13} />
                  <span className="font-medium">{stats.win_rate}%</span>
                  <span className="text-gray-500">win rate</span>
                </div>
              )}
            </div>

            {/* Scanner toggle */}
            <button
              onClick={scannerActive ? stopScanner : startScanner}
              disabled={!connected}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                scannerActive
                  ? 'bg-red-600/20 text-red-400 border border-red-600/40 hover:bg-red-600/30'
                  : 'bg-green-600/20 text-green-400 border border-green-600/40 hover:bg-green-600/30'
              }`}
            >
              {scannerActive
                ? <><Square size={13} /> Stop</>
                : <><Play  size={13} /> Start</>
              }
            </button>

            {/* Connection indicator */}
            <div className={`flex items-center gap-1.5 text-xs ${connected ? 'text-green-400' : 'text-red-400'}`}>
              {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
              <span className="hidden sm:block">{connected ? 'Live' : 'Offline'}</span>
            </div>
          </div>
        </div>

        {/* Scanner status bar */}
        {scannerActive && (
          <div className="border-t border-gray-800 bg-gray-900/50">
            <div className="max-w-7xl mx-auto px-4 py-1.5 flex items-center gap-2">
              {scannerStatus.scanning && (
                <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
              )}
              <p className="text-gray-400 text-xs">{scannerStatus.message}</p>
              {scannerStatus.last_scan && (
                <p className="text-gray-600 text-xs ml-auto">
                  Last scan: {new Date(scannerStatus.last_scan + 'Z').toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        )}
      </header>

      {/* ── Main layout ─────────────────────────────────────────────── */}
      <div className="flex-1 max-w-7xl mx-auto w-full px-4 py-5 flex flex-col lg:flex-row gap-5">

        {/* ── Left column: tabs + signal list ─────────────────────── */}
        <div className="w-full lg:w-96 flex flex-col gap-4 shrink-0">

          {/* Tab bar */}
          <div className="flex bg-gray-800/60 border border-gray-700/50 rounded-xl p-1">
            {([
              { key: 'feed',    label: 'Live Feed',  icon: Activity },
              { key: 'history', label: 'History',    icon: List },
            ] as const).map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === key
                    ? 'bg-gray-700 text-white shadow-sm'
                    : 'text-gray-400 hover:text-gray-300'
                }`}
              >
                <Icon size={14} />
                {label}
                {key === 'feed' && pendingCount > 0 && (
                  <span className="bg-blue-600 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
                    {pendingCount}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Signal list */}
          <div className="flex-1 space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
            {activeTab === 'feed' && (
              <>
                {liveSignals.length === 0 ? (
                  <EmptyState
                    active={scannerActive}
                    connected={connected}
                    onStart={startScanner}
                  />
                ) : (
                  liveSignals.map(sig => (
                    <SignalCard key={sig.id} signal={sig} />
                  ))
                )}
              </>
            )}

            {activeTab === 'history' && (
              <>
                {historySignals.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <List size={40} className="text-gray-700 mb-3" />
                    <p className="text-gray-500 text-sm">No resolved signals yet</p>
                  </div>
                ) : (
                  historySignals.map(sig => (
                    <SignalCard key={sig.id} signal={sig} />
                  ))
                )}
              </>
            )}
          </div>
        </div>

        {/* ── Right column: detail + stats ───────────────────────── */}
        <div className="flex-1 flex flex-col gap-5 min-w-0">

          {/* Signal detail panel */}
          {selectedSignal ? (
            <SignalDetail signal={selectedSignal} />
          ) : (
            <div className="bg-gray-800/40 border border-gray-700/40 border-dashed rounded-2xl flex flex-col items-center justify-center py-16 text-center">
              <BarChart2 size={40} className="text-gray-700 mb-3" />
              <p className="text-gray-500 font-medium">Select a signal to view chart</p>
              <p className="text-gray-600 text-sm mt-1">
                Click any signal card on the left to see its TradingView chart,<br />
                entry/SL/TP levels, and detailed stats
              </p>
            </div>
          )}

          {/* Performance stats */}
          <div className="bg-gray-800/40 border border-gray-700/40 rounded-2xl p-5">
            <div className="flex items-center gap-2 mb-5">
              <BarChart2 size={18} className="text-blue-400" />
              <h2 className="text-white font-semibold">Performance</h2>
            </div>
            <StatsPanel />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Empty state ────────────────────────────────────────────────────────────

function EmptyState({
  active, connected, onStart,
}: { active: boolean; connected: boolean; onStart: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-4 ${
        active ? 'bg-blue-500/10' : 'bg-gray-800'
      }`}>
        <Activity size={28} className={active ? 'text-blue-400 animate-pulse' : 'text-gray-600'} />
      </div>

      {!connected ? (
        <>
          <p className="text-gray-400 font-medium">Connecting to server…</p>
          <p className="text-gray-600 text-sm mt-1">Please wait</p>
        </>
      ) : !active ? (
        <>
          <p className="text-gray-400 font-medium">Scanner is off</p>
          <p className="text-gray-600 text-sm mt-1 mb-4">
            Start the scanner to begin receiving signals
          </p>
          <button
            onClick={onStart}
            className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors"
          >
            <Play size={14} /> Start Scanner
          </button>
        </>
      ) : (
        <>
          <p className="text-gray-400 font-medium">Scanning markets…</p>
          <p className="text-gray-600 text-sm mt-1">
            Signals appear here when high-probability setups are found
          </p>
          <div className="flex gap-1.5 mt-4">
            {[0, 1, 2].map(i => (
              <div key={i}
                className="w-2 h-2 rounded-full bg-blue-400 animate-bounce"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
