# MANUAL-STEPS — что делается только руками

`setup-vault.sh` создаёт всю файловую часть vault. Ниже — шаги, которые
нельзя автоматизировать из терминала: GUI Obsidian и iPhone. Порядок —
как в ТЗ.

---

## 0. Prerequisites (до запуска скрипта)

```bash
xcode-select --install          # если ещё не стоит
brew install --cask obsidian    # или скачать с https://obsidian.md
```

iCloud Drive должен быть включён: System Settings → Apple Account →
iCloud → iCloud Drive → ON.

Первый запуск Obsidian: отказаться от Catalyst/Sync (платно, не нужно),
отказаться от welcome vault.

---

## 1. Открыть vault

Скрипт уже создал папку. В Obsidian: **Open folder as vault** →

```
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/main-vault
```

---

## 2. Community plugins (Этап 2 ТЗ)

Settings → Community plugins → Turn on community plugins → Browse.

Обязательные (5): **Templater**, **Periodic Notes**, **Advanced URI**,
**QuickAdd**, **Dataview**.

Опциональные (2, по необходимости): **Excalidraw**, **Tasks**.

Не ставить в первый месяц: Calendar, Day Planner, Kanban, Outliner,
Mind Map, Canvas as Database, любые dashboard-плагины. Максимум 7 плагинов.

---

## 3. Templater (Этап 4 ТЗ)

Settings → Templater:

- Template folder location: `99-TEMPLATES`
- Trigger Templater on new file creation: **ON**
- Folder templates → добавить запись:
  - Folder: `10-DAILY`
  - Template: `99-TEMPLATES/daily.md`

---

## 4. Periodic Notes (Этап 5 ТЗ)

Settings → Periodic Notes → Daily Notes:

- Enabled
- Date format: `YYYY-MM-DD`
- New file location: `10-DAILY`
- Template file location: `99-TEMPLATES/daily.md`
- Weekly Notes: **Off**

---

## 5. Hotkeys (Этап 6 ТЗ)

Settings → Hotkeys:

| Hotkey | Действие |
|---|---|
| `Cmd+Shift+D` | Periodic Notes: Open today's daily note |
| `Cmd+Shift+I` | Open `00-INBOX/quick.md` (файл уже создан скриптом) |
| `Cmd+Shift+N` | QuickAdd: New note from template |
| `Cmd+Shift+F` | Search in all files |

---

## 6. iPhone Shortcuts (Этап 7 ТЗ)

Приложение Shortcuts на iPhone. Три шортката, у всех логика одинаковая:
Dictate Text → Get Current Date (`YYYY-MM-DD HH:mm`) → Text → Append to File
(iCloud Drive).

| Shortcut | Path для Append to File | Префикс |
|---|---|---|
| Voice to Obsidian Inbox | `Obsidian/main-vault/00-INBOX/voice-inbox.md` | — |
| Quick Decision Log | `Obsidian/main-vault/60-DECISIONS/quick-log.md` | — |
| Idea Capture | `Obsidian/main-vault/00-INBOX/ideas.md` | `[IDEA]` |

Шаблон строки для шага Text:

```
\n\n## {Current Date}\n\n{Dictated Text}\n\n---\n
```

Voice-шорткат: Add to Home Screen → виджет.

---

## 7. Скрипт overnight-симуляции

Откройте `~/scripts/overnight-dissertation.sh` и отредактируйте строку:

```bash
DISSERTATION_REPO="$HOME/path/to/dissertation/repo"
```

указав реальный путь к репозиторию с `dzheparov_mps.py`.

launchd-агенты (`com.larmor.dissertation`, `com.larmor.vault-backup`) уже
загружены скриптом. Проверка:

```bash
launchctl list | grep larmor
```

Запуск симуляции прямо сейчас для теста:

```bash
bash ~/scripts/overnight-dissertation.sh
```

Если Mac ночью с закрытой крышкой — overnight-скрипт уже использует
`caffeinate -i`, чтобы система не уснула во время симуляции.

---

## 8. GitHub backup (Этап 10.2 ТЗ)

Скрипт уже сделал `git init` и первый коммит в vault. Осталось привязать
remote:

1. Создать **private** репозиторий на GitHub под именем `obsidian-vault`.
2. В терминале:

```bash
cd "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/main-vault"
git remote add origin git@github.com:USER/obsidian-vault.git
git branch -M main
git push -u origin main
```

Weekly-бэкап по воскресеньям 23:00 уже настроен через launchd
(`com.larmor.vault-backup`).

---

## Acceptance criteria (Этап ТЗ)

- [ ] `Cmd+Shift+D` открывает сегодняшнюю daily note с заполненным шаблоном
- [ ] Voice memo с iPhone появляется в `00-INBOX/voice-inbox.md` за < 2 минуты
- [ ] `claude-vault` запускает Claude Code в каталоге vault, видит `CLAUDE.md`
- [ ] Тестовая overnight-симуляция записала результат в `.../Dissertation/runs/`
- [ ] `Cmd+Shift+F` находит контент по поиску
- [ ] GitHub backup настроен, первый push прошёл
- [ ] Все 6 templates созданы и Templater их подставляет
- [ ] `50-ARCHIVE/` содержит README с правилом «do not touch until Q4 2026»

После закрытия всех пунктов — никаких доработок vault до сентября.
