# reddit-sentiments
# Sentiment‑Miner

Turn Reddit chatter into a live “mood ring” for the stock market.

## What it does (in plain English)

1. **Listens to Reddit**  
   Every 5 minutes it checks the biggest finance communities (WallStreetBets, r/stocks, etc.).  
   It grabs new posts and top comments that mention any S&P 500 ticker (AAPL, TSLA, AMZN…).

2. **Figures out the vibe**  
   Smart language models read each post and decide: positive, negative, or neutral.  
   Scores are rolled up into easy‑to‑read numbers—per stock, per minute, hour, or day.

3. **Shows you the story**  
   Open the dashboard to see:  
   * A heat‑map of which tickers are loved or hated right now  
   * Live charts that wiggle as fresh posts come in  
   * “Buzz” alerts when a stock suddenly dominates the conversation

That’s it: no spreadsheets, no copy‑paste—just open your browser and watch the crowd’s sentiment in real time.

## Try it on your own laptop

```bash
git clone https://github.com/<you>/sentiment-miner.git
cd sentiment-miner
cp .env.example .env   # add your Reddit API keys here
docker compose up --build
