#!/bin/bash
set -e

echo ""
echo "══════════════════════════════════════════"
echo "  RomeoPHD v6.0 — Codespace Setup"
echo "══════════════════════════════════════════"
echo ""

# ─── 1. PostgreSQL ───────────────────────────────────────────
echo "▶ Starting PostgreSQL..."
sudo service postgresql start

echo "▶ Creating database user and schema..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='romeo'" \
  | grep -q 1 || sudo -u postgres psql -c "CREATE USER romeo WITH PASSWORD 'romeo';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='romeophi'" \
  | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE romeophi OWNER romeo;"

echo "✓ PostgreSQL ready (romeo@localhost:5432/romeophi)"
echo ""

# ─── 2. pnpm ─────────────────────────────────────────────────
echo "▶ Installing pnpm..."
npm install -g pnpm@latest --silent
echo "✓ pnpm $(pnpm --version)"
echo ""

# ─── 3. Dependencies ─────────────────────────────────────────
echo "▶ Installing workspace dependencies..."
pnpm install --frozen-lockfile
echo "✓ Dependencies installed"
echo ""

# ─── 4. Apply critical bug patches ───────────────────────────
echo "▶ Applying critical patches..."
node .devcontainer/patch.mjs
echo "✓ Patches applied"
echo ""

# ─── 5. DB migration ─────────────────────────────────────────
echo "▶ Running database migration (drizzle push)..."
pnpm --filter @workspace/db run push --accept-data-loss
echo "✓ Database schema applied"
echo ""

# ─── 6. .env file ────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "▶ Creating .env file..."
  cat > .env << 'EOF'
# ──────────────────────────────────────────────
# RomeoPHD v6.0 — Environment Variables
# ──────────────────────────────────────────────

DATABASE_URL=postgresql://romeo:romeo@localhost:5432/romeophi
PORT=3001
NODE_ENV=development

# Добавьте свой ключ из https://console.anthropic.com
ANTHROPIC_API_KEY=
EOF
  echo "✓ .env created — добавьте ANTHROPIC_API_KEY!"
else
  echo "✓ .env уже существует"
fi
echo ""

# ─── Done ────────────────────────────────────────────────────
echo "══════════════════════════════════════════"
echo "  ✓ Setup complete!"
echo ""
echo "  Следующий шаг:"
echo "  1. Откройте .env и вставьте ANTHROPIC_API_KEY"
echo "  2. Запустите: pnpm run dev"
echo "══════════════════════════════════════════"
echo ""
