import os, json, redis, torch, logging
from celery import Celery
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from db import run

app = Celery(broker=os.getenv("REDIS_URL"))
rds  = redis.Redis.from_url(os.getenv("REDIS_URL"))

# FinBERT model
logging.basicConfig(level=logging.INFO)
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
model     = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
model.eval()

def classify(text: str):
    inputs = tokenizer(text, truncation=True, return_tensors="pt")
    with torch.no_grad():
        probs = torch.softmax(model(**inputs).logits, dim=1)[0].tolist()
    pos, neu, neg = probs[2], probs[1], probs[0]
    score = pos - neg
    return score, pos, neg

@app.task
def consume_batch():
    try:
        # Use a consumer group for robust processing
        group = "sentiment"
        stream = "raw_posts"
        try:
            rds.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass  # Group already exists

        resp = rds.xreadgroup(group, "worker-1", {stream: ">"}, count=1, block=5000)
        if not resp:
            return
        stream_name, messages = resp[0]
        msg_id, data = messages[0]
        payload = json.loads(data[b"json"])

        text = f"{payload['title']}  {payload['selftext']}"
        score, pos, neg = classify(text)

        for ticker in payload["tickers"].split(","):
            try:
                run(
                    """INSERT INTO sentiment_events
                       (reddit_id,ticker,model,score,pos_prob,neg_prob,created_ts)
                       VALUES ($1,$2,'finbert',$3,$4,$5,to_timestamp($6))""",
                    payload["id"], ticker, score, pos, neg, payload["t"]
                )
                logging.info(f"Inserted sentiment for {ticker}: {score:.3f}")
            except Exception as db_err:
                logging.error(f"DB insert failed: {db_err}")

        rds.xack(stream, group, msg_id)  # Acknowledge only after success
    except Exception as e:
        logging.error(f"Worker error: {e}")

if __name__ == "__main__":
    from time import sleep
    while True:
        consume_batch.delay()
        sleep(2)
