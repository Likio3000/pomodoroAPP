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
  const [draft, setDraft] = useState(state.settings);
  const [error, setError] = useState('');
  const [restore, setRestore] = useState<Backup | null>(null);
  const [notice, setNotice] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const active = state.timer.status !== 'idle';
  return (
    <Dialog title="Encuentra tu ritmo." onClose={onClose} wide>
      <p className="dialog-copy">
        Un poco de estructura. Todo el espacio para hacerlo a tu manera.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (await dispatch({ type: 'settings', settings: draft })) onClose();
          else
            setError(
              'No se pudieron guardar los ajustes. Comprueba los valores y el estado de la sesión.',
            );
        }}
      >
        <fieldset disabled={active}>
          <legend>Duración de las sesiones</legend>
          <div className="duration-fields">
            {(
              [
                ['focus', 'Enfoque', 180],
                ['short', 'Pausa corta', 60],
                ['long', 'Pausa larga', 90],
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
        <p className="small muted">
          {active
            ? 'Reinicia o termina la sesión para cambiar las duraciones.'
            : 'Después de cuatro enfoques, te proponemos una pausa larga.'}
        </p>
        <label className="setting-row">
          <span>
            <strong>Objetivo diario</strong>
            <small>Una orientación, no una obligación.</small>
          </span>
          <input
            aria-label="Objetivo diario"
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
            <strong>Un sonido al terminar</strong>
            <small>Un aviso suave para cambiar de ritmo.</small>
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
            <strong>Avisos del navegador</strong>
            <small>Se piden solo si los activas.</small>
          </span>
          <button
            className="secondary compact"
            type="button"
            onClick={async () => {
              if (!('Notification' in window)) {
                setNotice('Este navegador no admite estos avisos.');
                return;
              }
              try {
                const permission = await Notification.requestPermission();
                setNotice(
                  permission === 'granted'
                    ? 'Avisos activados. Puedes desactivarlos en los ajustes del navegador.'
                    : 'Avisos desactivados. El temporizador seguirá funcionando.',
                );
              } catch {
                setNotice('No se han podido activar los avisos en este navegador.');
              }
            }}
          >
            Activar avisos
          </button>
        </div>
        {notice ? (
          <p className="small muted" role="status">
            {notice}
          </p>
        ) : null}
        <div className="backup-section">
          <h3>Tus datos, contigo.</h3>
          <p className="small muted">
            Todo se guarda en este navegador y dispositivo. Exporta una copia antes de borrar sus
            datos o cambiar de navegador. No hay sincronización en la nube.
          </p>
          <div className="backup-actions">
            <button
              type="button"
              className="secondary compact"
              onClick={() =>
                download(
                  JSON.stringify(
                    {
                      version: 2,
                      settings: state.settings,
                      tasks: state.tasks,
                      sessions: state.sessions,
                    },
                    null,
                    2,
                  ),
                  `pomodoro-copia-${dayKey(Date.now())}.json`,
                  'application/json',
                )
              }
            >
              <Icon name="download" size={16} />
              Guardar copia
            </button>
            <button type="button" className="text-button" onClick={() => fileRef.current?.click()}>
              Restaurar copia
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".json,application/json"
              className="sr-only"
              tabIndex={-1}
              aria-label="Archivo de copia de seguridad"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (!file) return;
                try {
                  if (file.size > 5_000_000) throw new Error('La copia supera el límite de 5 MB.');
                  setRestore(parseBackup(await file.text()));
                  setError('');
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'No se ha podido leer la copia.');
                }
              }}
            />
          </div>
        </div>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialog-actions">
          <button type="button" className="text-button" onClick={onClose}>
            Cancelar
          </button>
          <button className="primary">Guardar ajustes</button>
        </div>
      </form>
      {restore ? (
        <Dialog title="¿Restaurar esta copia?" onClose={() => setRestore(null)}>
          <p className="dialog-copy">
            Se reemplazarán tus tareas, ajustes e historial por {restore.tasks.length} tareas y{' '}
            {restore.sessions.length} sesiones de la copia. El temporizador se reiniciará. Guarda
            una copia de tus datos actuales si quieres conservarlos.
          </p>
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setRestore(null)}>
              Cancelar
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
              Restaurar datos
            </button>
          </div>
        </Dialog>
      ) : null}
    </Dialog>
  );
}
