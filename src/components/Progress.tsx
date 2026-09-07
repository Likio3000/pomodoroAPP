import { useI18n } from '../i18n/context';
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
  const { t, language } = useI18n();
  const stats = statistics(state.sessions, Date.now(), language);
  return (
    <div
      className="metrics"
      role="region"
      aria-label={allTime ? t('totalProgress') : t('todayProgress')}
    >
      <div>
        <p>
          {allTime ? stats.totalMinutes : stats.minutes}
          <span> min</span>
        </p>
        <span className="metric-label">{allTime ? t('totalFocus') : t('todayFocus')}</span>
      </div>
      <div>
        <p>{allTime ? state.sessions.length : stats.today.length}</p>
        <span className="metric-label">{allTime ? t('totalSessions') : t('todaySessions')}</span>
      </div>
      <div>
        <p>
          {stats.streak}
          <span> {stats.streak === 1 ? t('day') : t('days')}</span>
        </p>
        <span className="metric-label">{t('streak')}</span>
      </div>
    </div>
  );
}
export function Progress({ state }: { state: State }) {
  const { t, language, locale } = useI18n();
  const [filter, setFilter] = useState('week');
  const [limit, setLimit] = useState(30);
  const now = Date.now();
  const stats = statistics(state.sessions, now, language);
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
          <h1>{t('progressTitle')}</h1>
          <p className="muted">{t('progressSubtitle')}</p>
        </div>
        <button
          className="secondary"
          disabled={!state.sessions.length}
          onClick={() =>
            download(
              csv(state.sessions, language),
              `senda-${t('sessionsFile')}-${dayKey(now)}.csv`,
              'text/csv;charset=utf-8',
            )
          }
        >
          <Icon name="download" size={18} />
          {t('exportCsv')}
        </button>
      </header>
      <Metrics state={state} allTime />
      <section className="week-section" aria-labelledby="week-title">
        <div className="section-heading">
          <h2 id="week-title">{t('lastWeek')}</h2>
          <span className="muted">
            {t('focusMinutes', {
              count: weekMinutes,
              unit: t(weekMinutes === 1 ? 'minute' : 'minutes'),
            })}
          </span>
        </div>
        <div
          className="week-chart"
          role="img"
          aria-label={stats.week
            .map((d) =>
              t('chartDay', {
                date: d.key,
                count: d.minutes,
                unit: t(d.minutes === 1 ? 'minute' : 'minutes'),
              }),
            )
            .join(', ')}
        >
          {stats.week.map((d) => (
            <div className={`chart-column ${d.today ? 'today' : ''}`} key={d.key}>
              <span className="bar-value">{d.minutes ? `${d.minutes} min` : '—'}</span>
              <div className="bar-track">
                <div className="chart-bar" style={{ height: `${(d.minutes / max) * 100}%` }} />
              </div>
              <span className="day-label">{d.today ? t('today') : d.label}</span>
            </div>
          ))}
        </div>
        <p className="small muted">
          {state.sessions.length ? t('historyExplanation') : t('firstSession')}
        </p>
      </section>
      <section className="history-section" aria-labelledby="history-title">
        <div className="section-heading">
          <h2 id="history-title">{t('sessionBySession')}</h2>
          <label className="history-filter">
            <span className="sr-only">{t('filterHistory')}</span>
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setLimit(30);
              }}
            >
              <option value="today">{t('todayFilter')}</option>
              <option value="week">{t('weekFilter')}</option>
              <option value="all">{t('allHistory')}</option>
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
                    <strong>{s.taskTitle || t('untitledSession')}</strong>
                    <time dateTime={new Date(s.completedAt).toISOString()}>
                      {new Date(s.completedAt).toLocaleString(locale, {
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
                {t('moreSessions')}
              </button>
            ) : null}
          </>
        ) : (
          <div className="history-empty">
            <Icon name="sound" size={25} />
            <p>{t('emptyHistory')}</p>
            <span className="muted small">{t('emptyHistoryBody')}</span>
          </div>
        )}
      </section>
    </main>
  );
}
