// src/components/signals/SignalCard.tsx
import { TrendingUp, TrendingDown, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { Signal, useStore } from '../../store/useStore'

interface Props { signal: Signal }

const STATUS_STYLE: Record<string, string> = {
  PENDING: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
  WIN:     'bg-green-500/10  text-green-400  border-green-500/30',
  LOSS:    'bg-red-500/10    text-red-400    border-red-500/30',
  EXPIRED: 'bg-gray-500/10  text-gray-400   border-gray-500/30',
}

const STATUS_ICON = {
  PENDING: Clock,
  WIN:     CheckCircle,
  LOSS:    XCircle,
  EXPIRED: AlertCircle,
}

const SCORE_LABELS: Record<string, string> = {
  trend_confirmation: 'Trend',
  rsi_pullback:       'RSI',
  market_structure:   'Structure',
  atr_volatility:     'Volatility',
  liquidity_sweep:    'Liq. Sweep',
}

export function SignalCard({ signal }: Props) {
  const { setSelectedSignalId, selectedSignalId } = useStore()
  const isSelected = selectedSignalId === signal.id
  const StatusIcon = STATUS_ICON[signal.status] ?? Clock

  const formatPrice = (p: number) =>
    signal.pair.includes('BTC') || signal.pair.includes('ETH')
      ? p.toLocaleString('en-US', { maximumFractionDigits: 2 })
      : p.toFixed(5)

  const timeStr = new Date(signal.created_at + 'Z').toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit'
  })
  const dateStr = new Date(signal.created_at + 'Z').toLocaleDateString([], {
    month: 'short', day: 'numeric'
  })

  return (
    <div
      onClick={() => setSelectedSignalId(isSelected ? null : signal.id)}
      className={`
        group cursor-pointer rounded-xl border p-4 transition-all duration-200
        hover:border-blue-500/50 hover:shadow-lg hover:shadow-blue-500/5
        ${isSelected
          ? 'border-blue-500/60 bg-blue-500/5 shadow-lg shadow-blue-500/10'
          : 'border-gray-700/50 bg-gray-800/60'}
      `}
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          {signal.direction === 'BUY'
            ? <TrendingUp  size={18} className="text-green-400 shrink-0" />
            : <TrendingDown size={18} className="text-red-400   shrink-0" />
          }
          <div>
            <span className="text-white font-bold text-sm">{signal.pair}</span>
            <span className={`ml-2 text-xs font-semibold px-1.5 py-0.5 rounded ${
              signal.direction === 'BUY'
                ? 'bg-green-500/20 text-green-400'
                : 'bg-red-500/20 text-red-400'
            }`}>
              {signal.direction}
            </span>
          </div>
        </div>

        <div className="flex flex-col items-end gap-1">
          <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${STATUS_STYLE[signal.status]}`}>
            <StatusIcon size={11} />
            {signal.status}
          </span>
          <span className="text-gray-500 text-xs">{dateStr} {timeStr}</span>
        </div>
      </div>

      {/* Prices */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[
          { label: 'Entry',  value: formatPrice(signal.entry),      color: 'text-white' },
          { label: 'SL',     value: formatPrice(signal.stop_loss),  color: 'text-red-400' },
          { label: 'TP',     value: formatPrice(signal.take_profit), color: 'text-green-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-gray-900/50 rounded-lg p-2 text-center">
            <p className="text-gray-500 text-xs mb-0.5">{label}</p>
            <p className={`${color} font-mono text-xs font-medium`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Score bar + RR */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500 text-xs">Score</span>
          <div className="flex gap-0.5">
            {[...Array(8)].map((_, i) => (
              <div key={i} className={`w-2 h-2 rounded-sm ${
                i < signal.score ? 'bg-blue-400' : 'bg-gray-700'
              }`} />
            ))}
          </div>
          <span className="text-blue-400 text-xs font-bold">{signal.score}/8</span>
        </div>
        <span className="text-gray-400 text-xs">
          RR <span className="text-white font-medium">1:{signal.risk_reward}</span>
        </span>
      </div>

      {/* Expanded score breakdown */}
      {isSelected && (
        <div className="mt-3 pt-3 border-t border-gray-700/50">
          <p className="text-gray-500 text-xs mb-2">Score breakdown</p>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.entries(SCORE_LABELS).map(([key, label]) => {
              const pts = signal.score_breakdown?.[key] ?? 0
              return (
                <div key={key} className={`flex items-center gap-1.5 text-xs rounded px-2 py-1 ${
                  pts > 0 ? 'bg-green-500/10 text-green-400' : 'bg-gray-800 text-gray-500'
                }`}>
                  <span>{pts > 0 ? '✓' : '–'}</span>
                  <span>{label}</span>
                  {pts > 0 && <span className="ml-auto font-bold">+{pts}</span>}
                </div>
              )
            })}
          </div>
          <p className="text-blue-400 text-xs mt-2 text-center">
            Click to view chart ↓
          </p>
        </div>
      )}
    </div>
  )
}
