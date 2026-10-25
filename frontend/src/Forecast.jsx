import { useEffect, useMemo, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { fetchForecast, fetchMeta } from './api'

const CUTOFFS = ['07:00', '09:00', '10:00']
const fmtMW = (v) => (v == null ? '—' : `${Math.round(v).toLocaleString('en-GB')} MW`)
const fmtTime = (iso, opts) =>
  new Date(iso).toLocaleString('en-GB', { timeZone: 'Europe/London', ...opts })

function Kpi({ label, value, hint }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  )
}

export default function Forecast({ cutoff, setCutoff }) {
  const [dates, setDates] = useState([])
  const [date, setDate] = useState('2026-01-20')
  const [showCorrected, setShowCorrected] = useState(false)
  const [showActual, setShowActual] = useState(true)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchMeta().then((m) => setDates(m.dates)).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    setError(null)
    fetchForecast(date, cutoff, ctrl.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setData(null)
          setError(e.message)
        }
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [date, cutoff])

  const chartData = useMemo(
    () =>
      (data?.rows ?? []).map((r) => ({
        t: r.start_time,
        forecast: r.forecast_mw,
        corrected: r.corrected_forecast_mw,
        actual: r.actual_mw,
        band: r.band_low_mw == null ? null : [r.band_low_mw, r.band_high_mw],
      })),
    [data],
  )

  const s = data?.summary
  const idx = dates.indexOf(date)

  return (
    <div>

      <section className="controls">
        <label>
          Delivery day
          <div className="date-row">
            <button disabled={idx <= 0} onClick={() => setDate(dates[idx - 1])}>‹</button>
            <select value={date} onChange={(e) => setDate(e.target.value)}>
              {(dates.length ? dates : [date]).map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <button disabled={idx < 0 || idx >= dates.length - 1} onClick={() => setDate(dates[idx + 1])}>›</button>
          </div>
        </label>
        <label>
          Decision cutoff (D-1, UK time)
          <select value={cutoff} onChange={(e) => setCutoff(e.target.value)}>
            {CUTOFFS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={showCorrected} onChange={(e) => setShowCorrected(e.target.checked)} />
          Show bias-adjusted line
        </label>
        <label className="check">
          <input type="checkbox" checked={showActual} onChange={(e) => setShowActual(e.target.checked)} />
          Show actual (evaluation only)
        </label>
      </section>

      {error && <div className="error">Could not load data: {error}</div>}
      {loading && !data && <div className="muted">Loading…</div>}

      {data && (
        <>
          <section className="kpis">
            <Kpi
              label="Forecast used"
              value={fmtTime(data.forecast_publish_times.at(-1), { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
              hint={`Latest published before ${data.cutoff_local} on D-1`}
            />
            <Kpi label="Mean forecast" value={fmtMW(chartData.reduce((a, r) => a + r.forecast, 0) / chartData.length)} />
            <Kpi label="MAE (raw forecast)" value={fmtMW(s.mae_mw)} hint={`${s.nmae_pct}% of mean actual`} />
            <Kpi
              label="MAE (bias-adjusted)"
              value={fmtMW(s.corrected_mae_mw)}
              hint={data.correction ? `Ratio ${data.correction.ratio} from ${data.correction.history_days} days` : 'Not enough history'}
            />
            <Kpi label="Bias on the day" value={fmtMW(s.bias_mw)} hint="Positive = over-forecast" />
          </section>

          <section className="card">
            <ResponsiveContainer width="100%" height={380}>
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="t" interval={5} tickFormatter={(t) => fmtTime(t, { hour: '2-digit', minute: '2-digit' })} />
                <YAxis domain={[0, (m) => Math.ceil(m / 5000) * 5000]} tickCount={6} tickFormatter={(v) => `${(v / 1000).toFixed(0)} GW`} />
                <Tooltip
                  labelFormatter={(t) => fmtTime(t, { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                  formatter={(v, name) => [Array.isArray(v) ? `${Math.round(v[0]).toLocaleString('en-GB')} to ${Math.round(v[1]).toLocaleString('en-GB')} MW` : fmtMW(v), name]}
                />
                <Legend />
                <Area dataKey="band" name="90% range for actual" stroke="none" fill="#3b82f6" fillOpacity={0.15} isAnimationActive={false} />
                <Line dataKey="forecast" name="Forecast" stroke="#2563eb" dot={false} strokeWidth={2} isAnimationActive={false} />
                {showCorrected && (
                  <Line dataKey="corrected" name="Bias-adjusted forecast" stroke="#059669" strokeDasharray="6 4" dot={false} strokeWidth={2} isAnimationActive={false} />
                )}
                {showActual && (
                  <Line dataKey="actual" name="Actual (evaluation)" stroke="#111827" dot={false} strokeWidth={2} isAnimationActive={false} />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </section>

          <section className="notes">
            <p>
              <b>Reading this chart.</b> The shaded range is built from the forecast errors of the previous{' '}
              {data.band ? data.correction.history_days : '—'} days (up to {data.correction?.history_end ?? '—'}),
              which is all a buyer could know at decision time. It is deliberately asymmetric, because the forecast
              has mostly over-predicted wind.
            </p>
            <p>
              <b>Caution.</b> The bias-adjusted line improved accuracy on average in a January backtest, but not on
              every day, so compare both MAE figures above. Actuals are shown only to evaluate the forecast after the fact.
            </p>
          </section>
        </>
      )}
    </div>
  )
}