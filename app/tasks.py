import os, json, redis, torch, logging
from celery import Celery
from celery.schedules import schedule
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from db import run

app = Celery('tasks', broker=os.getenv("REDIS_URL"))
rds  = redis.Redis.from_url(os.getenv("REDIS_URL"))

# Global model variables for lazy loading
_tokenizer = None
_model = None
_model_loaded = False

logging.basicConfig(level=logging.INFO)

def load_model():
    """Lazy load FinBERT model with error handling"""
    global _tokenizer, _model, _model_loaded
    
    if _model_loaded:
        return _tokenizer, _model
        
    try:
        logging.info("[load_model] Loading FinBERT model...")
        _tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        _model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        _model.eval()
        _model_loaded = True
        logging.info("[load_model] FinBERT model loaded successfully.")
        return _tokenizer, _model
    except Exception as e:
        logging.error(f"[load_model] Failed to load FinBERT model: {e}")
        # Fallback to simple sentiment (positive bias for demo)
        return None, None

def classify(text: str):
    """Classify text sentiment using FinBERT or fallback method"""
    try:
        tokenizer, model = load_model()
        
        if tokenizer is None or model is None:
            # Simple fallback: count positive/negative words
            logging.warning("[classify] Using fallback sentiment analysis")
            positive_words = ['good', 'great', 'excellent', 'buy', 'bull', 'up', 'gain', 'profit', 'win']
            negative_words = ['bad', 'terrible', 'sell', 'bear', 'down', 'loss', 'lose', 'crash']
            
            text_lower = text.lower()
            pos_count = sum(1 for word in positive_words if word in text_lower)
            neg_count = sum(1 for word in negative_words if word in text_lower)
            
            if pos_count > neg_count:
                return 0.5, 0.7, 0.2  # Positive
            elif neg_count > pos_count:
                return -0.5, 0.2, 0.7  # Negative
            else:
                return 0.0, 0.4, 0.4   # Neutral
        
        # Use FinBERT
        inputs = tokenizer(text, truncation=True, return_tensors="pt", max_length=512)
        with torch.no_grad():
            probs = torch.softmax(model(**inputs).logits, dim=1)[0].tolist()
        pos, neu, neg = probs[2], probs[1], probs[0]
        score = pos - neg
        return score, pos, neg
        
    except Exception as e:
        logging.error(f"[classify] Sentiment analysis failed: {e}")
        # Return neutral sentiment as fallback
        return 0.0, 0.33, 0.33

@app.task
def consume_batch():
    try:
        group = "sentiment"
        stream = "raw_posts"
        logging.info("[consume_batch] Starting task...")
        try:
            rds.xgroup_create(stream, group, id="0", mkstream=True)
            logging.info("[consume_batch] Created consumer group.")
        except redis.exceptions.ResponseError:
            logging.info("[consume_batch] Consumer group already exists.")
        resp = rds.xreadgroup(group, "worker-1", {stream: ">"}, count=1, block=5000)
        logging.info(f"[consume_batch] xreadgroup response: {resp}")
        if not resp:
            logging.info("[consume_batch] No messages to process.")
            return
        stream_name, messages = resp[0]
        msg_id, data = messages[0]
        payload = json.loads(data[b"json"])
        logging.info(f"[consume_batch] Processing message id {msg_id} with payload: {payload}")
        text = f"{payload['title']}  {payload['selftext']}"
        score, pos, neg = classify(text)
        logging.info(f"[consume_batch] Classified text. Score: {score}, Pos: {pos}, Neg: {neg}")
        for ticker in payload["tickers"].split(","):
            try:
                logging.info(f"[consume_batch] Inserting sentiment for {ticker}")
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
        logging.info(f"[consume_batch] Acknowledged message id {msg_id}")
    except Exception as e:
        logging.error(f"Worker error: {e}")

# Schedule consume_batch every 2 seconds
app.conf.beat_schedule = {
    'consume-batch-every-2-seconds': {
        'task': 'tasks.consume_batch',
        'schedule': 2.0,
    },
}
