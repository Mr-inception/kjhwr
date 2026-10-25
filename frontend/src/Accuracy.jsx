import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, Line, ComposedChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { fetchAccuracy, fetchBacktest } from './api'

const CUTOFFS = ['07:00', '09:00', '10:00']
const mw = (v) => (v == null ? '—' : `${Math.round(v).toLocaleString('en-GB')} MW`)
const gw = (v) => `${(v / 1000).toFixed(1)} GW`


function Kpi({ label, value, hint }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  )
}

function Chart({ title, note, children }) {
  return (
    <section className="card">
      <h3>{title}</h3>
      {note && <p className="muted small">{note}</p>}
      <ResponsiveContainer width="100%" height={280}>{children}</ResponsiveContainer>
    </section>
  )
}

export default function Accuracy({ cutoff, setCutoff }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState(null)

  const [bt, setBt] = useState(null)

  useEffect(() => {
    const ctrl = new AbortController()
    setError(null)
    Promise.all([fetchAccuracy(cutoff, ctrl.signal), fetchBacktest(cutoff, ctrl.signal)])
      .then(([acc, back]) => {
        setD(acc)
        setBt(back)
      })
      .catch((e) => e.name !== 'AbortError' && setError(e.message))
    return () => ctrl.abort()
  }, [cutoff])

  if (error) return <div className="error">Could not load data: {error}</div>
  if (!d) return <div className="muted">Loading…</div>

  const o = d.overall
  const q = d.signed_error_quantiles_mw

  return (
    <>
      <section className="controls">
        <label>
          Decision cutoff (D-1, UK time)
          <select value={cutoff} onChange={(e) => setCutoff(e.target.value)}>
            {CUTOFFS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </section>

      <section className="kpis">
        <Kpi label="Mean absolute error" value={mw(o.mae_mw)} hint={`${o.nmae_pct}% of mean actual wind`} />
        <Kpi label="Average bias" value={mw(o.bias_mw)} hint="Positive = forecast above actual" />
        <Kpi label="90th percentile abs. error" value={mw(o.p90_abs_error_mw)} hint="9 in 10 half-hours are within this" />
        <Kpi label="RMSE" value={mw(o.rmse_mw)} hint={`${o.n} half-hours, January 2026`} />
      </section>

      <section className="card">
        <h3>Planning range: what actual wind could be</h3>
        <p className="muted small">
          Errors are one-sided (forecast minus actual), so a symmetric ± range would mislead. For a forecast F,
          the 90% range for actual wind is F − {Math.round(q.p95).toLocaleString('en-GB')} to F + {Math.round(-q.p05).toLocaleString('en-GB')} MW
          (median error {Math.round(q.p50).toLocaleString('en-GB')} MW). This uses all of January, so it is descriptive.
          The delivery-day page uses only earlier days.
        </p>
      </section>

      <Chart title="Error by forecast horizon" note="Latest forecast published at least this many hours before the target time.">
        <ComposedChart data={d.by_horizon}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="horizon_h" tickFormatter={(h) => `${h}h`} />
          <YAxis tickFormatter={gw} />
          <Tooltip formatter={(v) => mw(v)} labelFormatter={(h) => `${h} h ahead`} />
          <Legend />
          <Bar dataKey="mae_mw" name="MAE" fill="#2563eb" />
          <Line dataKey="bias_mw" name="Bias" stroke="#dc2626" strokeWidth={2} />
        </ComposedChart>
      </Chart>

      <Chart title="Day-ahead error by hour of day (UK time)">
        <ComposedChart data={d.by_hour}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="hour" tickFormatter={(h) => `${String(h).padStart(2, '0')}:00`} interval={2} />
          <YAxis tickFormatter={gw} />
          <Tooltip formatter={(v) => mw(v)} labelFormatter={(h) => `${String(h).padStart(2, '0')}:00`} />
          <Legend />
          <Bar dataKey="mae_mw" name="MAE" fill="#2563eb" />
          <Line dataKey="bias_mw" name="Bias" stroke="#dc2626" strokeWidth={2} dot={false} />
        </ComposedChart>
      </Chart>

      <Chart title="Daily bias" note="Positive bars: forecast was above actual. The bias changes a lot from day to day.">
        <BarChart data={d.daily}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tickFormatter={(s) => s.slice(8)} interval={1} />
          <YAxis tickFormatter={gw} />
          <ReferenceLine y={0} stroke="#111827" />
          <Tooltip formatter={(v) => mw(v)} />
          <Bar dataKey="bias_mw" name="Bias" fill="#dc2626" />
        </BarChart>
      </Chart>

      <section className="card">
        <h3>Error by wind level</h3>
        <p className="muted small">Half-hours grouped into quarters by actual generation.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Wind level</th><th>Actual range</th><th>Mean forecast</th><th>Mean actual</th><th>MAE</th><th>Bias</th></tr>
            </thead>
            <tbody>
              {d.by_wind_level.map((r) => (
                <tr key={r.level}>
                  <td>{r.level}</td>
                  <td>{gw(r.actual_min_mw)} to {gw(r.actual_max_mw)}</td>
                  <td>{mw(r.mean_forecast_mw)}</td>
                  <td>{mw(r.mean_actual_mw)}</td>
                  <td>{mw(r.mae_mw)}</td>
                  <td>{mw(r.bias_mw)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3>Would a bias adjustment have helped? (out-of-sample backtest)</h3>
        <p className="muted small">
          Each day is adjusted using only earlier days a buyer could have known (up to D-2). Compare within a row only:
          longer windows are scored on fewer days. One winter month, so treat it as promising, not proven.
        </p>
        <div className="table-wrap">
                   <table>
            <thead>
              <tr><th>History window</th><th>Days scored</th><th>Raw MAE</th><th>Adjusted MAE</th><th>Change</th></tr>
            </thead>
            <tbody>
              {(bt?.rows ?? []).map((r) => (
                <tr key={r.window_days}>
                  <td>{r.window_days} days</td>
                  <td>{r.days_scored}</td>
                  <td>{mw(r.raw_mae_mw)}</td>
                  <td>{mw(r.adjusted_mae_mw)}</td>
                  <td>−{r.improvement_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}