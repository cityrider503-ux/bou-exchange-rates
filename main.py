import asyncio
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Fix Windows console encoding for Unicode characters
sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright

BOU_INTEREST_RATES_URL = "https://www.bou.or.ug/interest_rates_exchange_rates"
MAJOR_RATES_REPORT_ID = "c76b8c30-56ec-4011-b832-5e36b91dee8a"
COMESA_RATES_REPORT_ID = "caf1cc9c-d2af-4a28-ba99-c04fa2f230f5"


def parse_powerbi_table(raw_text: str) -> tuple[str, list[dict]]:
    """
    Parse the raw Power BI frame text into structured exchange rate records.
    Returns (report_date, records_list).
    """
    text = raw_text.replace("\xa0", " ")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Extract date if present (e.g. 18-Sep-2026)
    report_date = ""
    for l in lines:
        m = re.search(r"(\d{1,2}[\-\s][A-Za-z]{3,9}[\-\s]\d{4})", l)
        if m:
            report_date = m.group(1)
            break

    ignore_lines = {
        "Show keyboard shortcuts", "Show screen reader tips", "Skip to main content",
        "Power BI Report", "Select Date:", "All", "Indicator:", "Major Exchange Rates",
        "Rates for COMESA Member Countries", "Scroll up", "Scroll down", "Scroll left",
        "Scroll right", "Currency", "Cross Rates", "Buying Rates", "Selling Rates",
        "Buying Rate (UGX)", "Selling Rate (UGX)", "U.S. Dollar", "*Weekends have no data",
        "*Weekends and Public Holidays have no data", "COMESA Exchange Rates", "."
    }

    # Split by '.' delimiter which Power BI uses between visual blocks
    blocks = []
    curr_block = []
    for l in lines:
        if l == ".":
            if curr_block:
                blocks.append(curr_block)
                curr_block = []
        else:
            curr_block.append(l)
    if curr_block:
        blocks.append(curr_block)

    def is_number(s: str) -> bool:
        try:
            float(s.replace(",", "").replace(" ", ""))
            return True
        except ValueError:
            return False

    records = []
    for b in blocks:
        clean_b = [x for x in b if x not in ignore_lines]
        if len(clean_b) >= 4:
            currency = clean_b[0]
            nums = clean_b[1:4]
            if all(is_number(n) for n in nums):
                records.append({
                    "currency": currency,
                    "cross_rate": nums[0],
                    "buy_rate": nums[1],
                    "sell_rate": nums[2]
                })

    return report_date, records


def format_plain_text(major_data: list[dict], comesa_data: list[dict], report_date: str) -> str:
    """Format both tables as a clean plain-text string for logs and text-fallback email."""
    date_str = report_date if report_date else datetime.now().strftime("%d-%b-%Y")
    
    out = []
    out.append("=" * 75)
    out.append(f"BANK OF UGANDA — OFFICIAL FOREIGN EXCHANGE RATES")
    out.append(f"Date  : {date_str}")
    out.append(f"Source: {BOU_INTEREST_RATES_URL}")
    out.append("=" * 75)
    out.append("")
    out.append("1. MAJOR FOREIGN EXCHANGE RATES")
    out.append("-" * 75)
    out.append(f"{'Currency / Pair':<36} {'Cross Rate':>11} {'Buy (UGX)':>12} {'Sell (UGX)':>12}")
    out.append("-" * 75)
    for r in major_data:
        out.append(f"{r['currency']:<36} {r['cross_rate']:>11} {r['buy_rate']:>12} {r['sell_rate']:>12}")
    out.append("-" * 75)
    out.append("")
    out.append("2. COMESA MEMBER COUNTRIES EXCHANGE RATES")
    out.append("-" * 75)
    out.append(f"{'Member Currency':<36} {'Rate vs USD':>11} {'Buy (UGX)':>12} {'Sell (UGX)':>12}")
    out.append("-" * 75)
    for r in comesa_data:
        out.append(f"{r['currency']:<36} {r['cross_rate']:>11} {r['buy_rate']:>12} {r['sell_rate']:>12}")
    out.append("-" * 75)
    out.append("")
    out.append("* Weekends and Public Holidays have no published rates.")
    return "\n".join(out)


def generate_email_html(major_data: list[dict], comesa_data: list[dict], report_date: str) -> str:
    """Generate a responsive, modern HTML email with inline CSS."""
    date_display = report_date if report_date else datetime.now().strftime("%d %B %Y")

    # Key highlight rates for the top quick-glance tiles
    key_rates = {}
    for r in major_data:
        curr = r["currency"].lower()
        if "uganda" in curr or "ugx" in curr:
            key_rates["USD / UGX"] = (r["buy_rate"], r["sell_rate"])
        elif "euro" in curr:
            key_rates["EUR / UGX"] = (r["buy_rate"], r["sell_rate"])
        elif "pound" in curr or "gbp" in curr:
            key_rates["GBP / UGX"] = (r["buy_rate"], r["sell_rate"])
        elif "kenya" in curr or "kes" in curr:
            key_rates["KES / UGX"] = (r["buy_rate"], r["sell_rate"])

    tiles_html = ""
    for label, (buy, sell) in key_rates.items():
        tiles_html += f"""
        <td style="padding: 5px; width: 25%;">
            <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 6px; text-align: center;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px;">{label}</div>
                <div style="font-size: 14px; font-weight: 700; color: #0F172A; margin: 4px 0 2px 0;">{buy}</div>
                <div style="font-size: 11px; color: #94A3B8;">Sell: <span style="color: #475569; font-weight: 600;">{sell}</span></div>
            </div>
        </td>
        """

    def build_rows(data: list[dict]) -> str:
        rows = ""
        for i, r in enumerate(data):
            bg = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
            rows += f"""
            <tr style="background-color: {bg};">
                <td style="padding: 9px 12px; font-size: 13px; color: #1E293B; font-weight: 500; border-bottom: 1px solid #E2E8F0;">{r['currency']}</td>
                <td style="padding: 9px 12px; font-size: 13px; color: #475569; text-align: right; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; border-bottom: 1px solid #E2E8F0;">{r['cross_rate']}</td>
                <td style="padding: 9px 12px; font-size: 13px; color: #0D9488; font-weight: 600; text-align: right; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; border-bottom: 1px solid #E2E8F0;">{r['buy_rate']}</td>
                <td style="padding: 9px 12px; font-size: 13px; color: #0284C7; font-weight: 600; text-align: right; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; border-bottom: 1px solid #E2E8F0;">{r['sell_rate']}</td>
            </tr>
            """
        return rows

    major_rows_html = build_rows(major_data)
    comesa_rows_html = build_rows(comesa_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank of Uganda Official Exchange Rates</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #F1F5F9; padding: 25px 12px;">
        <tr>
            <td align="center">
                <!-- Main Container Card -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width: 720px; background-color: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 12px 36px rgba(15, 23, 42, 0.08);">
                    <tr>
                        <td style="background: linear-gradient(135deg, #0A2540 0%, #173A60 100%); padding: 30px 24px; text-align: center; border-bottom: 3px solid #C5A059;">
                            <div style="display: inline-block; padding: 4px 12px; background-color: rgba(197, 160, 89, 0.2); border: 1px solid #C5A059; border-radius: 20px; color: #E5C378; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase;">
                                Central Bank of Uganda
                            </div>
                            <h1 style="margin: 0; color: #FFFFFF; font-size: 23px; font-weight: 800; letter-spacing: -0.5px;">
                                Official Foreign Exchange Rates
                            </h1>
                            <p style="margin: 8px 0 0 0; color: #94A3B8; font-size: 14px;">
                                Daily Market Rates &bull; <strong style="color: #F1F5F9;">{date_display}</strong>
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 20px 6px 20px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                <tr>
                                    {tiles_html}
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 20px 24px 20px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 12px;">
                                <tr>
                                    <td align="left">
                                        <h2 style="margin: 0; color: #0F172A; font-size: 16px; font-weight: 700;">
                                            1. Major Foreign Exchange Rates
                                        </h2>
                                        <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Cross Rates, Official Buying &amp; Selling Quotes (UGX)</div>
                                    </td>
                                    <td align="right" valign="top">
                                        <span style="background-color: #E2E8F0; color: #334155; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 12px;">{len(major_data)} Pairs</span>
                                    </td>
                                </tr>
                            </table>

                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse: collapse; width: 100%; border-radius: 8px; overflow: hidden;">
                                <thead>
                                    <tr style="background-color: #0A2540; color: #FFFFFF;">
                                        <th style="padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Currency / Pair</th>
                                        <th style="padding: 10px 12px; text-align: right; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Cross Rate</th>
                                        <th style="padding: 10px 12px; text-align: right; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Buy (UGX)</th>
                                        <th style="padding: 10px 12px; text-align: right; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Sell (UGX)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {major_rows_html}
                                </tbody>
                            </table>
                        </td>
                    </tr>

                    <tr>
                        <td style="padding: 0 20px 24px 20px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 12px;">
                                <tr>
                                    <td align="left">
                                        <h2 style="margin: 0; color: #0F172A; font-size: 16px; font-weight: 700;">
                                            2. COMESA Member Countries Exchange Rates
                                        </h2>
                                        <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Regional Currencies against U.S. Dollar &amp; Uganda Shilling</div>
                                    </td>
                                    <td align="right" valign="top">
                                        <span style="background-color: #E2E8F0; color: #334155; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 12px;">{len(comesa_data)} Members</span>
                                    </td>
                                </tr>
                            </table>

                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse: collapse; width: 100%; border-radius: 8px; overflow: hidden;">
                                <thead>
                                    <tr style="background-color: #0A2540; color: #FFFFFF;">
                                        <th style="padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Member Currency</th>
                                        <th style="padding: 10px 12px; text-align: right; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Rate vs USD</th>
                                        <th style="padding: 10px 12px; text-align: right; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Buy (UGX)</th>
                                        <th style="padding: 10px 12px; text-align: right; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Sell (UGX)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {comesa_rows_html}
                                </tbody>
                            </table>
                        </td>
                    </tr>

                    <tr>
                        <td style="background-color: #F8FAFC; padding: 20px; border-top: 1px solid #E2E8F0; text-align: center;">
                            <p style="margin: 0 0 6px 0; font-size: 12px; color: #64748B; line-height: 1.5;">
                                Source: <a href="{BOU_INTEREST_RATES_URL}" target="_blank" style="color: #0284C7; text-decoration: underline; font-weight: 600;">Bank of Uganda Financial Markets Page</a>
                            </p>
                            <p style="margin: 0; font-size: 11px; color: #94A3B8; line-height: 1.5;">
                                * Weekends and Public Holidays have no published rates. Rates are indicative and subject to change.<br>
                                Automated notification powered by BOU Exchange Rate Monitor.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return html


async def fetch_both_tables() -> tuple[list[dict], list[dict], str]:
    """
    Scrape both Major Exchange Rates and COMESA Member Rates from
    https://www.bou.or.ug/interest_rates_exchange_rates using Playwright.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        print(f"Loading {BOU_INTEREST_RATES_URL}...")
        await page.goto(BOU_INTEREST_RATES_URL, wait_until="domcontentloaded", timeout=60_000)

        # 1. Fetch Major Rates
        print("Waiting for Major Rates frame...")
        major_frame = None
        for _ in range(30):
            await asyncio.sleep(2)
            for f in page.frames:
                if MAJOR_RATES_REPORT_ID in f.url:
                    major_frame = f
                    break
            if major_frame:
                break

        if not major_frame:
            raise RuntimeError("Could not find Major Rates Power BI iframe.")

        print("Waiting for Major Rates data to render...")
        major_text = ""
        for _ in range(25):
            await asyncio.sleep(2)
            txt = await major_frame.inner_text("body")
            if any(k in txt for k in ["Australian Dollar", "Euro", "U.S. Dollar"]):
                major_text = txt
                print("Major Rates data ready!")
                break
        else:
            major_text = await major_frame.inner_text("body")

        major_date, major_data = parse_powerbi_table(major_text)
        print(f"Extracted {len(major_data)} Major Currency pairs (Date: {major_date}).")

        # 2. Fetch COMESA Rates
        print("Clicking 'COMESA Members' tab...")
        comesa_btn = await page.query_selector("text='COMESA Members'")
        if not comesa_btn:
            raise RuntimeError("Could not find 'COMESA Members' tab button.")

        await comesa_btn.click()

        print("Waiting for COMESA frame...")
        comesa_frame = None
        for _ in range(30):
            await asyncio.sleep(2)
            for f in page.frames:
                if COMESA_RATES_REPORT_ID in f.url:
                    comesa_frame = f
                    break
            if comesa_frame:
                break

        if not comesa_frame:
            raise RuntimeError("Could not find COMESA Rates Power BI iframe.")

        print("Waiting for COMESA data to render...")
        comesa_text = ""
        for _ in range(25):
            await asyncio.sleep(2)
            txt = await comesa_frame.inner_text("body")
            if any(k in txt for k in ["Burundi Francs", "Kenya Shillings", "Tanzania Shillings"]):
                comesa_text = txt
                print("COMESA Rates data ready!")
                break
        else:
            comesa_text = await comesa_frame.inner_text("body")

        comesa_date, comesa_data = parse_powerbi_table(comesa_text)
        print(f"Extracted {len(comesa_data)} COMESA Currencies (Date: {comesa_date}).")

        await browser.close()

    report_date = major_date or comesa_date
    return major_data, comesa_data, report_date


def send_email(major_data: list[dict], comesa_data: list[dict], report_date: str, recipient_email: str):
    """Send both plain-text and HTML email with inline CSS styles via Gmail SMTP."""
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = (os.getenv("SENDER_EMAIL") or "").strip()
    sender_password = (os.getenv("SENDER_PASSWORD") or "").strip()
    recipient_email = (recipient_email or "").strip()

    if not sender_email or not sender_password:
        print(
            "\nEmail not sent — set SENDER_EMAIL and SENDER_PASSWORD environment variables:\n"
            "  $env:SENDER_EMAIL    = 'your_email@gmail.com'\n"
            "  $env:SENDER_PASSWORD = 'your-app-password'"
        )
        return

    if not recipient_email or "@" not in recipient_email:
        raise ValueError(f"RECIPIENT_EMAIL is missing or invalid: {recipient_email!r}")

    plain_text = format_plain_text(major_data, comesa_data, report_date)
    html_content = generate_email_html(major_data, comesa_data, report_date)

    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = recipient_email
    subject_date = report_date if report_date else datetime.now().strftime("%d %B %Y")
    msg["Subject"] = f"Official Bank of Uganda Exchange Rates — {subject_date}"

    # Attach both parts (text first as fallback, HTML second as primary)
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg, from_addr=sender_email, to_addrs=[recipient_email])
        server.quit()
        print(f"Email sent successfully to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


if __name__ == "__main__":
    RECIPIENT = (os.getenv("RECIPIENT_EMAIL") or "").strip() or "dylanivandarussian@gmail.com"

    print("\n--- Scraping Bank of Uganda Exchange Rates ---")
    major_data, comesa_data, report_date = asyncio.run(fetch_both_tables())

    plain_text_summary = format_plain_text(major_data, comesa_data, report_date)
    print("\n" + plain_text_summary + "\n")

    if major_data or comesa_data:
        send_email(major_data, comesa_data, report_date, RECIPIENT)
