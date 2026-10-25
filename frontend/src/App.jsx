import { useState } from 'react'
import Accuracy from './Accuracy'
import Forecast from './Forecast'

export default function App() {
  const [view, setView] = useState('forecast')
  const [cutoff, setCutoff] = useState('09:00')

  return (
    <div className="page">
      <header>
        <h1>UK wind generation: day-ahead forecast monitor</h1>
        <p className="sub">
          Latest wind forecast available when buying for a delivery day, and how accurate it has been.
        </p>
      </header>
      <nav className="tabs">
        <button className={view === 'forecast' ? 'active' : ''} onClick={() => setView('forecast')}>
          Delivery-day forecast
        </button>
        <button className={view === 'accuracy' ? 'active' : ''} onClick={() => setView('accuracy')}>
          Forecast accuracy
        </button>
      </nav>
      {view === 'forecast' ? (
        <Forecast cutoff={cutoff} setCutoff={setCutoff} />
      ) : (
        <Accuracy cutoff={cutoff} setCutoff={setCutoff} />
      )}
    </div>
  )
}