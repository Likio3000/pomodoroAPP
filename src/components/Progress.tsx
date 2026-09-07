import { useState } from 'react';
import type { State } from '../domain/model';
import { csv, dayKey, daysBefore, statistics } from '../domain/stats';
import { Icon } from './Icon';
export function download(contents: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function Metrics({ state, allTime = false }: { state: State; allTime?: boolean }) {
  const stats = statistics(state.sessions, Date.now());
  return (
    <div
      className="metrics"
      role="region"
      aria-label={allTime ? 'Progreso acumulado' : 'Progreso de hoy'}
    >
      <div>
        <p>
          {allTime ? stats.totalMinutes : stats.minutes}
          <span> min</span>
        </p>
        <span className="metric-label">
          {allTime ? 'ENFOQUE ACUMULADO' : 'TIEMPO DE ENFOQUE HOY'}
        </span>
      </div>
      <div>
        <p>{allTime ? state.sessions.length : stats.today.length}</p>
        <span className="metric-label">{allTime ? 'SESIONES COMPLETADAS' : 'SESIONES DE HOY'}</span>
      </div>
      <div>
        <p>
          {stats.streak}
          <span> {stats.streak === 1 ? 'día' : 'días'}</span>
        </p>
        <span className="metric-label">RACHA ACTUAL</span>
      </div>
    </div>
  );
}
export function Progress({ state }: { state: State }) {
  const [filter, setFilter] = useState('week');
  const [limit, setLimit] = useState(30);
  const now = Date.now();
  const stats = statistics(state.sessions, now);
  const weekMinutes = stats.week.reduce((sum, day) => sum + day.minutes, 0);
  const max = Math.max(60, ...stats.week.map((d) => d.minutes));
  const sessions = state.sessions
    .filter(
      (s) =>
        filter === 'all' ||
        (filter === 'today'
          ? dayKey(s.completedAt) === dayKey(now)
          : dayKey(s.completedAt) >= dayKey(daysBefore(now, 6).getTime())),
    )
    .sort((a, b) => b.completedAt - a.completedAt);
  return (
    <main className="progress-page" id="main-content">
      <header className="progress-heading">
        <div>
          <h1>El tiempo bien dedicado.</h1>
          <p className="muted">Pequeños momentos. Un progreso que se queda.</p>
        </div>
        <button
          className="secondary"
          disabled={!state.sessions.length}
          onClick={() =>
            download(
              csv(state.sessions),
              `pomodoro-sesiones-${dayKey(now)}.csv`,
              'text/csv;charset=utf-8',
            )
          }
        >
          <Icon name="download" size={18} />
          Exportar CSV
        </button>
      </header>
      <Metrics state={state} allTime />
      <section className="week-section" aria-labelledby="week-title">
        <div className="section-heading">
          <h2 id="week-title">Tu última semana</h2>
          <span className="muted">
            {weekMinutes} {weekMinutes === 1 ? 'minuto' : 'minutos'} de enfoque
          </span>
        </div>
        <div
          className="week-chart"
          role="img"
          aria-label={stats.week.map((d) => `${d.key}: ${d.minutes} minutos`).join(', ')}
        >
          {stats.week.map((d) => (
            <div className={`chart-column ${d.today ? 'today' : ''}`} key={d.key}>
              <span className="bar-value">{d.minutes ? `${d.minutes} min` : '—'}</span>
              <div className="bar-track">
                <div className="chart-bar" style={{ height: `${(d.minutes / max) * 100}%` }} />
              </div>
              <span className="day-label">{d.today ? 'hoy' : d.label}</span>
            </div>
          ))}
        </div>
        <p className="small muted">
          {state.sessions.length
            ? 'Solo sesiones de enfoque terminadas. Los descansos no suman minutos.'
            : 'Tu primera sesión dibujará el comienzo. Sin prisas.'}
        </p>
      </section>
      <section className="history-section" aria-labelledby="history-title">
        <div className="section-heading">
          <h2 id="history-title">Sesión a sesión</h2>
          <label className="history-filter">
            <span className="sr-only">Filtrar historial</span>
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setLimit(30);
              }}
            >
              <option value="today">Hoy</option>
              <option value="week">Últimos 7 días</option>
              <option value="all">Todo el historial</option>
            </select>
          </label>
        </div>
        {sessions.length ? (
          <>
            <ul className="history-list">
              {sessions.slice(0, limit).map((s) => (
                <li key={s.id}>
                  <span className="history-check">
                    <Icon name="check" size={18} />
                  </span>
                  <div>
                    <strong>{s.taskTitle || 'Un momento de enfoque'}</strong>
                    <time dateTime={new Date(s.completedAt).toISOString()}>
                      {new Date(s.completedAt).toLocaleString('es', {
                        day: 'numeric',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </time>
                  </div>
                  <span className="history-duration">{s.duration / 60_000} min</span>
                </li>
              ))}
            </ul>
            {sessions.length > limit ? (
              <button className="secondary" onClick={() => setLimit(limit + 30)}>
                Ver más sesiones
              </button>
            ) : null}
          </>
        ) : (
          <div className="history-empty">
            <Icon name="sound" size={25} />
            <p>Aún no hay sesiones en este periodo.</p>
            <span className="muted small">
              Vuelve a Enfoque y dedica un momento a lo que importa.
            </span>
          </div>
        )}
      </section>
    </main>
  );
}
