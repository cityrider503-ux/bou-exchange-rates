# BOU Exchange Rates Emailer

A Python automation tool that scrapes the **official foreign exchange rates** from the [Bank of Uganda Financial Markets portal](https://www.bou.or.ug/interest_rates_exchange_rates) and delivers a **responsive, professional HTML email** with inline CSS styling.

## Features

- **Dual Exchange Rate Tables**:
  1. **Major Foreign Exchange Rates** (21 currency pairs including USD, EUR, GBP, KES, Gold XAU, SDR, JPY, CAD, CNY, and more).
  2. **COMESA Member Countries Exchange Rates** (16 regional currencies including Kenya, Tanzania, Rwanda, Burundi, South Africa, Malawi, and more).
- **Power BI Headless Extraction**: Uses Playwright to render and interact with the dynamic Power BI embedded reports on the BOU website.
- **Executive HTML Email Design**:
  - Deep navy brand styling (`#0A2540`) with gold accent line (`#C5A059`).
  - Key Currency Highlight cards (USD/UGX, EUR/UGX, GBP/UGX, KES/UGX).
  - Responsive tables with zebra striping, currency badges, and aligned numbers.
  - Multi-part MIME format (`multipart/alternative` with plain-text fallback).

## Sample Output

```
===========================================================================
BANK OF UGANDA — OFFICIAL FOREIGN EXCHANGE RATES
Date  : 18-Sep-2026
Source: https://www.bou.or.ug/interest_rates_exchange_rates
===========================================================================

1. MAJOR FOREIGN EXCHANGE RATES
---------------------------------------------------------------------------
Currency / Pair                       Cross Rate    Buy (UGX)   Sell (UGX)
---------------------------------------------------------------------------
Australian Dollar (AUD)/U.S. Dollar         0.71     2,796.56     2,804.47
Euro/U.S. Dollar                            1.15     4,505.90     4,518.17
Gold (XAU)/U.S. Dollar                  4,394.05 17,245,625.75 17,291,570.50
Kuwaiti Dinar (KWD)/U.S. Dollar             3.25    12,772.53    12,800.91
Pound Sterling (GBP)/U.S. Dollar            1.34     5,247.33     5,261.88
U.S. Dollar/Kenya Shillings (KES)         129.60        30.26        30.39
U.S. Dollar/Uganda Shillings (UGX)      3,930.00     3,925.00     3,935.00
...

2. COMESA MEMBER COUNTRIES EXCHANGE RATES
---------------------------------------------------------------------------
Member Currency                      Rate vs USD    Buy (UGX)   Sell (UGX)
---------------------------------------------------------------------------
Burundi Francs (BIF)                   3,003.500        1.301        1.316
Comoros Francs (KMF)                     429.250        9.123        9.189
Djibouti Francs (DJF)                    178.075       21.983       22.157
Ethiopian Birr (ETB)                     163.299       23.800       24.338
Kenya Shillings (KES)                    129.600       30.262       30.386
Rwanda Francs (RWF)                    1,470.000        2.661        2.686
South African Rand ( S.A. Rand)           16.231      241.724      242.531
Tanzania Shillings (TZS)               2,645.000        1.476        1.496
Uganda Shillings ( UGX)                3,930.000    3,925.000    3,935.000
...
```

## Requirements

- Python 3.10+
- A Gmail account with 2-Step Verification and an [App Password](https://myaccount.google.com/apppasswords).

## Setup & Installation

```bash
git clone https://github.com/cityrider503-ux/bou-exchange-rates.git
cd bou-exchange-rates

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate # Linux / macOS

# Install dependencies and Playwright Chromium
pip install -r requirements.txt
playwright install chromium
```

## Running the Script

Set your Gmail credentials as environment variables:

```powershell
$env:SENDER_EMAIL    = "your_email@gmail.com"
$env:SENDER_PASSWORD = "your-16-char-app-password"
$env:RECIPIENT_EMAIL = "recipient@example.com" # optional, defaults to cityrider503@gmail.com

python main.py
```

## License

MIT
