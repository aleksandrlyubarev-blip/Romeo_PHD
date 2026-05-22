#!/usr/bin/env bash
#
# setup-vault.sh — разворачивает Obsidian vault "main-vault" на macOS.
#
# Что делает (всё, что можно автоматизировать из терминала):
#   - создаёт структуру папок в iCloud Drive
#   - пишет 6 Templater-шаблонов в 99-TEMPLATES/
#   - пишет CLAUDE.md, README архива, future-vault-upgrades.md, индекс skills
#   - пишет ~/scripts/overnight-dissertation.sh и ~/scripts/vault-backup.sh
#   - пишет launchd .plist для overnight-симуляции и weekly-бэкапа
#   - добавляет vault-алиасы в ~/.zshrc
#   - инициализирует git-репозиторий в vault
#
# Чего НЕ делает (только вручную в GUI/iOS — см. MANUAL-STEPS.md):
#   - установка community-плагинов, настройка Templater / Periodic Notes
#   - hotkeys, iPhone Shortcuts, привязка GitHub-remote
#
# Запуск:  bash setup-vault.sh
# Скрипт идемпотентный: повторный запуск НЕ перезаписывает уже существующие
# файлы (на случай, если вы успели их отредактировать).

set -euo pipefail

# ─────────────────────────── config ────────────────────────────
VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/main-vault"
SCRIPTS_DIR="$HOME/scripts"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
ZSHRC="$HOME/.zshrc"

# ─────────────────────────── helpers ───────────────────────────
info() { printf '\033[1;34m▶\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$1"; }
tilde() { case "$1" in "$HOME"/*) printf '~%s' "${1#"$HOME"}";; *) printf '%s' "$1";; esac; }

# write_if_absent <path> : пишет stdin в файл, только если файла ещё нет
write_if_absent() {
  local path="$1"
  if [ -e "$path" ]; then
    warn "пропуск (уже существует): $(tilde "$path")"
    cat >/dev/null
  else
    mkdir -p "$(dirname "$path")"
    cat > "$path"
    ok "создан: $(tilde "$path")"
  fi
}

# ─────────────────────── sanity checks ─────────────────────────
if [ "$(uname)" != "Darwin" ]; then
  warn "Это не macOS. Скрипт рассчитан на Mac — пути iCloud/launchd не сработают."
  read -r -p "Всё равно продолжить? [y/N] " a; [ "${a:-}" = "y" ] || exit 1
fi

ICLOUD_ROOT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents"
if [ ! -d "$HOME/Library/Mobile Documents" ]; then
  warn "iCloud Drive не найден (~/Library/Mobile Documents отсутствует)."
  warn "Включите System Settings → Apple Account → iCloud → iCloud Drive и повторите."
  exit 1
fi
mkdir -p "$ICLOUD_ROOT"

# ───────────────────── 1. структура папок ──────────────────────
info "Создаю структуру папок vault"
mkdir -p "$VAULT"/{00-INBOX,10-DAILY,40-RESOURCES,50-ARCHIVE,60-DECISIONS,99-TEMPLATES}
mkdir -p "$VAULT"/20-PROJECTS/{RoboQC,Dissertation,Flex-career}
mkdir -p "$VAULT"/20-PROJECTS/Dissertation/runs
mkdir -p "$VAULT"/30-AREAS/{Family,Languages,Health}
mkdir -p "$VAULT"/70-AGENTS/skills/{roboqc-fmea-review,roboqc-threshold-tune,roboqc-pilot-gate}
ok "структура папок готова"

# ───────────────────── 2. шесть шаблонов ───────────────────────
info "Пишу Templater-шаблоны в 99-TEMPLATES/"

write_if_absent "$VAULT/99-TEMPLATES/daily.md" <<'TPL_DAILY'
---
date: <% tp.date.now("YYYY-MM-DD") %>
energy:
sleep_hours:
mood:
---

# <% tp.date.now("YYYY-MM-DD, dddd") %>

## Цели на сегодня (max 3)

- [ ] **RoboQC:**
- [ ] **Dissertation:**
- [ ] **Other:**

## Что обнаружил

-

## Что отложил (parking lot)

-

## Decisions

-

## Воспоминание дня (1 строка)

>
TPL_DAILY

write_if_absent "$VAULT/99-TEMPLATES/project.md" <<'TPL_PROJECT'
---
status: active
created: <% tp.date.now("YYYY-MM-DD") %>
review_by:
---

# <% tp.file.title %>

## Цель (1 строка)



## Status
active | paused | archived

## Next 3 actions

1.
2.
3.

## Open questions

-

## Linked decisions

-

## Linked notes

-
TPL_PROJECT

write_if_absent "$VAULT/99-TEMPLATES/decision.md" <<'TPL_DECISION'
---
date: <% tp.date.now("YYYY-MM-DD") %>
revisit_by:
status: active
---

# Decision: <% tp.file.title %>

## Контекст



## Альтернативы рассмотренные

1.
2.
3.

## Решение



## Причина



## Что меняется в плане после этого

-

## Revisit by



## Linked
TPL_DECISION

write_if_absent "$VAULT/99-TEMPLATES/meeting.md" <<'TPL_MEETING'
---
date: <% tp.date.now("YYYY-MM-DD") %>
type: internal | customer | family
attendees:
---

# Meeting: <% tp.file.title %>

## Цель встречи



## Notes



## Action items

- [ ]
- [ ]

## Follow-up by

TPL_MEETING

write_if_absent "$VAULT/99-TEMPLATES/idea.md" <<'TPL_IDEA'
---
date: <% tp.date.now("YYYY-MM-DD") %>
status: parked | pursuing
---

# Idea: <% tp.file.title %>

## Идея (1-2 предложения)



## Зачем (problem solved)



## Why now / why not now



## Решение: park / pursue?

- [ ] park
- [ ] pursue

Если pursue — какой проект в `20-PROJECTS/` создать?
TPL_IDEA

write_if_absent "$VAULT/99-TEMPLATES/agent-prompt.md" <<'TPL_AGENT'
---
created: <% tp.date.now("YYYY-MM-DD") %>
agent: claude-code | codex | claude-chat
domain: roboqc | dissertation | obsidian | general
---

# Agent Prompt: <% tp.file.title %>

## Goal



## Context



## Constraints



## Expected output format



## Anti-patterns (что НЕ делать)

-
TPL_AGENT

# ───────────────── 3. CLAUDE.md в корне vault ───────────────────
info "Пишу CLAUDE.md"
write_if_absent "$VAULT/CLAUDE.md" <<'CLAUDE_MD'
# Vault Context for Claude Code

## Active projects (only touch these)

- 20-PROJECTS/RoboQC/ — handheld demo branch, target: 1 Sept demo
- 20-PROJECTS/Dissertation/ — β-NMR manuscript, target: P₀₀ overestimate fix
- 20-PROJECTS/Flex-career/ — CV, LinkedIn, Workday applications

## Archived (DO NOT modify until Q4 2026)

- 50-ARCHIVE/Andrew-Swarm/
- 50-ARCHIVE/PinoCut/
- 50-ARCHIVE/Notturno/
- 50-ARCHIVE/Огненная-Лапа/
- 50-ARCHIVE/Industrial-Intel/

## Naming conventions

- Daily notes: `YYYY-MM-DD.md` в `10-DAILY/`
- Decisions: `YYYY-MM-DD-short-name.md` в `60-DECISIONS/`
- Dissertation runs: `YYYY-MM-DD-HHMM-run-N.md` в `20-PROJECTS/Dissertation/runs/`

## Tone

Russian, short, no marketing. Direct technical statements only.

## Tools available

- Codex for overnight physics simulations
- Claude Code for source-level work in repos linked from project notes
- This vault for orchestration and decision history
CLAUDE_MD

# ───────────────── 4. README архива + future ────────────────────
info "Пишу README архива и заметку будущих апгрейдов"
write_if_absent "$VAULT/50-ARCHIVE/README.md" <<'ARCHIVE_README'
# 50-ARCHIVE — DO NOT TOUCH until Q4 2026

Эта папка — кладбище приостановленных треков. Правило одно:

> **Не открывать и не редактировать содержимое `50-ARCHIVE/` до Q4 2026.**

Любая работа здесь до сентября — это прокрастинация под видом продуктивности.
Реактивация — только осознанным решением, зафиксированным в `60-DECISIONS/`.

## Содержимое

- `Andrew-Swarm/` — routing-агенты для повторяющихся задач
- `PinoCut/`
- `Notturno/`
- `Огненная-Лапа/`
- `Industrial-Intel/`

## Будущие апгрейды vault

См. `future-vault-upgrades.md` — список вынесен сюда намеренно,
чтобы не отвлекал. Revisit Q4 2026.
ARCHIVE_README

write_if_absent "$VAULT/50-ARCHIVE/future-vault-upgrades.md" <<'FUTURE_MD'
---
status: parked
revisit_by: 2026-Q4
---

# Future vault upgrades — revisit Q4 2026

Не реализовывать до получения Sustain Engineer offer.

- MCP server для прямой интеграции Obsidian ↔ Claude (mcp-obsidian community server)
- Andrew Swarm reactivation — routing для повторяющихся задач из inbox
- Moltis integration — долгие автономные pipelines
- Dataview dashboard «week in review» с метриками по треку
- Sync на Mac Studio M4 Max (36GB) когда железо появится
FUTURE_MD

# ───────────────── 5. индекс skills ─────────────────────────────
write_if_absent "$VAULT/70-AGENTS/skills/README.md" <<'SKILLS_README'
# Skills index

Индекс RFV-skills для Claude Code / Codex. Одна строка описания на skill.

- `roboqc-fmea-review/` — review FMEA-таблиц на полноту и severity-консистентность
- `roboqc-threshold-tune/` — подбор порогов детектора по pilot-данным
- `roboqc-pilot-gate/` — gate-критерии перехода pilot → production

> Перенести сюда существующие skill-директории из текущего расположения.
SKILLS_README

# плейсхолдеры для quick-capture (hotkey + iPhone Shortcuts)
[ -e "$VAULT/00-INBOX/quick.md" ]      || { : > "$VAULT/00-INBOX/quick.md";      ok "создан: $(tilde "$VAULT/00-INBOX/quick.md")"; }
[ -e "$VAULT/00-INBOX/voice-inbox.md" ] || { : > "$VAULT/00-INBOX/voice-inbox.md"; ok "создан: $(tilde "$VAULT/00-INBOX/voice-inbox.md")"; }
[ -e "$VAULT/00-INBOX/ideas.md" ]      || { : > "$VAULT/00-INBOX/ideas.md";      ok "создан: $(tilde "$VAULT/00-INBOX/ideas.md")"; }
[ -e "$VAULT/60-DECISIONS/quick-log.md" ] || { : > "$VAULT/60-DECISIONS/quick-log.md"; ok "создан: $(tilde "$VAULT/60-DECISIONS/quick-log.md")"; }

# ───────────────── 6. overnight + backup scripts ────────────────
info "Пишу скрипты в $(tilde "$SCRIPTS_DIR")"
mkdir -p "$SCRIPTS_DIR"

write_if_absent "$SCRIPTS_DIR/overnight-dissertation.sh" <<'OVERNIGHT_SH'
#!/bin/bash
set -e

# ── ОТРЕДАКТИРОВАТЬ: абсолютный путь к репозиторию диссертации ──
DISSERTATION_REPO="$HOME/path/to/dissertation/repo"

VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/main-vault"
RUNS_DIR="$VAULT/20-PROJECTS/Dissertation/runs"
TIMESTAMP=$(date +%Y-%m-%d-%H%M)
LOG_FILE="$RUNS_DIR/$TIMESTAMP-overnight.md"

mkdir -p "$RUNS_DIR"

if [ ! -d "$DISSERTATION_REPO" ]; then
  echo "ОШИБКА: не найден DISSERTATION_REPO=$DISSERTATION_REPO" >&2
  echo "Отредактируйте переменную в начале overnight-dissertation.sh" >&2
  exit 1
fi

# Header
cat > "$LOG_FILE" <<EOF
---
date: $(date +%Y-%m-%d)
time: $(date +%H:%M)
type: overnight-simulation
status: running
---

# Overnight Dissertation Run $TIMESTAMP

## Parameters

- N_g: 20
- c: 0.1006
- H0: 200 G
- beta_0: 12.151
- beta_1: 11.144
- xi_0: 3, xi_j: 1

## Output

\`\`\`
EOF

# Run simulation
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate rwdm-research
cd "$DISSERTATION_REPO"

# caffeinate -i не даёт Mac уснуть, пока идёт симуляция
caffeinate -i python dzheparov_mps.py --Ng 20 --c 0.1006 --H0 200 >> "$LOG_FILE" 2>&1

# Footer
cat >> "$LOG_FILE" <<EOF
\`\`\`

## Status: completed

## Next analysis steps

- [ ] Compare P00(t→∞) vs DLS 1998
- [ ] Check pulse averaging hypothesis
- [ ] Validate normalization

EOF

# Notify
osascript -e "display notification \"Dissertation run completed: $TIMESTAMP\" with title \"Codex Overnight\""
OVERNIGHT_SH

write_if_absent "$SCRIPTS_DIR/vault-backup.sh" <<'BACKUP_SH'
#!/bin/bash
cd "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/main-vault" || exit 1
git add .
git commit -m "weekly snapshot $(date +%Y-%m-%d)" || echo "nothing to commit"
git push || echo "push skipped (remote не настроен?)"
BACKUP_SH

chmod +x "$SCRIPTS_DIR/overnight-dissertation.sh" "$SCRIPTS_DIR/vault-backup.sh"
ok "скрипты сделаны исполняемыми"

# ───────────────── 7. launchd .plist ────────────────────────────
info "Пишу launchd .plist в $(tilde "$LAUNCH_AGENTS")"
mkdir -p "$LAUNCH_AGENTS"

DISS_PLIST="$LAUNCH_AGENTS/com.larmor.dissertation.plist"
BACKUP_PLIST="$LAUNCH_AGENTS/com.larmor.vault-backup.plist"

write_if_absent "$DISS_PLIST" <<PLIST_DISS
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.larmor.dissertation</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPTS_DIR/overnight-dissertation.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardErrorPath</key>
    <string>$HOME/scripts/overnight-dissertation.err.log</string>
</dict>
</plist>
PLIST_DISS

write_if_absent "$BACKUP_PLIST" <<PLIST_BACKUP
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.larmor.vault-backup</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPTS_DIR/vault-backup.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardErrorPath</key>
    <string>$HOME/scripts/vault-backup.err.log</string>
</dict>
</plist>
PLIST_BACKUP

# загрузка launchd-агентов (unload перед load — на случай повторного запуска)
for p in "$DISS_PLIST" "$BACKUP_PLIST"; do
  launchctl unload "$p" 2>/dev/null || true
  if launchctl load -w "$p" 2>/dev/null; then
    ok "launchd загружен: $(tilde "$p")"
  else
    warn "launchctl load не сработал для $(tilde "$p") — загрузите вручную"
  fi
done

# ───────────────── 8. zsh-алиасы ────────────────────────────────
info "Добавляю vault-алиасы в ~/.zshrc"
ZMARKER="# >>> obsidian vault aliases >>>"
if [ -f "$ZSHRC" ] && grep -qF "$ZMARKER" "$ZSHRC"; then
  warn "алиасы уже есть в ~/.zshrc — пропуск"
else
  cat >> "$ZSHRC" <<'ZSHRC_BLOCK'

# >>> obsidian vault aliases >>>
export OBSIDIAN_VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/main-vault"
alias vault='cd "$OBSIDIAN_VAULT"'
alias claude-vault='vault && claude'
alias daily="open \"$OBSIDIAN_VAULT/10-DAILY/\$(date +%Y-%m-%d).md\""
# <<< obsidian vault aliases <<<
ZSHRC_BLOCK
  ok "алиасы добавлены в ~/.zshrc (выполните: source ~/.zshrc)"
fi

# ───────────────── 9. git init в vault ──────────────────────────
info "Инициализирую git-репозиторий в vault"
cd "$VAULT"
if [ -d .git ]; then
  warn "git-репозиторий уже существует — пропуск init"
else
  git init -q
  cat > .gitignore <<'GITIGNORE'
.obsidian/workspace*
.obsidian/cache
.trash/
.DS_Store
GITIGNORE
  if git config user.email >/dev/null 2>&1; then
    git add .
    git commit -q -m "initial vault setup"
    ok "git-репозиторий создан, первый коммит сделан"
  else
    warn "git user.email не настроен — .gitignore создан, но коммит пропущен."
    warn "Настройте git config user.name/user.email и сделайте коммит вручную."
  fi
fi

# ───────────────────────── итог ─────────────────────────────────
echo
ok "Автоматическая часть завершена."
echo
echo "Vault: $(tilde "$VAULT")"
echo
echo "ОСТАЛОСЬ ВРУЧНУЮ (см. MANUAL-STEPS.md):"
echo "  1. Установить Obsidian, открыть vault main-vault по пути выше."
echo "  2. Community plugins: Templater, Periodic Notes, Advanced URI, QuickAdd, Dataview."
echo "  3. Настроить Templater (folder template для 10-DAILY) и Periodic Notes."
echo "  4. Назначить hotkeys."
echo "  5. Создать 3 iPhone Shortcuts (voice / decision / idea)."
echo "  6. Отредактировать DISSERTATION_REPO в ~/scripts/overnight-dissertation.sh."
echo "  7. Создать private GitHub-репо obsidian-vault и привязать remote."
echo "  8. Пройти sync-test и acceptance criteria."
echo
