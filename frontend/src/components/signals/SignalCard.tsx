// src/components/signals/SignalCard.tsx
import { TrendingUp, TrendingDown, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { Signal, useStore } from '../../store/useStore'

interface Props { signal: Signal }

const STATUS_STYLE: Record<string, string> = {
  PENDING: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  WIN:     'bg-green-500/15  text-green-400  border-green-500/30',
  LOSS:    'bg-red-500/15    text-red-400    border-red-500/30',
  EXPIRED: 'bg-gray-500/15  text-gray-400   border-gray-500/30',
}

const STATUS_ICON: Record<string, any> = {
  PENDING: Clock, WIN: CheckCircle, LOSS: XCircle, EXPIRED: AlertCircle,
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

  const fmt = (p: number) =>
    signal.pair === 'XAU/USD' ? p.toFixed(2)
    : signal.pair.includes('JPY') ? p.toFixed(3)
    : p.toFixed(5)

  const timeStr = new Date(signal.created_at + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const dateStr = new Date(signal.created_at + 'Z').toLocaleDateString([], { month: 'short', day: 'numeric' })
  const pipRisk   = signal.pip_risk   ?? 0
  const pipReward = signal.pip_reward ?? 0

  return (
    <div
      onClick={() => setSelectedSignalId(isSelected ? null : signal.id)}
      className={[
        'cursor-pointer rounded-xl border p-4 transition-all duration-200',
        'hover:border-blue-500/40 hover:shadow-lg hover:shadow-blue-500/5',
        isSelected
          ? 'border-blue-500/50 bg-blue-500/5 shadow-lg shadow-blue-500/10'
          : 'border-white/6 bg-white/3 hover:bg-white/5',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          {signal.direction === 'BUY'
            ? <TrendingUp  size={16} className="text-green-400 shrink-0" />
            : <TrendingDown size={16} className="text-red-400   shrink-0" />}
          <div>
            <span className="text-white font-bold text-sm">{signal.pair}</span>
            <span className={['ml-1.5 text-xs font-bold px-1.5 py-0.5 rounded',
              signal.direction === 'BUY' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
            ].join(' ')}>
              {signal.direction}
            </span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={['flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border', STATUS_STYLE[signal.status]].join(' ')}>
            <StatusIcon size={10} />{signal.status}
          </span>
          <span className="text-gray-600 text-xs">{dateStr} {timeStr}</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-1.5 mb-3">
        {[
          { label: 'Entry', value: fmt(signal.entry),       color: 'text-white' },
          { label: 'SL',    value: fmt(signal.stop_loss),   color: 'text-red-400' },
          { label: 'TP',    value: fmt(signal.take_profit), color: 'text-green-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-black/20 rounded-lg p-2 text-center">
            <p className="text-gray-500 text-xs mb-0.5">{label}</p>
            <p className={color + ' font-mono text-xs font-semibold'}>{value}</p>
          </div>
        ))}
      </div>

      {(pipRisk > 0 || pipReward > 0) && (
        <div className="flex items-center justify-between mb-3 bg-black/20 rounded-lg px-3 py-2">
          <div className="text-center">
            <p className="text-gray-500 text-xs">Risk</p>
            <p className="text-red-400 font-bold text-sm">{pipRisk}p</p>
          </div>
          <div className="text-gray-700 text-xs">|</div>
          <div className="text-center">
            <p className="text-gray-500 text-xs">Target</p>
            <p className="text-green-400 font-bold text-sm">{pipReward}p</p>
          </div>
          <div className="text-gray-700 text-xs">|</div>
          <div className="text-center">
            <p className="text-gray-500 text-xs">RR</p>
            <p className="text-blue-400 font-bold text-sm">1:{signal.risk_reward}</p>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <span className="text-gray-600 text-xs">Score</span>
        <div className="flex gap-0.5 flex-1">
          {[...Array(8)].map((_, i) => (
            <div key={i} className={'h-1.5 flex-1 rounded-full ' + (i < signal.score ? 'bg-blue-400' : 'bg-white/8')} />
          ))}
        </div>
        <span className="text-blue-400 text-xs font-bold">{signal.score}/8</span>
      </div>

      {signal.status === 'WIN' && (
        <div className="mt-2 flex items-center justify-center gap-2 bg-green-500/10 border border-green-500/20 rounded-lg py-1.5">
          <CheckCircle size={12} className="text-green-400" />
          <span className="text-green-400 text-xs font-bold">+{pipReward} pips profit</span>
        </div>
      )}
      {signal.status === 'LOSS' && (
        <div className="mt-2 flex items-center justify-center gap-2 bg-red-500/10 border border-red-500/20 rounded-lg py-1.5">
          <XCircle size={12} className="text-red-400" />
          <span className="text-red-400 text-xs font-bold">-{pipRisk} pips loss</span>
        </div>
      )}

      {isSelected && (
        <div className="mt-3 pt-3 border-t border-white/6">
          <p className="text-gray-500 text-xs mb-2">Score breakdown</p>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.entries(SCORE_LABELS).map(([key, label]) => {
              const pts = signal.score_breakdown?.[key] ?? 0
              return (
                <div key={key} className={'flex items-center gap-1.5 text-xs rounded-lg px-2 py-1.5 ' + (pts > 0 ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-white/3 text-gray-600 border border-white/5')}>
                  <span>{pts > 0 ? '✓' : '–'}</span>
                  <span>{label}</span>
                  {pts > 0 && <span className="ml-auto font-bold">+{pts}</span>}
                </div>
              )
            })}
          </div>
          <p className="text-blue-400/60 text-xs mt-2.5 text-center">Tap again to view chart ↓</p>
        </div>
      )}
    </div>
  )
}
