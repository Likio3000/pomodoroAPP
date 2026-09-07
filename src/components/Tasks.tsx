import { useI18n } from '../i18n/context';
import { useState, type FormEvent } from 'react';
import type { State, Task } from '../domain/model';
import { statistics } from '../domain/stats';
import { dispatch } from '../store';
import { Icon } from './Icon';
import { Dialog } from './Dialog';
function TaskRow({
  task,
  selected,
  onEdit,
}: {
  task: Task;
  selected: boolean;
  onEdit: () => void;
}) {
  const { t } = useI18n();
  return (
    <li className={`task-row ${selected ? 'selected' : ''} ${task.done ? 'done' : ''}`}>
      <button
        className="task-check"
        aria-label={t(task.done ? 'reopenTask' : 'completeTask', { title: task.title })}
        aria-pressed={task.done}
        onClick={() => void dispatch({ type: 'done', id: task.id })}
      >
        {task.done ? <Icon name="check" size={16} /> : null}
      </button>
      <button
        className="task-select"
        disabled={task.done}
        aria-pressed={selected}
        onClick={() => void dispatch({ type: 'select', id: selected ? null : task.id })}
      >
        <span>{task.title}</span>
        <small>
          {task.sessions
            ? `${task.sessions} ${task.sessions === 1 ? t('session') : t('sessions')}`
            : selected
              ? t('nextFocus')
              : t('selectTask')}
        </small>
      </button>
      <button
        className="icon-button task-edit"
        aria-label={t('editTask', { title: task.title })}
        onClick={onEdit}
      >
        <Icon name="edit" size={17} />
      </button>
    </li>
  );
}
export function Tasks({ state }: { state: State }) {
  const { t, language } = useI18n();
  const [text, setText] = useState('');
  const [editing, setEditing] = useState<Task | null>(null);
  const [draft, setDraft] = useState('');
  const [showDone, setShowDone] = useState(false);
  const pending = state.tasks.filter((t) => !t.done);
  const done = state.tasks.filter((t) => t.done);
  const today = statistics(state.sessions, Date.now(), language).today.length;
  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    if (await dispatch({ type: 'add', title: text, id: crypto.randomUUID() })) setText('');
  };
  return (
    <aside className="task-rail" aria-labelledby="tasks-title">
      <div className="task-area">
        <div className="section-heading">
          <h2 id="tasks-title">{t('nextStep')}</h2>
          <span className="task-count">{pending.length}</span>
        </div>
        <p className="muted rail-subtitle">{t('taskSubtitle')}</p>
        <form className="add-task" onSubmit={add}>
          <label className="sr-only" htmlFor="task-input">
            {t('taskPrompt')}
          </label>
          <input
            id="task-input"
            placeholder={t('taskPrompt')}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={160}
            autoComplete="off"
          />
          <button className="primary add-button" aria-label={t('addTask')} disabled={!text.trim()}>
            <Icon name="plus" size={25} />
          </button>
        </form>
        {pending.length ? (
          <ul className="task-list">
            {pending.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                selected={task.id === state.selectedTask}
                onEdit={() => {
                  setEditing(task);
                  setDraft(task.title);
                }}
              />
            ))}
          </ul>
        ) : (
          <div className="task-empty">
            <span className="empty-symbol">
              <Icon name="check" size={40} />
            </span>
            <h3>{done.length ? t('allDone') : t('emptyTask')}</h3>
            <p>{done.length ? t('allDoneBody') : t('emptyTaskBody')}</p>
          </div>
        )}
        {done.length ? (
          <div className="completed-tasks">
            <button
              className="text-button"
              onClick={() => setShowDone(!showDone)}
              aria-expanded={showDone}
            >
              {t(showDone ? 'hideCompleted' : 'showCompleted', { count: done.length })}
            </button>
            {showDone ? (
              <ul className="task-list">
                {done.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    selected={false}
                    onEdit={() => {
                      setEditing(task);
                      setDraft(task.title);
                    }}
                  />
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="daily-goal">
        <div className="section-heading">
          <h2>{t('todayRhythm')}</h2>
          <span>{t('goalProgress', { count: today, goal: state.settings.goal })}</span>
        </div>
        <div
          className="goal-segments"
          role="progressbar"
          aria-label={t('dailyGoal')}
          aria-valuemin={0}
          aria-valuemax={state.settings.goal}
          aria-valuenow={Math.min(today, state.settings.goal)}
        >
          {Array.from({ length: state.settings.goal }, (_, i) => (
            <span key={i} className={i < today ? 'filled' : ''} />
          ))}
        </div>
        <p className="muted">{today >= state.settings.goal ? t('goalMet') : t('everySession')}</p>
      </div>
      {editing ? (
        <Dialog title={t('intention')} onClose={() => setEditing(null)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (await dispatch({ type: 'rename', id: editing.id, title: draft }))
                setEditing(null);
            }}
          >
            <label className="field-label" htmlFor="edit-task">
              {t('task')}
            </label>
            <input
              id="edit-task"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={160}
              required
              autoFocus
            />
            <p className="muted small">{t('originalTitle')}</p>
            <div className="dialog-actions spread">
              <button
                type="button"
                className="text-button danger"
                onClick={() => {
                  void dispatch({ type: 'delete', id: editing.id });
                  setEditing(null);
                }}
              >
                <Icon name="trash" size={17} />
                {t('deleteTask')}
              </button>
              <button className="primary" disabled={!draft.trim()}>
                {t('save')}
              </button>
            </div>
          </form>
        </Dialog>
      ) : null}
    </aside>
  );
}
