from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Set
import logging
import aiohttp
import csv
import io
import asyncio
import redis
import os
import json
from datetime import datetime, timedelta
from db import fetch, fetchrow, execute

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global S&P 500 cache
_sp500_tickers: Optional[Set[str]] = None

async def load_sp500() -> Set[str]:
    """Load S&P 500 ticker symbols from external data source"""
    global _sp500_tickers
    
    if _sp500_tickers is not None:
        return _sp500_tickers
        
    try:
        url = "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    reader = csv.DictReader(io.StringIO(text))
                    _sp500_tickers = {row["Symbol"] for row in reader}
                    logging.info(f"Loaded {len(_sp500_tickers)} S&P 500 tickers")
                else:
                    logging.error(f"Failed to fetch S&P 500 data: {response.status}")
                    _sp500_tickers = set()
    except Exception as e:
        logging.error(f"Error loading S&P 500 data: {e}")
        _sp500_tickers = set()
    
    return _sp500_tickers

# Redis connection for triggering collection
rds = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

async def has_recent_data(ticker: str, hours: int = 1) -> bool:
    """Check if we have recent data for this ticker (within last hour)"""
    try:
        recent_data = await fetchrow(
            """SELECT COUNT(*) as count FROM sentiment_events 
               WHERE ticker = $1 AND scored_ts >= NOW() - INTERVAL '%s hours'""" % hours,
            ticker
        )
        return dict(recent_data)['count'] > 0
    except Exception as e:
        logging.error(f"Error checking recent data for {ticker}: {e}")
        return False

async def collect_ticker_data(ticker: str):
    """Trigger on-demand collection for specific ticker"""
    try:
        # Import collector functions
        from collector import collect_posts_for_ticker
        
        # Collect posts specifically for this ticker
        logging.info(f"Starting targeted collection for {ticker}")
        posts = await collect_posts_for_ticker(ticker)
        
        if posts:
            # Push to Redis for immediate processing
            for post in posts:
                post_data = {
                    "id": post["id"],
                    "sub": post["subreddit"],
                    "t": post["created_utc"],
                    "tickers": ticker,  # Only the requested ticker
                    "title": post["title"],
                    "selftext": post.get("selftext", "")
                }
                # Worker expects a 'json' field with JSON string
                redis_data = {"json": json.dumps(post_data)}
                rds.xadd("raw_posts", redis_data)
            
            # Wait for processing to complete (up to 45 seconds)
            await wait_for_processing(ticker, max_wait=45)
            logging.info(f"On-demand collection completed for {ticker}")
        else:
            logging.info(f"No posts found for {ticker}")
            
    except Exception as e:
        logging.error(f"Error in on-demand collection for {ticker}: {e}")

async def wait_for_processing(ticker: str, max_wait: int = 45):
    """Wait for sentiment processing to complete"""
    start_time = datetime.now()
    while (datetime.now() - start_time).seconds < max_wait:
        # Check if new data has been processed
        if await has_recent_data(ticker, hours=0.05):  # Check last 3 minutes
            print(f"[API] Processing completed for {ticker}")
            return
        await asyncio.sleep(1)  # Check every 1 second
    
    print(f"[API] Processing timeout for {ticker} after {max_wait}s, continuing anyway")

class TickerRequest(BaseModel):
    ticker: str

class SentimentEvent(BaseModel):
    id: int
    reddit_id: str
    ticker: str
    model: str
    score: float
    pos_prob: float
    neg_prob: float
    created_ts: datetime
    scored_ts: datetime

class TickerSentiment(BaseModel):
    ticker: str
    latest_score: float
    avg_score: float
    total_mentions: int
    last_updated: datetime

@app.get("/")
def read_root():
    return {"status": "API is running!"}

@app.get("/sp500")
async def get_sp500_tickers():
    """Get list of all S&P 500 ticker symbols"""
    try:
        tickers = await load_sp500()
        return {"tickers": sorted(list(tickers)), "count": len(tickers)}
    except Exception as e:
        logging.error(f"Error getting S&P 500 tickers: {e}")
        raise HTTPException(status_code=500, detail="Failed to load S&P 500 data")

@app.post("/validate-ticker")
async def validate_ticker(req: TickerRequest):
    """Validate if a ticker is in the S&P 500"""
    ticker = req.ticker.upper()
    try:
        sp500_tickers = await load_sp500()
        is_valid = ticker in sp500_tickers
        return {
            "ticker": ticker,
            "is_sp500": is_valid,
            "message": f"{'Valid' if is_valid else 'Invalid'} S&P 500 ticker"
        }
    except Exception as e:
        logging.error(f"Error validating ticker {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate ticker")

@app.get("/search/{ticker}")
async def search_ticker(ticker: str, days: int = 30, limit: int = 100, fresh: bool = False):
    """Comprehensive ticker search with on-demand data collection"""
    ticker = ticker.upper()
    
    print(f"[API] Starting search for {ticker}, fresh={fresh}")
    
    try:
        # Check if we need fresh data collection
        has_recent = await has_recent_data(ticker)
        print(f"[API] Search {ticker}: fresh={fresh}, has_recent_data={has_recent}")
        
        if fresh or not has_recent:
            print(f"[API] Triggering on-demand collection for {ticker}")
            await collect_ticker_data(ticker)
            print(f"[API] On-demand collection completed for {ticker}")
        else:
            print(f"[API] Using cached data for {ticker}")
    except Exception as collection_error:
        print(f"[API] Collection error for {ticker}: {collection_error}")
        # Continue with existing data even if collection fails
    
    try:
        # Get basic ticker stats
        ticker_stats_query = """
        SELECT 
            ticker,
            COUNT(*) as total_mentions,
            AVG(score) as avg_sentiment,
            STDDEV(score) as sentiment_volatility,
            MIN(scored_ts) as first_mention,
            MAX(scored_ts) as last_mention,
            MIN(score) as min_sentiment,
            MAX(score) as max_sentiment
        FROM sentiment_events 
        WHERE ticker = $1
        GROUP BY ticker
        """
        
        # Get historical sentiment timeline by day
        timeline_query = """
        SELECT DATE(scored_ts) as date,
               COUNT(*) as mentions,
               AVG(score) as avg_sentiment,
               STDDEV(score) as sentiment_volatility,
               MIN(score) as min_sentiment,
               MAX(score) as max_sentiment
        FROM sentiment_events 
        WHERE ticker = $1 AND scored_ts >= NOW() - INTERVAL '%s days'
        GROUP BY DATE(scored_ts)
        ORDER BY date DESC
        """ % days
        
        # Get recent individual posts with Reddit links
        posts_query = """
        SELECT reddit_id, score, pos_prob, neg_prob, scored_ts, created_ts,
               'https://www.reddit.com/comments/' || reddit_id as reddit_url
        FROM sentiment_events
        WHERE ticker = $1 AND scored_ts >= NOW() - INTERVAL '%s days'
        ORDER BY scored_ts DESC
        LIMIT $2
        """ % days
        
        # Execute all queries
        ticker_info = await fetchrow(ticker_stats_query, ticker)
        timeline = await fetch(timeline_query, ticker)
        recent_posts = await fetch(posts_query, ticker, limit)
        
        return {
            "ticker": ticker,
            "found": ticker_info is not None,
            "ticker_info": dict(ticker_info) if ticker_info else None,
            "timeline": [dict(row) for row in timeline],
            "recent_posts": [dict(row) for row in recent_posts],
            "search_params": {"days": days, "limit": limit}
        }
    except Exception as e:
        logging.error(f"Error searching ticker {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Search failed")

@app.get("/trending")
async def get_trending_tickers(period: str = "24h", limit: int = 20):
    """Get most discussed tickers for specified time period"""
    period_map = {
        "24h": "1 day",
        "7d": "7 days", 
        "30d": "30 days"
    }
    
    if period not in period_map:
        raise HTTPException(status_code=400, detail="Invalid period. Use 24h, 7d, or 30d")
        
    try:
        query = f"""
        SELECT ticker,
               COUNT(*) as mention_count,
               AVG(score) as avg_sentiment,
               STDDEV(score) as sentiment_volatility,
               MIN(score) as min_sentiment,
               MAX(score) as max_sentiment,
               MAX(scored_ts) as last_seen
        FROM sentiment_events 
        WHERE scored_ts >= NOW() - INTERVAL '{period_map[period]}'
        GROUP BY ticker
        HAVING COUNT(*) >= 2  -- At least 2 mentions to be considered trending
        ORDER BY mention_count DESC, avg_sentiment DESC
        LIMIT $1
        """
        
        rows = await fetch(query, limit)
        return {
            "period": period,
            "tickers": [dict(row) for row in rows]
        }
    except Exception as e:
        logging.error(f"Error fetching trending tickers: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/autocomplete")
async def autocomplete_tickers(q: str, limit: int = 10):
    """Ticker autocomplete for search"""
    if len(q) < 2:
        return {"suggestions": []}
        
    try:
        # Search for tickers that start with or contain the query
        query = """
        SELECT ticker, 
               COUNT(*) as mention_count,
               MAX(scored_ts) as last_seen,
               AVG(score) as avg_sentiment
        FROM sentiment_events 
        WHERE ticker ILIKE $1 OR ticker ILIKE $2
        GROUP BY ticker
        ORDER BY mention_count DESC, ticker
        LIMIT $3
        """
        
        rows = await fetch(query, f"{q.upper()}%", f"%{q.upper()}%", limit)
        return {
            "query": q.upper(),
            "suggestions": [dict(row) for row in rows]
        }
    except Exception as e:
        logging.error(f"Error in autocomplete: {e}")
        raise HTTPException(status_code=500, detail="Search failed")

@app.post("/ticker-exists")
async def check_ticker_exists(req: TickerRequest):
    """Check if ticker exists in our database"""
    ticker = req.ticker.upper()
    try:
        result = await fetchrow(
            "SELECT ticker, COUNT(*) as mention_count FROM sentiment_events WHERE ticker = $1 GROUP BY ticker", 
            ticker
        )
        return {
            "exists": result is not None,
            "ticker": ticker,
            "mentions": dict(result)["mention_count"] if result else 0
        }
    except Exception as e:
        logging.error(f"Error checking ticker existence: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/sentiments/{ticker}")
async def get_ticker_sentiments(ticker: str, hours: Optional[int] = 24):
    """Get sentiment history for a specific ticker"""
    ticker = ticker.upper()
    try:
        query = """
        SELECT id, reddit_id, ticker, model, score, pos_prob, neg_prob, created_ts, scored_ts
        FROM sentiment_events 
        WHERE ticker = $1 AND scored_ts >= NOW() - INTERVAL '%s hours'
        ORDER BY scored_ts DESC
        """ % hours
        
        rows = await fetch(query, ticker)
        result = []
        for row in rows:
            row_dict = dict(row)
            # Add Reddit URL
            row_dict['reddit_url'] = f"https://www.reddit.com/comments/{row_dict['reddit_id']}"
            result.append(row_dict)
        return result
    except Exception as e:
        logging.error(f"Error fetching sentiments for {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/sentiments/latest")
async def get_latest_sentiments():
    """Get latest sentiment summary for all tickers"""
    try:
        query = """
        WITH latest_sentiments AS (
            SELECT 
                ticker,
                score,
                scored_ts,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY scored_ts DESC) as rn
            FROM sentiment_events
            WHERE scored_ts >= NOW() - INTERVAL '24 hours'
        ),
        ticker_stats AS (
            SELECT 
                ticker,
                AVG(score) as avg_score,
                COUNT(*) as total_mentions,
                MAX(scored_ts) as last_updated
            FROM sentiment_events
            WHERE scored_ts >= NOW() - INTERVAL '24 hours'
            GROUP BY ticker
        )
        SELECT 
            ts.ticker,
            ls.score as latest_score,
            ts.avg_score,
            ts.total_mentions,
            ts.last_updated
        FROM ticker_stats ts
        JOIN latest_sentiments ls ON ts.ticker = ls.ticker AND ls.rn = 1
        ORDER BY ts.last_updated DESC
        """
        
        rows = await fetch(query)
        return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"Error fetching latest sentiments: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/tickers")
async def get_available_tickers():
    """Get list of all tickers with sentiment data"""
    try:
        query = """
        SELECT 
            ticker,
            COUNT(*) as mention_count,
            AVG(score) as avg_sentiment,
            MIN(scored_ts) as first_seen,
            MAX(scored_ts) as last_seen
        FROM sentiment_events
        GROUP BY ticker
        ORDER BY mention_count DESC
        """
        
        rows = await fetch(query)
        return [dict(row) for row in rows]
    except Exception as e:
        logging.error(f"Error fetching tickers: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/activity/recent")
async def get_recent_activity(limit: int = 10):
    """Get recent sentiment analysis activity"""
    try:
        query = """
        SELECT 
            ticker,
            score,
            scored_ts,
            reddit_id
        FROM sentiment_events
        ORDER BY scored_ts DESC
        LIMIT $1
        """
        
        rows = await fetch(query, limit)
        result = []
        for row in rows:
            row_dict = dict(row)
            # Add Reddit URL
            row_dict['reddit_url'] = f"https://www.reddit.com/comments/{row_dict['reddit_id']}"
            result.append(row_dict)
        return result
    except Exception as e:
        logging.error(f"Error fetching recent activity: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/data/sources")
async def get_data_sources():
    """Get information about data sources and methodology"""
    return {
        "subreddits_monitored": [
            "personalfinance", "wallstreetbets", "CryptoCurrency", "stocks",
            "StockMarket", "investing", "financialindependence", "pennystocks", 
            "Options", "SecurityAnalysis", "dividendinvesting", "ValueInvesting",
            "smallstreetbets", "daytrading", "investing_discussion"
        ],
        "collection_frequency": "Every 5 minutes",
        "posts_per_subreddit": "75 newest posts",
        "total_stocks_tracked": "All legitimate stock tickers (no restrictions)",
        "ticker_extraction": {
            "method": "Intelligent pattern matching with context analysis",
            "patterns": [
                "$TICKER format (highest confidence)",
                "Ticker with financial context (e.g., 'AAPL stock', 'NVDA earnings')",
                "Trading actions (e.g., 'bought MSFT', 'selling AMZN')",
                "Standalone tickers in financial discussions"
            ],
            "filtering": "Comprehensive blacklist of 200+ common English words to prevent false positives"
        },
        "sentiment_model": "ProsusAI/finbert",
        "model_description": "FinBERT - Financial domain-specific BERT model for sentiment analysis",
        "sentiment_calculation": {
            "description": "FinBERT outputs probabilities for positive, negative, and neutral sentiment",
            "formula": "sentiment_score = positive_probability - negative_probability",
            "range": "Score ranges from -1 (most negative) to +1 (most positive)",
            "classification": {
                "positive": "score > 0.1",
                "negative": "score < -0.1", 
                "neutral": "-0.1 <= score <= 0.1"
            }
        },
        "search_capabilities": {
            "ticker_search": "Search any ticker for comprehensive historical analysis",
            "trending_analysis": "Most discussed stocks by day/week/month",
            "autocomplete": "Smart ticker suggestions based on historical data"
        },
        "data_storage": "TimescaleDB with automatic time-series optimization"
    }

@app.get("/data/sample")
async def get_sample_data():
    """Get sample posts with sentiment analysis for demonstration"""
    try:
        query = """
        SELECT 
            reddit_id,
            ticker,
            score,
            pos_prob,
            neg_prob,
            created_ts,
            scored_ts,
            CASE 
                WHEN score > 0.1 THEN 'positive'
                WHEN score < -0.1 THEN 'negative' 
                ELSE 'neutral'
            END as classification
        FROM sentiment_events
        ORDER BY scored_ts DESC
        LIMIT 10
        """
        
        rows = await fetch(query)
        result = []
        for row in rows:
            row_dict = dict(row)
            row_dict['reddit_url'] = f"https://www.reddit.com/comments/{row_dict['reddit_id']}"
            result.append(row_dict)
        return result
    except Exception as e:
        logging.error(f"Error fetching sample data: {e}")
        raise HTTPException(status_code=500, detail="Database error")

