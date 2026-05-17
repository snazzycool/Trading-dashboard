// src/components/trading/AccountPanel.tsx
import { TrendingUp, TrendingDown, Wifi, WifiOff, DollarSign, Activity } from 'lucide-react'
import { useStore } from '../../store/useStore'

export function AccountPanel() {
  const { account, positions, capitalConnected, capitalEnv } = useStore()

  const equity   = (account?.balance ?? 0) + (account?.profit_loss ?? 0)
  const pnl      = account?.profit_loss ?? 0
  const pnlColor = pnl > 0 ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-gray-400'
  const pnlIcon  = pnl > 0 ? TrendingUp : TrendingDown

  if (!capitalConnected) {
    return (
      <div className="bg-[#0d0d1a] border border-white/6 rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <WifiOff size={16} className="text-red-400" />
          <h2 className="text-white font-semibold">Account</h2>
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/20">
            Disconnected
          </span>
        </div>
        <p className="text-gray-500 text-sm">Capital.com not connected. Check your API credentials.</p>
      </div>
    )
  }

  return (
    <div className="bg-[#0d0d1a] border border-white/6 rounded-2xl p-5 space-y-4">

      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-green-500/15 flex items-center justify-center">
          <DollarSign size={13} className="text-green-400" />
        </div>
        <h2 className="text-white font-semibold">Account</h2>
        <span className={`ml-auto text-xs px-2 py-0.5 rounded-full border font-medium ${
          capitalEnv === 'DEMO'
            ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20'
            : 'bg-green-500/15 text-green-400 border-green-500/20'
        }`}>
          {capitalEnv}
        </span>
      </div>

      {/* Balance cards */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-white/3 border border-white/6 rounded-xl p-3">
          <p className="text-gray-500 text-xs mb-1">Balance</p>
          <p className="text-white font-bold text-lg">
            {(account?.currency ?? 'USD')} {(account?.balance ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
        <div className="bg-white/3 border border-white/6 rounded-xl p-3">
          <p className="text-gray-500 text-xs mb-1">Equity</p>
          <p className="text-white font-bold text-lg">
            {equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
        <div className="bg-white/3 border border-white/6 rounded-xl p-3">
          <p className="text-gray-500 text-xs mb-1">Floating P&L</p>
          <p className={`font-bold text-lg ${pnlColor}`}>
            {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
          </p>
        </div>
        <div className="bg-white/3 border border-white/6 rounded-xl p-3">
          <p className="text-gray-500 text-xs mb-1">Available</p>
          <p className="text-blue-400 font-bold text-lg">
            {(account?.available ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
      </div>

      {/* Open positions */}
      {positions.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Activity size={13} className="text-blue-400" />
            <p className="text-gray-400 text-xs font-medium uppercase tracking-wide">
              Open Positions ({positions.length})
            </p>
          </div>
          <div className="space-y-2">
            {positions.map((pos: any) => {
              const profit  = pos.profit ?? 0
              const isProfit = profit >= 0
              return (
                <div
                  key={pos.deal_id}
                  className="flex items-center justify-between bg-white/3 border border-white/6 rounded-xl px-3 py-2.5"
                >
                  <div className="flex items-center gap-2">
                    {pos.direction === 'BUY'
                      ? <TrendingUp  size={14} className="text-green-400" />
                      : <TrendingDown size={14} className="text-red-400" />
                    }
                    <div>
                      <p className="text-white text-sm font-semibold">{pos.epic}</p>
                      <p className="text-gray-500 text-xs">
                        {pos.direction} @ {pos.open_level}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`font-bold text-sm ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                      {isProfit ? '+' : ''}{profit.toFixed(2)}
                    </p>
                    <p className="text-gray-600 text-xs">size {pos.size}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {positions.length === 0 && (
        <p className="text-gray-600 text-xs text-center py-2">No open positions</p>
      )}
    </div>
  )
}
