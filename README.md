# BOU Exchange Rates Emailer

A Python script that scrapes the **official daily foreign exchange rates** from the [Bank of Uganda](https://www.bou.or.ug/) and emails them to a recipient.

The rates are published inside a Power BI embedded report on the BOU homepage. This script uses a headless Chromium browser (Playwright) to render the iframe and extract the live data.

## Sample Output

```
Bank of Uganda Official Exchange Rates
Cycle : Closing
Date  : 18 September 2026
Source: https://www.bou.or.ug/
----------------------------------------
Currency      Buy (UGX)   Sell (UGX)
----------------------------------------
USD            3,930.00     3,940.00
EUR            4,505.35     4,517.60
GBP            5,243.80     5,258.32
KES               30.32        30.45
TZS                1.47         1.50
ZAR              241.20       242.00
----------------------------------------
```

## Requirements

- Python 3.10+
- A Gmail account with [2-Step Verification](https://myaccount.google.com/security) enabled
- A Gmail [App Password](https://myaccount.google.com/apppasswords) (not your regular password)

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/bou-exchange-rates.git
cd bou-exchange-rates
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium

# macOS / Linux
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

### 3. Configure credentials

Set these environment variables before running:

```powershell
# Windows PowerShell
$env:SENDER_EMAIL    = "you@gmail.com"
$env:SENDER_PASSWORD = "your-gmail-app-password"
```

```bash
# macOS / Linux
export SENDER_EMAIL="you@gmail.com"
export SENDER_PASSWORD="your-gmail-app-password"
```

### 4. Set your recipient email

Open `main.py` and update line:

```python
RECIPIENT = "your_email@example.com"
```

### 5. Run

```bash
# Windows
.venv\Scripts\python main.py

# macOS / Linux
.venv/bin/python main.py
```

## How It Works

1. Launches a headless Chromium browser via Playwright
2. Loads the full BOU homepage (`https://www.bou.or.ug/`)
3. Detects the Power BI exchange-rates iframe by its report ID
4. Polls until currency data appears in the rendered frame (~10–20 seconds)
5. Parses the rate table (currency, buy price, sell price)
6. Formats and sends the table via Gmail SMTP

> **Why Playwright?** The exchange rates are rendered by a Power BI report inside an iframe, which requires JavaScript execution. Simple HTTP requests (`requests` library) cannot load this content.

## Automating with Windows Task Scheduler

To receive rates automatically every weekday morning, create a batch script (`run.bat`):

```bat
@echo off
set SENDER_EMAIL=you@gmail.com
set SENDER_PASSWORD=your-app-password
C:\path\to\bou-exchange-rates\.venv\Scripts\python C:\path\to\bou-exchange-rates\main.py
```

Then schedule it with Task Scheduler to run Mon–Fri at your preferred time.

## License

MIT
