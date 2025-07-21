import os, asyncpg, asyncio, logging

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", "postgres"),
            database=os.getenv("PG_DB", "sentiment"),
            host=os.getenv("PG_HOST", "postgres"),
            min_size=1, max_size=5,
        )
    return _pool

async def execute(query, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, *args)
        except Exception as e:
            logging.error(f"DB error: {e}")
            raise

def run(query, *args):
    asyncio.run(execute(query, *args))