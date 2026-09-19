import asyncio
import os
import re
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Fix Windows console encoding for Unicode characters
sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright

BOU_URL = "https://www.bou.or.ug/"
RATES_REPORT_ID = "11d932dd-982c-421c-9abf-95bb2e4aef07"

# Known currencies published by BOU
KNOWN_CURRENCIES = {"USD", "EUR", "GBP", "KES", "TZS", "ZAR", "INR", "JPY", "CNY", "AED"}


def parse_rates(raw_text: str) -> list[dict]:
    """
    Parse the raw Power BI frame text into structured rate records.

    The text arrives in this pattern (repeating for each currency):
        CURRENCY_CODE
        BUY_VALUE
        SELL_VALUE
        Buy
        Sell
    """
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    # Detect the rate cycle (Opening / Closing / Midday)
    cycle = "Closing"
    for ln in lines:
        if ln in ("Opening", "Closing", "Midday"):
            cycle = ln
            break

    # Detect the date line  e.g. "Today's Official Exchange Rates (18 September 2026)"
    rate_date = date.today().strftime("%d %B %Y")
    for ln in lines:
        m = re.search(r"\((\d{1,2}\s+\w+\s+\d{4})\)", ln)
        if m:
            rate_date = m.group(1)
            break

    records = []
    i = 0
    while i < len(lines):
        token = lines[i].strip().upper().rstrip()
        if token in KNOWN_CURRENCIES:
            currency = token
            # Collect the next two numeric values (buy then sell)
            nums = []
            j = i + 1
            while j < len(lines) and len(nums) < 2:
                candidate = lines[j].replace(",", "").replace(" ", "")
                try:
                    nums.append(float(candidate))
                except ValueError:
                    pass
                j += 1
            if len(nums) == 2:
                records.append(
                    {
                        "currency": currency,
                        "buy": nums[0],
                        "sell": nums[1],
                    }
                )
            i = j
        else:
            i += 1

    return records, cycle, rate_date


def format_table(records: list[dict], cycle: str, rate_date: str) -> str:
    """Return a nicely aligned plain-text table of exchange rates."""
    header = f"Bank of Uganda Official Exchange Rates\n"
    header += f"Cycle : {cycle}\n"
    header += f"Date  : {rate_date}\n"
    header += f"Source: https://www.bou.or.ug/\n"
    header += "-" * 40 + "\n"
    header += f"{'Currency':<10} {'Buy (UGX)':>12} {'Sell (UGX)':>12}\n"
    header += "-" * 40 + "\n"

    rows = ""
    for r in records:
        rows += f"{r['currency']:<10} {r['buy']:>12,.2f} {r['sell']:>12,.2f}\n"

    return header + rows + "-" * 40


async def fetch_bou_exchange_rates() -> tuple[str, list[dict], str, str]:
    """
    Load the BOU homepage in a headless browser, locate the Power BI
    exchange-rates iframe, and extract structured rate data.

    Returns (formatted_table, records, cycle, rate_date).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        print("Loading Bank of Uganda homepage...")
        await page.goto(BOU_URL, wait_until="domcontentloaded", timeout=60_000)

        # Poll for the exchange-rates iframe frame to appear (up to 60 s)
        rates_frame = None
        print("Waiting for Power BI exchange-rates frame...", end="", flush=True)
        for _ in range(30):
            await asyncio.sleep(2)
            for frame in page.frames:
                if RATES_REPORT_ID in frame.url:
                    rates_frame = frame
                    break
            if rates_frame:
                break
            print(".", end="", flush=True)
        print()

        if not rates_frame:
            await browser.close()
            return "ERROR: Could not locate the exchange rates iframe.", [], "N/A", "N/A"

        # Wait for at least one known currency to appear as text
        print("Waiting for rate data to render...")
        for attempt in range(20):  # up to 40 s
            await asyncio.sleep(2)
            text = await rates_frame.inner_text("body")
            if any(curr in text.upper() for curr in KNOWN_CURRENCIES):
                print(f"Data ready after ~{(attempt + 1) * 2}s")
                break
        else:
            print("Warning: timed out waiting; using whatever is available.")

        raw_text = await rates_frame.inner_text("body")
        await browser.close()

    records, cycle, rate_date = parse_rates(raw_text)
    if not records:
        return (
            "Unable to parse exchange rate data from the Power BI frame.\n"
            f"Raw text received:\n{raw_text}",
            [],
            "N/A",
            "N/A",
        )

    table = format_table(records, cycle, rate_date)
    return table, records, cycle, rate_date


def send_email(table: str, recipient_email: str, rate_date: str):
    """Send the formatted exchange-rate table via Gmail SMTP."""
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")  # Use a Gmail App Password

    if not sender_email or not sender_password:
        print(
            "\nEmail not sent — set SENDER_EMAIL and SENDER_PASSWORD "
            "environment variables first.\n"
            "  $env:SENDER_EMAIL    = 'you@gmail.com'\n"
            "  $env:SENDER_PASSWORD = 'your-app-password'"
        )
        return

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = f"BOU Official Exchange Rates — {rate_date}"

    body = (
        f"Hello,\n\n"
        f"Here are the latest official exchange rates from the Bank of Uganda:\n\n"
        f"{table}\n\n"
        f"This is an automated message.\n"
    )
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"Email sent successfully to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


if __name__ == "__main__":
    RECIPIENT = "cityrider503@gmail.com"

    table, records, cycle, rate_date = asyncio.run(fetch_bou_exchange_rates())

    print("\n" + "=" * 40)
    print(table)
    print("=" * 40 + "\n")

    if records:
        send_email(table, RECIPIENT, rate_date)
