"""
Reddit collector – polls finance subs every 5 min and pushes ALL ticker mentions to Redis Streams.
Uses intelligent filtering to capture legitimate tickers while avoiding false positives.
"""
import os, re, json, asyncio, asyncpraw, redis
from dotenv import load_dotenv
load_dotenv()

# Improved ticker extraction with multiple strategies
TICKER_RE_DOLLAR = re.compile(r'\$([A-Z]{1,5})\b')  # $AAPL format (highest confidence)
TICKER_RE_CONTEXT = re.compile(r'\b([A-Z]{2,5})\s+(?:stock|ticker|share|call|put|option|earning|price|target|buy|sell|hold)s?\b', re.IGNORECASE) # AAPL stock
TICKER_RE_MENTIONS = re.compile(r'\b(?:buying|selling|holding|bought|sold|trading)\s+([A-Z]{2,5})\b', re.IGNORECASE) # bought AAPL
TICKER_RE_STANDALONE = re.compile(r'\b([A-Z]{4,5})\b')  # Only 4-5 letter standalone words

# Common words to filter out (blacklist of false positives)
COMMON_WORDS = {
    # 2-3 letter common words
    'IS', 'IT', 'TO', 'ON', 'IN', 'OR', 'OF', 'AT', 'BY', 'UP', 'NO', 'SO', 'GO', 'DO', 'IF', 'BE', 'WE', 'ME', 'MY', 'HE', 'AN', 'AS',
    'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM',
    'OLD', 'SEE', 'TWO', 'HOW', 'ITS', 'NOW', 'NEW', 'MAY', 'WAY', 'WHO', 'BOY', 'USE', 'MAN', 'SHE', 'AIR', 'TOP', 'LOW', 'END',
    'BIG', 'SET', 'OWN', 'PUT', 'SAY', 'TRY', 'WHY', 'LET', 'BAD', 'TOO', 'RUN', 'EYE', 'FAR', 'OFF', 'ADD', 'LOT', 'BAG',
    # 4+ letter common words that look like tickers
    'THIS', 'THAT', 'WITH', 'HAVE', 'THEY', 'WILL', 'BEEN', 'WERE', 'SAID', 'EACH', 'ONLY', 'ALSO', 'BACK', 'CALL', 'CAME', 'DONE',
    'EVEN', 'FIND', 'GOOD', 'HELP', 'JUST', 'KEEP', 'KNOW', 'LAST', 'LEFT', 'LIKE', 'LIVE', 'LOOK', 'MADE', 'MAKE', 'MANY', 'MOST',
    'MOVE', 'MUST', 'NAME', 'NEED', 'NEXT', 'OPEN', 'OVER', 'PART', 'PLAY', 'REAL', 'SAME', 'SEEM', 'SHOW', 'TAKE', 'TELL', 'THAN',
    'THEM', 'TURN', 'VERY', 'WANT', 'WELL', 'WENT', 'WHAT', 'WHEN', 'WHERE', 'WORK', 'YEAR', 'YOUR', 'FROM', 'WOULD', 'THERE',
    'COULD', 'OTHER', 'AFTER', 'FIRST', 'NEVER', 'THESE', 'THINK', 'WHERE', 'BEING', 'EVERY', 'GREAT', 'MIGHT', 'SHALL', 'STILL',
    'THOSE', 'UNDER', 'WHILE', 'SHOULD', 'AROUND', 'BEFORE', 'DURING', 'FOLLOW', 'HAVING', 'PUBLIC', 'SCHOOL', 'SECOND', 'SYSTEM',
    # Finance words that aren't tickers
    'CASH', 'DEBT', 'LOAN', 'RATE', 'FEES', 'FUND', 'LOSS', 'GAIN', 'RISK', 'HIGH', 'BULL', 'BEAR', 'LONG', 'PUTS',
    'BANK', 'CARD', 'PLAN', 'SAVE', 'SELL', 'HOLD', 'DOWN', 'WEEK', 'YEAR', 'TIME', 'DAYS', 'MUCH', 'LESS', 'MORE',
    'COST', 'PAID', 'BILL', 'RENT', 'FOOD', 'HOME', 'LIFE', 'WORK', 'JOBS', 'PAYS', 'NICE', 'BEST', 'EASY', 'HARD',
    'PRICE', 'VALUE', 'WORTH', 'TOTAL', 'POINT', 'SHARE', 'STOCK', 'TRADE', 'CALLS', 'SHORT', 'MARKET', 'MONEY',
    # Additional words that appear in financial contexts but aren't tickers
    'DOING', 'WELL', 'GOOD', 'POOR', 'BEEN', 'ALSO', 'THEM', 'INTO', 'OVER', 'ONLY', 'HERE', 'JUST', 'SOME',
    'AI', 'VS', 'TECH', 'SECTOR', 'AREA', 'WALL', 'PLACE', 'TEAM', 'LATE', 'LATER', 'EARLY', 'FAST', 'SLOW',
    'BOTH', 'TODAY', 'EACH', 'MOST', 'MANY', 'SAME', 'OPEN', 'BACK', 'NEAR', 'NEXT', 'SUCH', 'REAL',
    # Additional common words found in financial discussions
    'ABOVE', 'BELOW', 'ABOUT', 'OFTEN', 'SEEMS', 'GOING', 'FEELS', 'MAKES', 'LOOKS', 'COMES', 'TAKES',
    'YEARS', 'MONTH', 'HOURS', 'DAILY', 'THEIR', 'WHICH', 'THESE', 'THOSE', 'WEIRD', 'WISE', 'CLEAR',
    'SPACE', 'LEVEL', 'RIGHT', 'PEACE', 'TRUTH', 'LEARN', 'FEELS', 'TRULY', 'STAGE', 'FRESH', 'SMALL',
    'HUGE', 'MICRO', 'MACRO', 'BASED', 'GIVEN', 'ENDED', 'HOLDS', 'PARTS', 'DEALS', 'NOTES', 'TOOLS'
}

def extract_tickers(text: str) -> set:
    """Balanced ticker extraction - accurate but not overly restrictive"""
    tickers = set()
    
    # 1. $TICKER format (highest confidence - nearly always real tickers)
    dollar_matches = TICKER_RE_DOLLAR.findall(text.upper())
    tickers.update(dollar_matches)
    
    # 2. TICKER with explicit financial context (high confidence)
    context_matches = TICKER_RE_CONTEXT.findall(text.upper())
    # Only filter out obvious false positives, not legitimate tickers
    validated_context = [t for t in context_matches if t not in COMMON_WORDS]
    tickers.update(validated_context)
    
    # 3. Action + ticker (medium confidence) - "bought AAPL" 
    mention_matches = TICKER_RE_MENTIONS.findall(text.upper())
    # Filter out common words but allow legitimate tickers
    validated_mentions = [t for t in mention_matches if t not in COMMON_WORDS]
    tickers.update(validated_mentions)
    
    # 4. Standalone tickers - more permissive but still accurate
    standalone_pattern = re.compile(r'\b([A-Z]{2,5})\b')
    potential_tickers = standalone_pattern.findall(text.upper())
    
    # Create a broader financial context check for the entire text
    text_upper = text.upper()
    financial_context_found = any(word in text_upper for word in [
        'STOCK', 'STOCKS', 'SHARE', 'SHARES', 'TICKER', 'SYMBOL', 'NYSE', 'NASDAQ', 
        'TRADING', 'TRADE', 'PORTFOLIO', 'INVESTMENT', 'INVEST', 'EQUITY', 'SECURITIES',
        'EARNINGS', 'DIVIDEND', 'PRICE', 'TARGET', 'ANALYST', 'BULL', 'BEAR',
        'MARKET', 'MARKETS', 'S&P', 'DOW', 'RUSSELL', 'INDEX', 'FUND', 'ETF',
        'BUY', 'SELL', 'HOLD', 'BOUGHT', 'SOLD', 'HOLDING', 'BUYING', 'SELLING',
        'CALL', 'CALLS', 'PUT', 'PUTS', 'OPTION', 'OPTIONS', 'FUTURES',
        'REVENUE', 'PROFIT', 'LOSS', 'GAIN', 'GROWTH', 'VALUATION',
        'PERFORMANCE', 'INCLUDES', 'ALLOCATION', 'ANALYSIS', 'THESIS',
        'REPORT', 'UP', 'DOWN', 'VS', 'SECTOR', 'AI', 'TECH', 'CRYPTO', 'COIN'
    ])
    
    # If we found financial context in the text, be more permissive with standalone tickers
    if financial_context_found:
        for ticker in potential_tickers:
            if ticker not in COMMON_WORDS and len(ticker) >= 2:
                tickers.add(ticker)
    else:
        # No financial context - only add tickers that are 4+ chars and not common words
        # This catches obvious ticker symbols even without explicit context
        for ticker in potential_tickers:
            if ticker not in COMMON_WORDS and len(ticker) >= 4:
                # Additional check: avoid obvious English words that might be 4+ letters
                english_words = {'FROM', 'THAT', 'THIS', 'WITH', 'WHAT', 'WHEN', 'WHERE', 'THEY', 'THEM', 'WILL', 'BEEN', 'WERE'}
                if ticker not in english_words:
                    tickers.add(ticker)
    
    return tickers

async def collect_posts_for_ticker(ticker: str, limit: int = 100):
    """Collect Reddit posts specifically mentioning a given ticker"""
    print(f"[DEBUG] Starting targeted collection for {ticker}")
    
    reddit = asyncpraw.Reddit(
        client_id=os.getenv("RID"),
        client_secret=os.getenv("RSEC"),
        user_agent=os.getenv("RUSERAGENT"),
    )
    
    posts = []
    subs = ["personalfinance","wallstreetbets","CryptoCurrency","stocks",
            "StockMarket","investing","financialindependence","pennystocks", 
            "Options","SecurityAnalysis","dividendinvesting","ValueInvesting",
            "smallstreetbets","daytrading","investing_discussion"]
    
    # Search for posts containing the ticker across all finance subreddits
    for sub in subs:
        try:
            subreddit = await reddit.subreddit(sub)
            
            # Search for the ticker in multiple formats
            search_queries = [
                f"${ticker}",          # $AAPL format
                f"{ticker} stock",     # AAPL stock
                f"{ticker} earnings",  # AAPL earnings  
                ticker                 # Just AAPL
            ]
            
            for query in search_queries:
                try:
                    async for post in subreddit.search(query, sort="new", time_filter="month", limit=20):
                        # Verify the ticker is actually mentioned
                        full_text = f"{post.title} {post.selftext}"
                        found_tickers = extract_tickers(full_text)
                        
                        if ticker in found_tickers:
                            post_data = {
                                "id": post.id,
                                "subreddit": post.subreddit.display_name,
                                "title": post.title,
                                "selftext": post.selftext,
                                "created_utc": post.created_utc
                            }
                            posts.append(post_data)
                            
                            if len(posts) >= limit:
                                break
                                
                except Exception as e:
                    print(f"[ERROR] Search failed for {query} in {sub}: {e}")
                    continue
                    
            if len(posts) >= limit:
                break
                
        except Exception as e:
            print(f"[ERROR] Failed to search subreddit {sub}: {e}")
            continue
    
    print(f"[DEBUG] Found {len(posts)} posts for {ticker}")
    return posts

async def main():
    print("[DEBUG] Starting universal collector - capturing ALL legitimate tickers...")
    print(f"[DEBUG] RID: {os.getenv('RID')}")
    print(f"[DEBUG] RSEC: {os.getenv('RSEC')}")
    print(f"[DEBUG] RUSERAGENT: {os.getenv('RUSERAGENT')}")
    
    reddit = asyncpraw.Reddit(
        client_id=os.getenv("RID"),
        client_secret=os.getenv("RSEC"),
        user_agent=os.getenv("RUSERAGENT"),
    )
    q = redis.Redis.from_url(os.getenv("REDIS_URL"))
    
    # Expanded subreddit list for broader coverage
    subs = ["personalfinance","wallstreetbets","CryptoCurrency","stocks",
            "StockMarket","investing","financialindependence","pennystocks",
            "Options","SecurityAnalysis","dividendinvesting","ValueInvesting",
            "smallstreetbets","daytrading","investing_discussion"]
    
    while True:
        for sub in subs:
            try:
                subreddit = await reddit.subreddit(sub)
                async for post in subreddit.new(limit=75):  # Increased limit for more coverage
                    # Combine title and selftext for better context
                    full_text = f"{post.title} {post.selftext}"
                    tickers = extract_tickers(full_text)
                    
                    # Process ALL legitimate tickers found (no S&P 500 restriction)
                    if not tickers:
                        continue
                        
                    print(f"[DEBUG] Found tickers {tickers} in r/{sub}: {post.title[:50]}...")
                    payload = {
                        "id": post.id,
                        "sub": sub,
                        "t": post.created_utc,
                        "tickers": ",".join(tickers),
                        "title": post.title,
                        "selftext": post.selftext,
                    }
                    q.xadd("raw_posts", {"json": json.dumps(payload)})
            except Exception as e:
                print(f"[ERROR] Failed to process subreddit r/{sub}: {e}")
                
        await asyncio.sleep(300)  # 5 min

if __name__ == "__main__":
    asyncio.run(main()) 