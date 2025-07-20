"""
Reddit collector – polls 11 subs every 5\u00a0min and pushes S&P\u00a0500 mentions to Redis Streams.
"""
import os, re, json, asyncio, asyncpraw, redis
from dotenv import load_dotenv
load_dotenv()

TICKER_RE = re.compile(r'(\\$?[A-Z]{2,5})(?=\\b)')
WHITELIST = set()

async def load_sp500():
    import aiohttp, csv, io
    url = "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
    async with aiohttp.ClientSession() as s, s.get(url) as r:
        text = await r.text()
    reader = csv.DictReader(io.StringIO(text))
    return {row["Symbol"] for row in reader}

async def main():
    global WHITELIST
    WHITELIST = await load_sp500()
    reddit = asyncpraw.Reddit(
        client_id=os.getenv("RID"),
        client_secret=os.getenv("RSEC"),
        user_agent=os.getenv("RUSERAGENT"),
    )
    q = redis.Redis.from_url(os.getenv("REDIS_URL"))
    subs = ["personalfinance","wallstreetbets","CryptoCurrency","stocks",
            "StockMarket","investing","financialindependence","pennystocks",
            "Options","SecurityAnalysis","dividendinvesting"]
    while True:
        for sub in subs:
            subreddit = await reddit.subreddit(sub)
            async for post in subreddit.new(limit=50):
                syms = {t.lstrip("$") for t in TICKER_RE.findall(post.title.upper())}
                matches = syms & WHITELIST
                if not matches:
                    continue
                payload = {
                    "id": post.id,
                    "sub": sub,
                    "t": post.created_utc,
                    "tickers": ",".join(matches),
                    "title": post.title,
                    "selftext": post.selftext,
                }
                q.xadd("raw_posts", {"json": json.dumps(payload)})
        await asyncio.sleep(300)  # 5\u00a0min

if __name__ == "__main__":
    asyncio.run(main()) 