CREATE EXTENSION IF NOT EXISTS timescaledb;
-- sentiment table
CREATE TABLE IF NOT EXISTS sentiment_events (
  id            BIGSERIAL PRIMARY KEY,
  reddit_id     TEXT,
  ticker        TEXT,
  model         TEXT,
  score         DOUBLE PRECISION,
  pos_prob      DOUBLE PRECISION,
  neg_prob      DOUBLE PRECISION,
  created_ts    TIMESTAMPTZ,
  scored_ts     TIMESTAMPTZ DEFAULT NOW()
);
SELECT create_hypertable('sentiment_events','scored_ts', if_not_exists => TRUE); 