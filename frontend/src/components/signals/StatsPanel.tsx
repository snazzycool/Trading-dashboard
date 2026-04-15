// src/components/signals/StatsPanel.tsx
import {
  PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { TrendingUp, Activity, Target, Award } from 'lucide-react'
import { useStore } from '../../store/useStore'

export function StatsPanel() {
  const { stats } = useStore()

  if (!stats || stats.total === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Activity size={40} className="text-gray-600 mb-4" />
        <p className="text-gray-400 font-medium">No completed signals yet</p>
        <p className="text-gray-600 text-sm mt-1">Stats will appear after signals are resolved</p>
      </div>
    )
  }

  const resolved  = (stats.wins ?? 0) + (stats.losses ?? 0)
  const winRate   = stats.win_rate ?? 0
  const pieData   = [
    { name: 'Wins',    value: stats.wins    ?? 0, color: '#22c55e' },
    { name: 'Losses',  value: stats.losses  ?? 0, color: '#ef4444' },
    { name: 'Pending', value: stats.pending ?? 0, color: '#eab308' },
  ].filter(d => d.value > 0)

  const pairData = (stats.by_pair ?? [])
    .filter(p => p.wins + p.losses > 0)
    .slice(0, 8)
    .map(p => ({
      pair:     p.pair.replace('/', ''),
      wins:     p.wins,
      losses:   p.losses,
      winRate:  p.wins + p.losses > 0
        ? Math.round(p.wins / (p.wins + p.losses) * 100)
        : 0,
    }))

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Signals', value: stats.total,           icon: Activity, color: 'text-blue-400',   bg: 'bg-blue-500/10' },
          { label: 'Win Rate',      value: `${winRate}%`,          icon: TrendingUp, color: 'text-green-400', bg: 'bg-green-500/10' },
          { label: 'Wins',          value: stats.wins ?? 0,        icon: Award,      color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
          { label: 'Losses',        value: stats.losses ?? 0,      icon: Target,     color: 'text-red-400',  bg: 'bg-red-500/10' },
        ].map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className={`rounded-xl p-4 border border-gray-700/50 ${bg}`}>
            <div className={`${color} mb-2`}><Icon size={20} /></div>
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
            <p className="text-gray-400 text-xs mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* Win rate bar */}
      <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-4">
        <p className="text-gray-400 text-sm mb-3">Overall Win Rate</p>
        <div className="relative h-4 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 bg-gradient-to-r from-green-500 to-emerald-400 rounded-full transition-all duration-700"
            style={{ width: `${winRate}%` }}
          />
        </div>
        <div className="flex justify-between mt-1.5 text-xs text-gray-500">
          <span>{stats.wins ?? 0} wins</span>
          <span className="text-white font-bold">{winRate}%</span>
          <span>{stats.losses ?? 0} losses</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Pie chart */}
        {resolved > 0 && (
          <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-4">
            <p className="text-gray-400 text-sm mb-3">Signal Distribution</p>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={70}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Legend
                  iconType="circle"
                  iconSize={8}
                  formatter={(v) => <span className="text-gray-300 text-xs">{v}</span>}
                />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#fff' }}
                  itemStyle={{ color: '#9ca3af' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Per-pair bar chart */}
        {pairData.length > 0 && (
          <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-4">
            <p className="text-gray-400 text-sm mb-3">Results by Pair</p>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={pairData} barSize={10}>
                <XAxis
                  dataKey="pair"
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis hide />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#fff' }}
                  itemStyle={{ color: '#9ca3af' }}
                />
                <Bar dataKey="wins"   fill="#22c55e" radius={[3,3,0,0]} name="Wins" />
                <Bar dataKey="losses" fill="#ef4444" radius={[3,3,0,0]} name="Losses" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Per-pair table */}
      {pairData.length > 0 && (
        <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700/50">
            <p className="text-gray-300 font-medium text-sm">Per-Pair Breakdown</p>
          </div>
          <div className="divide-y divide-gray-700/30">
            {(stats.by_pair ?? []).map(p => {
              const tot = p.wins + p.losses
              const wr  = tot > 0 ? Math.round(p.wins / tot * 100) : 0
              return (
                <div key={p.pair} className="flex items-center px-4 py-2.5 hover:bg-gray-700/20 transition-colors">
                  <span className="text-white font-medium text-sm w-24">{p.pair}</span>
                  <div className="flex-1 flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div className="h-full bg-green-500 rounded-full" style={{ width: `${wr}%` }} />
                    </div>
                    <span className="text-gray-300 text-xs w-8 text-right">{wr}%</span>
                  </div>
                  <div className="flex gap-3 ml-4 text-xs">
                    <span className="text-green-400">{p.wins}W</span>
                    <span className="text-red-400">{p.losses}L</span>
                    <span className="text-gray-500">{p.total}T</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
