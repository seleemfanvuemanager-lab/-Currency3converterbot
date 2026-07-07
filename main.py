import os
import re
import logging
import asyncio
from typing import Dict, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from forex_python.converter import CurrencyRates, RatesNotAvailableError
from forex_python.bitcoin import BtcConverter

# ---------- CONFIGURATION ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get token from Railway environment variable
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set! Add it in Railway Variables.")

# Initialize converters
currency_converter = CurrencyRates()
btc_converter = BtcConverter()

# ---------- CONSTANTS ----------
SUPPORTED_CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", 
    "INR", "BRL", "ZAR", "NZD", "KRW", "SGD", "HKD", "MXN",
    "SEK", "NOK", "DKK", "PLN", "TRY", "RUB", "ILS", "SAR"
]

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", 
    "CAD": "CA$", "AUD": "AU$", "CHF": "CHF", "CNY": "¥",
    "INR": "₹", "BRL": "R$", "KRW": "₩", "SGD": "S$",
    "HKD": "HK$", "MXN": "Mex$", "ZAR": "R", "NZD": "NZ$",
    "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł",
    "TRY": "₺", "RUB": "₽", "ILS": "₪", "SAR": "ر.س"
}

# ---------- HELPER FUNCTIONS ----------
def get_symbol(currency_code: str) -> str:
    """Get currency symbol or return the code itself if not found."""
    return CURRENCY_SYMBOLS.get(currency_code.upper(), currency_code)

def format_number(num: float) -> str:
    """Format number with commas and 2 decimal places."""
    return f"{num:,.2f}"

def parse_amount(amount_str: str) -> Optional[float]:
    """Parse amount string, handling commas and decimals."""
    try:
        cleaned = amount_str.replace(",", "")
        return float(cleaned)
    except ValueError:
        return None

def parse_conversion(text: str) -> Optional[Tuple[float, str, str]]:
    """
    Parse text like "100 USD to EUR" or "50 GBP in JPY".
    Returns (amount, from_currency, to_currency) or None.
    """
    # Pattern: amount currency to/in/at currency
    pattern = r"^([\d,.]+)\s+([A-Za-z]{3})\s+(?:to|in|at|into)\s+([A-Za-z]{3})$"
    match = re.match(pattern, text.strip(), re.IGNORECASE)
    
    if not match:
        return None
    
    amount = parse_amount(match.group(1))
    if amount is None:
        return None
    
    from_cur = match.group(2).upper()
    to_cur = match.group(3).upper()
    
    return (amount, from_cur, to_cur)

def parse_rate(text: str) -> Optional[Tuple[str, str]]:
    """
    Parse text like "rate USD EUR".
    Returns (from_currency, to_currency) or None.
    """
    pattern = r"^rate\s+([A-Za-z]{3})\s+([A-Za-z]{3})$"
    match = re.match(pattern, text.strip(), re.IGNORECASE)
    
    if not match:
        return None
    
    return (match.group(1).upper(), match.group(2).upper())

# ---------- MENU BUILDER ----------
def get_main_menu() -> InlineKeyboardMarkup:
    """Create the main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("🔄 Convert Currency", callback_data="convert")],
        [InlineKeyboardButton("📊 Exchange Rate", callback_data="rate")],
        [InlineKeyboardButton("💰 Bitcoin Price", callback_data="btc")],
        [InlineKeyboardButton("📋 Supported Currencies", callback_data="list")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------- COMMAND HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    welcome_text = (
        f"👋 **Welcome to Currency3ConverterBot!**\n\n"
        f"I'm your personal currency assistant powered by live exchange rates.\n\n"
        f"✨ **Features:**\n"
        f"• Convert between 30+ currencies\n"
        f"• Get real-time exchange rates\n"
        f"• Check Bitcoin price\n"
        f"• Quick inline conversions\n\n"
        f"Use the buttons below or type commands directly!"
    )
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "📖 **Available Commands:**\n\n"
        "🔹 `/start` - Show main menu\n"
        "🔹 `/help` - Show this help\n"
        "🔹 `/list` - List all supported currencies\n"
        "🔹 `/convert` - Convert currency\n"
        "🔹 `/rate` - Get exchange rate\n"
        "🔹 `/btc` - Get Bitcoin price\n\n"
        "💡 **Quick Usage Examples:**\n"
        "• `100 USD to EUR` - Convert 100 USD to EUR\n"
        "• `50 GBP in JPY` - Convert 50 GBP to JPY\n"
        "• `rate USD EUR` - Get USD to EUR rate\n"
        "• `btc` - Get Bitcoin price in USD\n\n"
        "🌐 **Supported Currencies:**\n"
        f"{', '.join(SUPPORTED_CURRENCIES[:16])}\n"
        f"... and {len(SUPPORTED_CURRENCIES) - 16} more"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list command."""
    try:
        text = "📋 **Supported Currencies:**\n\n"
        # Show all supported currencies with symbols
        for i, currency in enumerate(SUPPORTED_CURRENCIES, 1):
            symbol = get_symbol(currency)
            text += f"{i:2}. {currency} ({symbol})\n"
        
        text += f"\n📊 **Total:** {len(SUPPORTED_CURRENCIES)} currencies"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error listing currencies: {e}")
        await update.message.reply_text("❌ Sorry, couldn't fetch currency list.")

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /convert command."""
    text = (
        "💰 **Currency Converter**\n\n"
        "Type your conversion like this:\n"
        "`100 USD to EUR`\n\n"
        "Or:\n"
        "`50 GBP in JPY`\n\n"
        "📌 **Common Currencies:**\n"
        f"{', '.join(SUPPORTED_CURRENCIES[:10])}\n\n"
        f"Type `/list` to see all {len(SUPPORTED_CURRENCIES)} supported currencies."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /rate command."""
    text = (
        "📊 **Exchange Rate**\n\n"
        "Type: `rate USD EUR`\n\n"
        "This will show you the exchange rate from USD to EUR."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def btc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /btc command."""
    try:
        price = btc_converter.get_latest_price("USD")
        await update.message.reply_text(
            f"💰 **Bitcoin Price**\n\n"
            f"1 BTC = **${format_number(price)}** USD\n\n"
            f"📊 *Data source: forex-python API*\n"
            f"🔄 Updated: Live",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error fetching BTC: {e}")
        await update.message.reply_text("❌ Failed to fetch Bitcoin price. Please try again later.")

# ---------- MESSAGE HANDLER ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle all text messages. Parse and respond to conversion requests.
    """
    text = update.message.text.strip()
    user = update.message.from_user.username or update.message.from_user.first_name
    
    logger.info(f"Message from @{user}: {text}")
    
    # ---------- Check for Bitcoin --------
    if text.lower() in ["btc", "bitcoin"]:
        await btc_command(update, context)
        return
    
    # ---------- Check for Rate Request --------
    rate_parts = parse_rate(text)
    if rate_parts:
        from_cur, to_cur = rate_parts
        await handle_rate(update, from_cur, to_cur)
        return
    
    # ---------- Check for Conversion --------
    conversion = parse_conversion(text)
    if conversion:
        amount, from_cur, to_cur = conversion
        await handle_conversion(update, amount, from_cur, to_cur)
        return
    
    # ---------- Unknown --------
    await update.message.reply_text(
        "🤔 I didn't understand that.\n\n"
        "Try one of these formats:\n"
        "• `100 USD to EUR` (convert currency)\n"
        "• `rate USD EUR` (get exchange rate)\n"
        "• `btc` (Bitcoin price)\n\n"
        "Type `/help` to see all commands.",
        parse_mode="Markdown"
    )

async def handle_conversion(update: Update, amount: float, from_cur: str, to_cur: str) -> None:
    """Handle currency conversion."""
    try:
        # Validate currencies
        if from_cur not in SUPPORTED_CURRENCIES:
            await update.message.reply_text(f"❌ Currency '{from_cur}' not supported. Type `/list` to see all.")
            return
        if to_cur not in SUPPORTED_CURRENCIES:
            await update.message.reply_text(f"❌ Currency '{to_cur}' not supported. Type `/list` to see all.")
            return
        
        # Perform conversion
        result = currency_converter.convert(from_cur, to_cur, amount)
        rate = result / amount
        symbol = get_symbol(to_cur)
        
        await update.message.reply_text(
            f"💱 **Conversion Result**\n\n"
            f"{format_number(amount)} {from_cur} = **{symbol}{format_number(result)} {to_cur}**\n\n"
            f"📊 *Rate: 1 {from_cur} = {rate:.4f} {to_cur}*\n"
            f"🔄 *1 {to_cur} = {1/rate:.4f} {from_cur}*",
            parse_mode="Markdown"
        )
    except RatesNotAvailableError:
        await update.message.reply_text(
            f"❌ Rate not available for {from_cur} or {to_cur}.\n"
            f"Please check the currency codes and try again."
        )
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await update.message.reply_text("❌ Conversion failed. Please try again.")

async def handle_rate(update: Update, from_cur: str, to_cur: str) -> None:
    """Handle exchange rate request."""
    try:
        # Validate currencies
        if from_cur not in SUPPORTED_CURRENCIES:
            await update.message.reply_text(f"❌ Currency '{from_cur}' not supported. Type `/list` to see all.")
            return
        if to_cur not in SUPPORTED_CURRENCIES:
            await update.message.reply_text(f"❌ Currency '{to_cur}' not supported. Type `/list` to see all.")
            return
        
        rate = currency_converter.get_rate(from_cur, to_cur)
        
        await update.message.reply_text(
            f"📊 **Exchange Rate**\n\n"
            f"1 {from_cur} = **{rate:.4f}** {to_cur}\n"
            f"1 {to_cur} = **{1/rate:.4f}** {from_cur}\n\n"
            f"🔄 *Live rate from European Central Bank*",
            parse_mode="Markdown"
        )
    except RatesNotAvailableError:
        await update.message.reply_text(
            f"❌ Rate not available for {from_cur} or {to_cur}."
        )
    except Exception as e:
        logger.error(f"Rate error: {e}")
        await update.message.reply_text("❌ Failed to fetch exchange rate.")

# ---------- CALLBACK HANDLER ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "convert":
        await query.edit_message_text(
            "💰 **Convert Currency**\n\n"
            "Type: `100 USD to EUR`\n\n"
            f"📌 Supported: {', '.join(SUPPORTED_CURRENCIES[:8])}",
            parse_mode="Markdown"
        )
    elif data == "rate":
        await query.edit_message_text(
            "📊 **Exchange Rate**\n\n"
            "Type: `rate USD EUR`\n\n"
            "Shows the live exchange rate between two currencies.",
            parse_mode="Markdown"
        )
    elif data == "btc":
        await query.edit_message_text("⏳ Fetching Bitcoin price...")
        await btc_command(update, context)
    elif data == "list":
        await list_command(update, context)
    elif data == "help":
        await help_command(update, context)

# ---------- ERROR HANDLER ----------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify user."""
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Something went wrong. Please try again later."
            )
    except:
        pass

# ---------- MAIN ----------
def main() -> None:
    """Start the bot."""
    try:
        # Create the Application
        application = Application.builder().token(TOKEN).build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("list", list_command))
        application.add_handler(CommandHandler("convert", convert_command))
        application.add_handler(CommandHandler("rate", rate_command))
        application.add_handler(CommandHandler("btc", btc_command))
        
        # Add callback handler for buttons
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Add message handler (catch-all for text)
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Start the bot with long polling (no webhook needed)
        logger.info("🚀 Starting Currency3ConverterBot...")
        logger.info(f"🤖 Bot username: @Currency3converterbot")
        logger.info("📡 Running with long polling...")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    main()
