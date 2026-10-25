async function get(path, params = {}, signal) {
  const qs = new URLSearchParams(params).toString()
  const res = await fetch(`/api/${path}${qs ? `?${qs}` : ''}`, { signal })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`)
  }
  return res.json()
}

export const fetchMeta = (signal) => get('meta', {}, signal)
export const fetchForecast = (date, cutoff, signal) => get('forecast', { date, cutoff }, signal)
export const fetchAccuracy = (cutoff, signal) => get('accuracy', { cutoff }, signal)
export const fetchBacktest = (cutoff, signal) => get('backtest', { cutoff }, signal)