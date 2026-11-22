const translations = {
  heading: ['Защитный шаблон', 'Defence template', 'Verteidigungsvorlage'],
  assignment: ['Защита', 'Defence', 'Verteidigung'],
  none: ['Без назначения', 'Unassigned', 'Nicht zugewiesen'],
  empty: ['Назначений нет', 'No assignments', 'Keine Zuweisungen'],
  unavailable: ['Недоступная территория', 'Unavailable territory', 'Nicht verfügbares Gebiet'],
  save: ['Сохранить шаблон', 'Save template', 'Vorlage speichern'],
  saving: ['Сохранение...', 'Saving...', 'Wird gespeichert...'],
  saved: ['Шаблон сохранён', 'Template saved', 'Vorlage gespeichert'],
  dirty: ['Есть несохранённые назначения', 'Unsaved assignments', 'Ungespeicherte Zuweisungen'],
  reload: ['Обновить шаблон', 'Reload template', 'Vorlage neu laden'],
  refresh: ['Обновить', 'Reload', 'Neu laden'],
  discard: ['Заменить несохранённый шаблон?', 'Discard unsaved template?', 'Ungespeicherte Vorlage verwerfen?'],
  cancel: ['Отмена', 'Cancel', 'Abbrechen'],
  conflict: ['Шаблон изменён или редактирование закрыто. Ваш вариант сохранён на экране.', 'The template changed or editing closed. Your draft remains on screen.', 'Die Vorlage wurde geändert oder die Bearbeitung beendet. Dein Entwurf bleibt sichtbar.'],
  failed: ['Не удалось сохранить шаблон. Ваш вариант сохранён на экране.', 'Could not save the template. Your draft remains on screen.', 'Die Vorlage konnte nicht gespeichert werden. Dein Entwurf bleibt sichtbar.'],
  reloadFailed: ['Не удалось обновить шаблон.', 'Could not reload the template.', 'Die Vorlage konnte nicht neu geladen werden.'],
};

export function defenceTemplateMessage(key, language = 'ru') {
  return translations[key]?.[({ ru: 0, en: 1, de: 2 })[language] ?? 0] || key;
}
