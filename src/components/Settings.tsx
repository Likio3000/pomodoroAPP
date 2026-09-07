import { errorText, UserError, type MessageKey } from '../i18n/messages';
import { useI18n } from '../i18n/context';
import { useRef, useState } from 'react';
import type { Backup, State } from '../domain/model';
import { parseBackup } from '../domain/model';
import { dispatch } from '../store';
import { unlockSound, chime } from '../sound';
import { dayKey } from '../domain/stats';
import { download } from './Progress';
import { Dialog } from './Dialog';
import { Icon } from './Icon';
export function Settings({ state, onClose }: { state: State; onClose: () => void }) {
  const { t, language } = useI18n();
  const [draft, setDraft] = useState(state.settings);
  const [error, setError] = useState<UserError | null>(null);
  const [restore, setRestore] = useState<Backup | null>(null);
  const [notice, setNotice] = useState<MessageKey | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const active = state.timer.status !== 'idle';
  return (
    <Dialog title={t('settingsTitle')} onClose={onClose} wide>
      <p className="dialog-copy">{t('settingsSubtitle')}</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (await dispatch({ type: 'settings', settings: draft })) onClose();
          else setError(new UserError('saveSettingsError'));
        }}
      >
        <fieldset disabled={active}>
          <legend>{t('durations')}</legend>
          <div className="duration-fields">
            {(
              [
                ['focus', t('focus'), 180],
                ['short', t('mode.short'), 60],
                ['long', t('mode.long'), 90],
              ] as const
            ).map(([key, label, max]) => (
              <label key={key}>
                {label}
                <span className="number-field">
                  <input
                    type="number"
                    min="1"
                    max={max}
                    step="1"
                    required
                    value={draft[key]}
                    onChange={(e) => setDraft({ ...draft, [key]: Number(e.target.value) })}
                  />{' '}
                  <span>min</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <p className="small muted">{active ? t('activeDurations') : t('longBreakHint')}</p>
        <label className="setting-row">
          <span>
            <strong>{t('dailyGoal')}</strong>
            <small>{t('goalHint')}</small>
          </span>
          <input
            aria-label={t('dailyGoal')}
            className="goal-input"
            type="number"
            min="1"
            max="16"
            step="1"
            required
            value={draft.goal}
            onChange={(e) => setDraft({ ...draft, goal: Number(e.target.value) })}
          />
        </label>
        <label className="setting-row">
          <span>
            <strong>{t('sound')}</strong>
            <small>{t('soundHint')}</small>
          </span>
          <input
            className="switch"
            type="checkbox"
            checked={draft.sound}
            onChange={(e) => {
              setDraft({ ...draft, sound: e.target.checked });
              if (e.target.checked) {
                unlockSound();
                setTimeout(chime, 100);
              }
            }}
          />
        </label>
        <div className="setting-row">
          <span>
            <strong>{t('notifications')}</strong>
            <small>{t('notificationsHint')}</small>
          </span>
          <button
            className="secondary compact"
            type="button"
            onClick={async () => {
              if (!('Notification' in window)) {
                setNotice('notificationsUnsupported');
                return;
              }
              try {
                const permission = await Notification.requestPermission();
                setNotice(
                  permission === 'granted' ? 'notificationsEnabled' : 'notificationsDisabled',
                );
              } catch {
                setNotice('notificationsFailed');
              }
            }}
          >
            {t('enableNotifications')}
          </button>
        </div>
        {notice ? (
          <p className="small muted" role="status">
            {t(notice)}
          </p>
        ) : null}
        <div className="backup-section">
          <h3>{t('yourData')}</h3>
          <p className="small muted">{t('dataExplanation')}</p>
          <div className="backup-actions">
            <button
              type="button"
              className="secondary compact"
              onClick={() =>
                download(
                  JSON.stringify(
                    {
                      version: 2,
                      language: state.language ?? 'es',
                      settings: state.settings,
                      tasks: state.tasks,
                      sessions: state.sessions,
                    },
                    null,
                    2,
                  ),
                  `senda-${t('backupFile')}-${dayKey(Date.now())}.json`,
                  'application/json',
                )
              }
            >
              <Icon name="download" size={16} />
              {t('saveBackup')}
            </button>
            <button type="button" className="text-button" onClick={() => fileRef.current?.click()}>
              {t('restoreBackup')}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".json,application/json"
              className="sr-only"
              tabIndex={-1}
              aria-label={t('backupInput')}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (!file) return;
                try {
                  if (file.size > 5_000_000) throw new UserError('backupSize');
                  setRestore(parseBackup(await file.text()));
                  setError(null);
                } catch (err) {
                  setError(err instanceof UserError ? err : new UserError('backupReadError'));
                }
              }}
            />
          </div>
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {errorText(language, error)}
          </p>
        ) : null}
        <div className="dialog-actions">
          <button type="button" className="text-button" onClick={onClose}>
            {t('cancel')}
          </button>
          <button className="primary">{t('saveSettings')}</button>
        </div>
      </form>
      {restore ? (
        <Dialog title={t('restoreTitle')} onClose={() => setRestore(null)}>
          <p className="dialog-copy">
            {t('restoreBody', { tasks: restore.tasks.length, sessions: restore.sessions.length })}
          </p>
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setRestore(null)}>
              {t('cancel')}
            </button>
            <button
              className="primary"
              onClick={async () => {
                if (await dispatch({ type: 'restore', data: restore })) {
                  setRestore(null);
                  onClose();
                }
              }}
            >
              {t('restoreData')}
            </button>
          </div>
        </Dialog>
      ) : null}
    </Dialog>
  );
}
