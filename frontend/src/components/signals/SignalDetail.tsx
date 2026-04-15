// src/components/signals/SignalDetail.tsx
import { useEffect, useRef } from 'react'
import { X, TrendingUp, TrendingDown, Clock, CheckCircle, XCircle } from 'lucide-react'
import { Signal, useStore } from '../../store/useStore'

// TwelveData symbol → TradingView symbol mapping
const TV_SYMBOL: Record<string, string> = {
  'EUR/USD': 'FX:EURUSD', 'GBP/USD': 'FX:GBPUSD', 'USD/JPY': 'FX:USDJPY',
  'AUD/USD': 'FX:AUDUSD', 'USD/CAD': 'FX:USDCAD', 'EUR/GBP': 'FX:EURGBP',
  'GBP/JPY': 'FX:GBPJPY', 'NZD/USD': 'FX:NZDUSD',
  'BTC/USD': 'BINANCE:BTCUSDT', 'ETH/USD': 'BINANCE:ETHUSDT',
  'SOL/USD': 'BINANCE:SOLUSDT', 'BNB/USD': 'BINANCE:BNBUSDT',
}

interface Props { signal: Signal }

export function SignalDetail({ signal }: Props) {
  const { setSelectedSignalId } = useStore()
  const chartRef = useRef<HTMLDivElement>(null)

  const tvSymbol = TV_SYMBOL[signal.pair] || `FX:${signal.pair.replace('/', '')}`

  // Inject TradingView widget
  useEffect(() => {
    if (!chartRef.current) return
    chartRef.current.innerHTML = ''

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/tv.js'
    script.async = true
    script.onload = () => {
      if (!(window as any).TradingView || !chartRef.current) return
      new (window as any).TradingView.widget({
        container_id: chartRef.current.id,
        symbol:       tvSymbol,
        interval:     '15',
        timezone:     'Etc/UTC',
        theme:        'dark',
        style:        '1',
        locale:       'en',
        width:        '100%',
        height:       380,
        hide_top_toolbar: false,
        hide_legend:      false,
        save_image:       false,
        enable_publishing: false,
        withdateranges:   true,
        studies: ['RSI@tv-basicstudies', 'MAExp@tv-basicstudies'],
      })
    }
    document.head.appendChild(script)

    return () => {
      if (document.head.contains(script)) document.head.removeChild(script)
    }
  }, [tvSymbol])

  const fmt = (p: number) =>
    signal.pair.includes('BTC') || signal.pair.includes('ETH')
      ? p.toLocaleString('en-US', { maximumFractionDigits: 2 })
      : p.toFixed(5)

  const isPending = signal.status === 'PENDING'
  const isWin     = signal.status === 'WIN'
  const isLoss    = signal.status === 'LOSS'

  const pnlPct = (() => {
    if (signal.direction === 'BUY') {
      if (isWin)  return `+${((signal.take_profit - signal.entry) / signal.entry * 100).toFixed(3)}%`
      if (isLoss) return `-${((signal.entry - signal.stop_loss) / signal.entry * 100).toFixed(3)}%`
    } else {
      if (isWin)  return `+${((signal.entry - signal.take_profit) / signal.entry * 100).toFixed(3)}%`
      if (isLoss) return `-${((signal.stop_loss - signal.entry) / signal.entry * 100).toFixed(3)}%`
    }
    return null
  })()

  return (
    <div className="bg-gray-800/80 border border-gray-700/50 rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700/50">
        <div className="flex items-center gap-3">
          {signal.direction === 'BUY'
            ? <TrendingUp size={20} className="text-green-400" />
            : <TrendingDown size={20} className="text-red-400" />
          }
          <div>
            <h3 className="text-white font-bold text-lg">{signal.pair}</h3>
            <p className="text-gray-400 text-xs">
              {new Date(signal.created_at + 'Z').toLocaleString()}
            </p>
          </div>
          <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
            signal.direction === 'BUY'
              ? 'bg-green-500/20 text-green-400'
              : 'bg-red-500/20 text-red-400'
          }`}>
            {signal.direction}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {pnlPct && (
            <span className={`text-sm font-bold ${isWin ? 'text-green-400' : 'text-red-400'}`}>
              {pnlPct}
            </span>
          )}
          <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium ${
            isPending ? 'bg-yellow-500/15 text-yellow-400' :
            isWin     ? 'bg-green-500/15  text-green-400'  :
            isLoss    ? 'bg-red-500/15    text-red-400'    :
                        'bg-gray-500/15   text-gray-400'
          }`}>
            {isPending && <Clock size={12} />}
            {isWin     && <CheckCircle size={12} />}
            {isLoss    && <XCircle size={12} />}
            {signal.status}
          </span>
          <button
            onClick={() => setSelectedSignalId(null)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-700 transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Chart */}
      <div className="px-5 pt-4">
        <div
          id={`tv-chart-${signal.id}`}
          ref={chartRef}
          className="w-full rounded-xl overflow-hidden"
          style={{ height: 380 }}
        />
      </div>

      {/* Trade levels */}
      <div className="grid grid-cols-3 gap-3 px-5 py-4">
        {[
          { label: 'Entry Price', value: fmt(signal.entry),      color: 'text-white',      bg: 'bg-blue-500/10  border-blue-500/30' },
          { label: 'Stop Loss',   value: fmt(signal.stop_loss),  color: 'text-red-400',    bg: 'bg-red-500/10   border-red-500/30' },
          { label: 'Take Profit', value: fmt(signal.take_profit), color: 'text-green-400', bg: 'bg-green-500/10 border-green-500/30' },
        ].map(({ label, value, color, bg }) => (
          <div key={label} className={`rounded-xl p-3 border text-center ${bg}`}>
            <p className="text-gray-400 text-xs mb-1">{label}</p>
            <p className={`${color} font-mono font-bold text-sm`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 px-5 pb-4">
        <div className="bg-gray-900/50 rounded-xl p-3 text-center">
          <p className="text-gray-500 text-xs mb-1">Score</p>
          <p className="text-blue-400 font-bold">{signal.score}/8</p>
        </div>
        <div className="bg-gray-900/50 rounded-xl p-3 text-center">
          <p className="text-gray-500 text-xs mb-1">Risk:Reward</p>
          <p className="text-white font-bold">1:{signal.risk_reward}</p>
        </div>
        <div className="bg-gray-900/50 rounded-xl p-3 text-center">
          <p className="text-gray-500 text-xs mb-1">ATR</p>
          <p className="text-purple-400 font-mono font-bold text-sm">{signal.atr.toFixed(5)}</p>
        </div>
      </div>
    </div>
  )
}
