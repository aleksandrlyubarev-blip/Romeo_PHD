---
created: 2026-05-22
agent: codex
domain: obsidian
---

# Agent Prompt: Завершить развёртывание Obsidian vault на Mac

## Goal

Довести до конца развёртывание Obsidian vault `main-vault` на этом
MacBook (M5 Pro, macOS) по ТЗ Q3 2026. Закрыть все acceptance criteria.

## Context

Vault — central nervous system для координации треков RoboQC,
диссертация (β-NMR), Flex-карьера. Цель — рабочий инструмент на июль-август,
не «второй мозг». Бюджет ₪0.

Деплой-комплект уже создан и лежит в репозитории `Romeo_PHD`, ветка
`claude/obsidian-vault-setup-f63Oj`, папка `obsidian-vault-setup/`:

- `setup-vault.sh` — идемпотентный скрипт, создаёт файловую часть vault
- `MANUAL-STEPS.md` — чек-лист ручных GUI/iOS-шагов + acceptance criteria

`setup-vault.sh` создаёт: структуру папок в iCloud Drive
(`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/main-vault`),
6 Templater-шаблонов, `CLAUDE.md`, README архива, скрипты
`~/scripts/overnight-dissertation.sh` и `~/scripts/vault-backup.sh`,
два launchd `.plist`, vault-алиасы в `~/.zshrc`, `git init` + первый коммит.

## Constraints

- Только бесплатные инструменты. Никаких Obsidian Sync / Catalyst.
- Не больше 7 community-плагинов в первый месяц.
- Не трогать содержимое `50-ARCHIVE/` — revisit Q4 2026.
- Никаких Dataview-дашбордов, CSS-снипетов, миграции из Notion.
- Папки не глубже 3 уровней, теги не глубже 2.
- Tone заметок: русский, коротко, без маркетинга.

## Задачи, которые ты (Codex) можешь сделать в терминале

1. Запустить `bash obsidian-vault-setup/setup-vault.sh`, проверить вывод.
2. В `~/scripts/overnight-dissertation.sh` заменить плейсхолдер
   `DISSERTATION_REPO="$HOME/path/to/dissertation/repo"` на реальный путь
   к репозиторию с `dzheparov_mps.py` (спросить пользователя, если неизвестен).
3. Проверить launchd: `launchctl list | grep larmor` — должны быть
   `com.larmor.dissertation` и `com.larmor.vault-backup`.
4. Прогнать тестовую overnight-симуляцию: `bash ~/scripts/overnight-dissertation.sh`,
   убедиться, что результат записан в `.../20-PROJECTS/Dissertation/runs/`.
5. Привязать git-remote: создать private-репо `obsidian-vault` на GitHub
   (через `gh repo create` или попросить пользователя), затем в каталоге
   vault `git remote add origin ...`, `git push -u origin main`.
6. Sync-test: создать `00-INBOX/sync-test.md`, попросить пользователя
   проверить файл в Obsidian iOS за < 5 минут.

## Задачи только для человека (агент сделать не может)

В GUI Obsidian — см. `MANUAL-STEPS.md` разделы 2-5:
установка 5 community-плагинов, настройка Templater (folder template
для `10-DAILY`) и Periodic Notes, hotkeys.
На iPhone — раздел 6: 3 шортката (voice / decision / idea).
Эти шаги озвучь пользователю как его зону ответственности.

## Expected output format

Чек-лист acceptance criteria с отметками сделано/осталось:

- [ ] `Cmd+Shift+D` открывает daily note с заполненным шаблоном
- [ ] Voice memo с iPhone → `00-INBOX/voice-inbox.md` за < 2 минуты
- [ ] `claude-vault` запускает Claude Code в каталоге vault, видит `CLAUDE.md`
- [ ] Тестовая overnight-симуляция записала результат в `Dissertation/runs/`
- [ ] `Cmd+Shift+F` находит контент по поиску
- [ ] GitHub backup настроен, первый push прошёл
- [ ] Все 6 templates созданы, Templater их подставляет
- [ ] `50-ARCHIVE/` содержит README с правилом «do not touch until Q4 2026»

## Anti-patterns (что НЕ делать)

- НЕ перезаписывать уже отредактированные пользователем файлы vault.
- НЕ ставить лишние плагины, не строить дашборды, не «оптимизировать»
  структуру vault — после деплоя zero доработок до сентября.
- НЕ открывать и не менять `50-ARCHIVE/`.
- НЕ коммитить в vault секреты; `.gitignore` уже исключает `.obsidian/workspace*`.
- НЕ делать pull request без явной просьбы.
