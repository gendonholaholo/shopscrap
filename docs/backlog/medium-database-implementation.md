# Backlog: Database Implementation

## Priority: MEDIUM

## Overview

Implementasi PostgreSQL database untuk menggantikan JSON file storage dan in-memory job queue.

---

## Problem Statement

```
KONDISI SAAT INI

1. Session/cookies disimpan di JSON file (./data/sessions/)
2. Job queue bersifat in-memory (hilang saat restart)
3. Tidak ada persistence untuk jobs

SOLUSI

PostgreSQL + SQLAlchemy + Alembic untuk:
- Session persistence
- Job persistence (survive restart)
```

---

## Implementation Status

### Dependencies - READY (sudah ada di pyproject.toml)

- [x] `sqlalchemy>=2.0.0`
- [x] `aiosqlite>=0.19.0` (akan diganti asyncpg)
- [ ] `asyncpg` (PostgreSQL async driver)
- [ ] `alembic` (migration tool)

### Database Setup - PENDING

- [ ] Setup PostgreSQL di docker-compose
- [ ] Konfigurasi database connection
- [ ] Setup Alembic untuk migrations

### Models - PENDING

- [ ] `sessions` table
- [ ] `jobs` table

### Migration - PENDING

- [ ] Initial migration script
- [ ] Migration commands di Makefile

### Integration - PENDING

- [ ] Update `SessionManager` untuk pakai DB
- [ ] Update `JobQueue` untuk pakai DB
- [ ] Update API endpoints

---

## Database Schema

```
┌─────────────────────────┐       ┌─────────────────────────┐
│        sessions         │       │          jobs           │
├─────────────────────────┤       ├─────────────────────────┤
│ id            UUID PK   │       │ id            UUID PK   │
│ cookies       JSONB     │       │ type          VARCHAR   │
│ source        VARCHAR   │       │ status        VARCHAR   │
│ uploaded_at   TIMESTAMP │       │ params        JSONB     │
│ expires_at    TIMESTAMP │       │ result        JSONB     │
│ is_valid      BOOLEAN   │       │ error         TEXT      │
│ created_at    TIMESTAMP │       │ progress      INT       │
│ updated_at    TIMESTAMP │       │ created_at    TIMESTAMP │
└─────────────────────────┘       │ started_at    TIMESTAMP │
                                  │ completed_at  TIMESTAMP │
                                  └─────────────────────────┘
```

---

## Technical Decisions

| Item | Keputusan | Alasan |
|------|-----------|--------|
| Database | PostgreSQL | Production-ready, JSONB support |
| ORM | SQLAlchemy 2.0 | Async support, type hints |
| Migration | Alembic | Standard untuk SQLAlchemy |
| JSONB | Ya (params, result, cookies) | Flexible, tidak perlu migrate terus |
| Soft delete | Tidak | Jobs tidak perlu di-recover |
| Table products | Tidak (untuk sekarang) | Over-engineering |
| Table scrape_history | Tidak (untuk sekarang) | Over-engineering |

---

## Folder Structure (Planned)

```
src/shopee_scraper/
├── database/
│   ├── __init__.py
│   ├── config.py          # Database URL, settings
│   ├── session.py         # Async session factory
│   └── models/
│       ├── __init__.py
│       ├── base.py        # Base model (id, timestamps)
│       ├── session.py     # Session model
│       └── job.py         # Job model

alembic/
├── alembic.ini
├── env.py
└── versions/
    └── 001_initial_tables.py
```

---

## Environment Variables

```bash
# Sudah ada di .env
DB_ENABLED=false
DB_HOST=localhost
DB_PORT=5432
DB_USER=shopee
DB_PASSWORD=shopee_secret
DB_NAME=shopee_data

# Akan generate URL:
# postgresql+asyncpg://shopee:shopee_secret@localhost:5432/shopee_data
```

---

## Docker Compose Addition (Planned)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: shopee
      POSTGRES_PASSWORD: shopee_secret
      POSTGRES_DB: shopee_data
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

---

## Migration Commands (Planned)

```bash
# Generate migration
make db-migrate message="add sessions table"

# Run migrations
make db-upgrade

# Rollback
make db-downgrade
```

---

## Future Extensions (Opsional)

Jika dibutuhkan nanti:

1. **Table `products`** - Cache scraped products untuk analytics
2. **Table `scrape_history`** - Tracking & audit trail
3. **Table `users`** - Multi-user support
4. **Table `api_keys`** - API key management di DB

---

## Notes

- Jangan gunakan SQLite (tidak production-ready untuk concurrent access)
- Gunakan `asyncpg` bukan `psycopg2` untuk async support
- JSONB lebih baik dari JSON (indexable, faster)
- Pastikan ada connection pooling untuk production
