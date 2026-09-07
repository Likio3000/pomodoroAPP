import 'fake-indexeddb/auto';
import { describe, expect, it } from 'vitest';
import { initialState, parseBackup, reduce, type State } from '../src/domain/model';
import { openDatabase, transaction } from '../src/domain/database';
import { csv, statistics } from '../src/domain/stats';
import { en, es, errorText, translate, UserError, type MessageKey } from '../src/i18n/messages';

describe('language without interrupting focus', () => {
  it('keeps a running timer and task attribution intact when switching languages', () => {
    const task = reduce(initialState(), { type: 'add', id: 'task', title: 'Mi intención' }, 1000);
    const running = reduce(task, { type: 'toggle' }, 2000);
    const english = reduce(running, { type: 'language', language: 'en' }, 10_000);
    expect(english.language).toBe('en');
    expect(english.timer).toBe(running.timer);
    expect(english.tasks).toBe(running.tasks);
    expect(english.sessions).toBe(running.sessions);
    expect(english.selectedTask).toBe(running.selectedTask);
  });
  it('keeps the language when an already open settings form is saved', () => {
    const state = initialState();
    const english = reduce(state, { type: 'language', language: 'en' }, 1000);
    expect(reduce(english, { type: 'settings', settings: state.settings }, 1001).language).toBe(
      'en',
    );
  });
  it('loads an existing record without a language and persists the choice across connections', async () => {
    const name = crypto.randomUUID();
    const db = await openDatabase(name);
    const legacy: State = reduce(initialState(), { type: 'toggle' }, Date.now());
    delete legacy.language;
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('app', 'readwrite');
      tx.objectStore('app').put(legacy, 'state');
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    const result = await transaction(db, { type: 'language', language: 'en' });
    expect(result.state.timer).toEqual(legacy.timer);
    db.close();
    const reopened = await openDatabase(name);
    expect((await transaction(reopened)).state.language).toBe('en');
    reopened.close();
  });
  it('preserves language in backups and accepts old backups without it', () => {
    const state = initialState();
    expect(parseBackup(JSON.stringify({ ...state, language: 'en' })).language).toBe('en');
    const legacy = { ...state };
    delete legacy.language;
    expect(parseBackup(JSON.stringify(legacy)).language).toBe('es');
    expect(() => parseBackup(JSON.stringify({ ...state, language: 'fr' }))).toThrow();
  });
});
describe('complete, reactive translations', () => {
  it('covers the same placeholders in both languages', () => {
    for (const key of Object.keys(es) as MessageKey[]) {
      expect(en[key].trim()).not.toBe('');
      expect(en[key].match(/\{\w+\}/g)?.sort() ?? []).toEqual(
        es[key].match(/\{\w+\}/g)?.sort() ?? [],
      );
    }
  });
  it('preserves user text verbatim during interpolation', () => {
    expect(translate('en', 'completeTask', { title: 'Revisar {count}' })).toBe(
      'Complete: Revisar {count}',
    );
  });
  it('renders the same error in the selected language, including setting names', () => {
    const error = new UserError('settingRange', { field: 'short', max: 60 });
    expect(errorText('en', error)).toBe('Check Short break: it must be between 1 and 60.');
    expect(errorText('es', error)).toBe('Revisa Pausa corta: debe estar entre 1 y 60.');
    expect(errorText('en', new Error('Untranslated internal detail'))).toContain('Could not save');
  });
  it('changes calendar labels and CSV headers without changing numeric results', () => {
    const now = new Date(2026, 8, 7, 12).getTime();
    const sessions = [
      { id: 'session', completedAt: now, duration: 1_500_000, taskTitle: 'Texto original' },
    ];
    const spanish = statistics(sessions, now, 'es');
    const english = statistics(sessions, now, 'en');
    expect(english.week.at(-1)?.label).toBe('Mon');
    expect(spanish.week.at(-1)?.label).toBe('lun');
    expect(english.totalMinutes).toBe(spanish.totalMinutes);
    expect(csv(sessions, 'en')).toContain('iso_date,task,minutes');
    expect(csv(sessions, 'en')).toContain('Texto original');
  });
});
