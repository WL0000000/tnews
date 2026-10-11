# NQ News Bot

Free alerts for the news that moves Nasdaq futures, sent to your phone (Telegram or Discord) and optionally read aloud on your computer.

**What it watches**

| Source | What you get | Speed |
|---|---|---|
| BLS official API (CPI, PPI, jobs report) | The numbers vs forecast and a call: positive, neutral or negative for NQ | Usually seconds to a minute after release |
| Federal Reserve press feed (FOMC statements, minutes) | Decision vs expectations, dissents, wording changes vs the last statement | Seconds to a minute |
| Free news feeds (Google News searches, CNBC, Fed) | Headlines scored for NQ relevance (Iran, oil, tariffs, Nvidia, Apple, OpenAI...) with a rough positive or negative tag | One to a few minutes |
| Forex Factory calendar | A morning list of today's US events with forecasts, in your time zone | Daily at 5:45 AM |

The positive/neutral/negative call is rule-based (hot inflation = bad for NQ while the Fed is hiking). If you add an Anthropic API key, each Fed and data alert also gets a two-line AI summary. Treat every call as context, not a trade signal: wait for the first 5-minute candle after any release.

## Setup (about 15 minutes)

1. **Python 3.11 or newer**, then in this folder:
   ```
   pip install -r requirements.txt
   ```
2. **Free BLS API key** (needed for CPI/PPI/jobs; without it BLS allows only 25 requests a day): register at https://data.bls.gov/registrationEngine/ and check your email.
3. **Telegram alerts**:
   - In Telegram, message **@BotFather**, send `/newbot`, follow the prompts, and copy the token it gives you.
   - Send any message to your new bot, then open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and copy the number after `"chat":{"id":`.
4. Copy `config.example.toml` to `config.toml` and fill in `telegram_token`, `telegram_chat_id`, `bls_api_key` and `contact_email`. Optional: `speak = true` (also run `pip install pyttsx3`), `anthropic_api_key`.
5. Check it works:
   ```
   python -m newsbot test       # sends a test alert to your phone
   python -m newsbot calendar   # this week's US events in your time zone
   python -m newsbot demo       # sample CPI, Fed and headline alerts, no internet needed
   ```
6. Start it before the session and leave the window open:
   ```
   python -m newsbot run
   ```
   On Windows you can make it start automatically with Task Scheduler (trigger: weekdays at 5:00 AM, action: `python -m newsbot run`, start in: this folder).

## Example alerts

```
CPI RELEASED (September data) at Wed 5:30:04 AM
>> Strongly negative for NQ
CPI m/m: 0.4% vs 0.3% expected
Core CPI m/m: 0.4% vs 0.3% expected
CPI y/y: 3.7% vs 3.6% expected
Why: ... Hotter data means more Fed hikes and higher yields, which hits tech.
Rule: wait for the first 5-min candle to close before entering.
```
```
FOMC STATEMENT at Wed 11:00:03 AM
>> Neutral for NQ
Decision: hike, upper bound 5.00%
Expected upper bound: 5.00%
Dissents: 2
Wording changes vs last statement:
  ADDED: Inflation has moved up further and remains elevated...
```
```
HEADLINES Mon 7:42:10 AM
- [likely negative, score 11] Iran says Strait of Hormuz will stay closed after new tanker strike (Reuters)
```

## Tuning

- Too many headline alerts: raise `min_headline_score` to 6. Too few: lower it to 3.
- Add your own words in `[headlines.extra_keywords]`, e.g. `palantir = 2`.
- If the Fed starts cutting because the economy is weak, set `regime = "growth"`: then weak jobs data becomes the bad news.

## Limits

- **Not as fast as a paid squawk.** BLS and the Fed post within seconds, but free news feeds lag one to a few minutes. Keep X notifications on for breaking geopolitical news.
- **The positive/negative tags on headlines are rough** (word lists). The data and Fed calls are more reliable because they compare real numbers with forecasts.
- **Forecasts come from the Forex Factory feed.** If it is down, alerts still show the numbers, without the comparison.
- Core PPI is left out on purpose; only headline PPI is checked.

## Tests

```
python -m unittest discover -s tests -t . -v
```
The files in `tests/fixtures` are made-up sample data in the real formats, used only for testing.
