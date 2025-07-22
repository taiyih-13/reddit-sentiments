# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Reddit-Sentiments is a real-time sentiment analysis system that monitors Reddit finance communities for S&P 500 stock mentions and analyzes sentiment using FinBERT. The system consists of microservices running via Docker Compose.

## Architecture

### Backend Services (Python)
- **collector.py**: Polls 11 finance subreddits every 5 minutes, extracts S&P 500 tickers, pushes to Redis streams
- **tasks.py**: Celery workers that consume Redis streams, run FinBERT sentiment analysis, store results in TimescaleDB
- **api.py**: FastAPI server providing REST endpoints (currently minimal)
- **db.py**: AsyncPG database connection pooling and query execution utilities

### Frontend (React + TypeScript)
- **Vite + React 19**: Located in `frontend/` directory, currently shows default Vite template
- **TypeScript**: Configured with strict settings

### Infrastructure
- **TimescaleDB**: Primary database with hypertables for time-series sentiment data
- **Redis**: Message broker for streaming posts between collector and workers
- **Celery**: Task queue system with beat scheduler for automated processing

## Common Commands

### Development Setup
```bash
# Start all services
docker compose up --build

# Start specific service
docker compose up postgres redis
```

### Frontend Development
```bash
cd frontend
npm run dev          # Start development server
npm run build        # Build for production  
npm run lint         # Run ESLint
```

### Backend Services
Individual services run via Docker Compose commands defined in docker-compose.yml:
- `collector`: `python collector.py`
- `worker`: `celery -A tasks worker --concurrency 2 --prefetch-multiplier 1 --loglevel=info`
- `beat`: `celery -A tasks beat --loglevel=info`
- `api`: `uvicorn api:app --host 0.0.0.0 --port 8000 --reload`

## Data Flow

1. **Collection**: collector.py fetches new posts from Reddit finance subreddits
2. **Streaming**: Posts with S&P 500 tickers pushed to Redis stream `raw_posts`
3. **Processing**: Celery workers consume stream, run FinBERT sentiment analysis
4. **Storage**: Sentiment scores stored in TimescaleDB `sentiment_events` table
5. **API**: FastAPI serves data to frontend (endpoints need implementation)

## Key Dependencies

### Python (app/requirements.txt)
- asyncpraw: Reddit API client
- transformers + torch: FinBERT model
- celery + redis: Task queue
- fastapi + uvicorn: Web API
- asyncpg: PostgreSQL async driver
- APScheduler: Task scheduling

### Frontend (frontend/package.json)
- React 19 + TypeScript
- Vite build system
- ESLint for linting

## Database Schema

**sentiment_events** (TimescaleDB hypertable):
- Primary key: `id` (bigserial)
- Foreign data: `reddit_id`, `ticker`, `model`
- Sentiment: `score`, `pos_prob`, `neg_prob`  
- Timestamps: `created_ts` (post time), `scored_ts` (analysis time)

## Environment Variables

Required in `.env` file:
- Reddit API: `RID`, `RSEC`, `RUSERAGENT`
- Database: `PG_PASSWORD`, `PG_DB`, `PG_USER`, `PG_HOST`  
- Redis: `REDIS_URL`