import os, asyncpg, asyncio, logging

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        logging.info("[db.py] Creating asyncpg pool...")
        _pool = await asyncpg.create_pool(
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", "postgres"),
            database=os.getenv("PG_DB", "sentiment"),
            host=os.getenv("PG_HOST", "postgres"),
            min_size=1, max_size=5,
        )
    return _pool

async def execute(query, *args):
    logging.info(f"[db.py] execute() called with query: {query} args: {args}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, *args)
            logging.info("[db.py] Query executed successfully.")
        except Exception as e:
            logging.error(f"[db.py] DB error: {e}")
            raise

def run(query, *args):
    logging.info(f"[db.py] run() called with query: {query} args: {args}")
    try:
        # Check if there's already an event loop running
        try:
            loop = asyncio.get_running_loop()
            # If we're in an existing loop, create a task instead
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(lambda: asyncio.run(execute(query, *args)))
                future.result()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            asyncio.run(execute(query, *args))
        logging.info("[db.py] run() completed successfully.")
    except Exception as e:
        logging.error(f"[db.py] run() error: {e}")
        raise

async def fetch(query, *args):
    """Fetch query results as list of records"""
    logging.info(f"[db.py] fetch() called with query: {query} args: {args}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetch(query, *args)
            logging.info(f"[db.py] Query returned {len(result)} rows.")
            return result
        except Exception as e:
            logging.error(f"[db.py] DB fetch error: {e}")
            raise

async def fetchrow(query, *args):
    """Fetch single row as record"""
    logging.info(f"[db.py] fetchrow() called with query: {query} args: {args}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchrow(query, *args)
            logging.info("[db.py] Single row fetched successfully.")
            return result
        except Exception as e:
            logging.error(f"[db.py] DB fetchrow error: {e}")
            raise