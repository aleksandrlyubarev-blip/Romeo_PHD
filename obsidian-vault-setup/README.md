# obsidian-vault-setup

Развёртывание Obsidian vault `main-vault` на M5 Pro MacBook (ТЗ Q3 2026).

Эта папка — деплой-комплект. На Mac:

```bash
bash setup-vault.sh
```

Скрипт создаёт всю файловую часть vault в iCloud Drive (структура папок,
6 Templater-шаблонов, `CLAUDE.md`, README архива, скрипты overnight/backup,
launchd `.plist`, zsh-алиасы, git-репозиторий). Идемпотентен — повторный
запуск не перезаписывает уже существующие файлы.

Затем — `MANUAL-STEPS.md`: шаги, которые делаются только в GUI Obsidian и
на iPhone (плагины, Templater/Periodic Notes config, hotkeys, Shortcuts,
GitHub remote) — терминалом их не автоматизировать.

## Файлы

- `setup-vault.sh` — основной скрипт развёртывания
- `MANUAL-STEPS.md` — чек-лист ручных шагов + acceptance criteria

## Почему две части

ТЗ описывает Mac/iOS-окружение: iCloud Drive, GUI-плагины Obsidian,
iPhone Shortcuts, launchd. Всё, что доступно из терминала, собрано в
`setup-vault.sh`. Остальное физически требует GUI/iPhone и вынесено в
`MANUAL-STEPS.md`.
