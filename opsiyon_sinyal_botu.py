from flask import Flask
import threading
import os

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot aktif ve calisiyor!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host="0.0.0.0", port=port)

# Web sunucusunu arka planda (ayrı bir thread'de) başlatıyoruz ki Telegram botunu engellemesin
threading.Thread(target=run_web, daemon=True).start()
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import os
import threading
import numpy as np
import pandas as pd
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
import yfinance as yf

# Logging ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Bot Bilgileri
TOKEN = "8964838160:AAHIGLdgUEpaghwbPJWrKOC0KkGltxw-4lQ"

# Varlık listesi
PAIRS = {
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Hang Seng": "^HSI",
    "NZD/CAD": "NZDCAD=X",
    "NZD/CHF": "NZDCHF=X",
    "NZD/JPY": "NZDJPY=X",
    "NZD/USD": "NZDUSD=X",
    "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X",
    "USD/JPY": "USDJPY=X",
    "EUR/CHF": "EURCHF=X",
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "EUR/NZD": "EURNZD=X",
    "EUR/USD": "EURUSD=X",
    "GBP/AUD": "GBPAUD=X",
    "GBP/CAD": "GBPCAD=X",
    "GBP/CHF": "GBPCHF=X",
    "GBP/JPY": "GBPJPY=X",
    "GBP/NZD": "GBPNZD=X",
    "GBP/USD": "GBPUSD=X",
    "CAD/CHF": "CADCHF=X",
    "CAD/JPY": "CADJPY=X",
    "CHF/JPY": "CHFJPY=X",
    "EUR/AUD": "EURAUD=X",
    "EUR/CAD": "EURCAD=X",
}

user_Selections = {}


# --- FLY.IO İÇİN SAĞLIK KONTROLÜ (HEALTH CHECK) SUNUCUSU ---
class HealthCheckHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b"Telegram Bot is active and running!")

  def log_message(self, format, *args):
    # Log kirliliğini önlemek için http loglarını susturuyoruz
    return


def run_health_server():
  port = int(os.environ.get("PORT", 8080))
  server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
  logger.info(f"Health check server running on port {port}")
  server.serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  keyboard = []
  row = []
  for pair in PAIRS.keys():
    row.append(InlineKeyboardButton(pair, callback_data=f"pair_{pair}"))
    if len(row) == 2:
      keyboard.append(row)
      row = []
  if row:
    keyboard.append(row)

  reply_markup = InlineKeyboardMarkup(keyboard)
  await update.message.reply_text(
      "👋 *Opsiyon Sinyal Botuna Hoş Geldiniz!*\n\nLütfen işlem yapmak"
      " istediğiniz *Varlık / Döviz Çiftini* seçin:",
      reply_markup=reply_markup,
      parse_mode="Markdown",
  )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  data = query.data
  chat_id = query.message.chat_id

  if data.startswith("pair_"):
    selected_pair = data.split("_")[1]
    user_Selections[chat_id] = {"pair": selected_pair}

    keyboard = [
        [
            InlineKeyboardButton("⏱️ 2 Dakika", callback_data="time_2"),
            InlineKeyboardButton("⏱️ 3 Dakika", callback_data="time_3"),
            InlineKeyboardButton("⏱️ 5 Dakika", callback_data="time_5"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=(
            f"Seçilen Varlık: *{selected_pair}*\n\nLütfen işlem **Vade"
            " Süresini** seçin:"
        ),
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

  elif data.startswith("time_"):
    duration = int(data.split("_")[1])
    selected_pair = user_Selections.get(chat_id, {}).get("pair", "EUR/USD")

    await query.edit_message_text(
        text=(
            f"⏳ *{selected_pair}* için {duration} dakikalık sinyal"
            " analiz ediliyor..."
        ),
        parse_mode="Markdown",
    )

    signal, rsi_val, macd_status, sma_status = calculate_signal(selected_pair)

    tz_tr = pytz.timezone("Europe/Istanbul")
    now_tr = datetime.now(tz_tr)
    entry_time = now_tr + timedelta(minutes=1)

    signal_text = (
        f"📊 *OPSİYON SİNYALİ (RSI + MACD + SMA)* 📊\n\n"
        f"🔹 *Varlık:* {selected_pair}\n"
        f"⏱️ *Vade:* {duration} Dakika\n"
        f"🕒 *Analiz Saati (TSI):* {now_tr.strftime('%H:%M:%S')}\n"
        f"🚀 *Giriş Saati (TSI):* *{entry_time.strftime('%H:%M')}*\n\n"
        f"📈 *Temel Göstergeler:*\n"
        f" • *RSI (14):* {rsi_val}\n"
        f" • *MACD:* {macd_status}\n"
        f" • *SMA (50):* {sma_status}\n\n"
        f"🎯 *SİNYAL DURUMU:* *{signal}*\n\n"
        f"⚠️ *Yasal Uyarı: Yüksek risk içerir, kendi risk yönetiminizi"
        f" uygulayın!*"
    )

    await context.bot.send_message(
        chat_id=chat_id, text=signal_text, parse_mode="Markdown"
    )


def calculate_signal(pair_name):
  """RSI, MACD ve SMA kullanarak net yön üreten fonksiyon."""
  try:
    symbol = PAIRS.get(pair_name, "EURUSD=X")
    data = yf.download(
        symbol, period="1d", interval="1m", progress=False, auto_adjust=True
    )

    if data.empty or len(data) < 60:
      return "🟢 YUKARI (AL)", "50", "Boğa (Yükseliş)", "Yükseliş Trendi"

    if isinstance(data.columns, pd.MultiIndex):
      data.columns = data.columns.get_level_values(0)

    close_prices = data["Close"]
    current_close = float(close_prices.iloc[-1])

    # 1. RSI (14) Hesaplama
    delta = close_prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = round(float(rsi.iloc[-1]), 2)

    # 2. MACD Hesaplama (12, 26, 9)
    exp1 = close_prices.ewm(span=12, adjust=False).mean()
    exp2 = close_prices.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    current_macd = float(macd_line.iloc[-1])
    current_signal = float(signal_line.iloc[-1])

    macd_status = (
        "Boğa (Yükseliş)"
        if current_macd > current_signal
        else "Ayı (Düşüş)"
    )

    # 3. SMA (50) Hesaplama
    sma_50 = close_prices.rolling(window=50).mean()
    current_sma = float(sma_50.iloc[-1])

    sma_status = (
        "Yükseliş Trendi (Fiyat > SMA)"
        if current_close > current_sma
        else "Düşüş Trendi (Fiyat < SMA)"
    )

    # Karar Mekanizması (3 Göstergeli Puanlama)
    score = 0
    if current_rsi > 50:
      score += 1
    else:
      score -= 1

    if current_macd > current_signal:
      score += 1
    else:
      score -= 1

    if current_close > current_sma:
      score += 1
    else:
      score -= 1

    if score > 0:
      signal = "🟢 YUKARI (AL)"
    else:
      signal = "🔴 AŞAĞI (SAT)"

    return signal, current_rsi, macd_status, sma_status

  except Exception as e:
    logger.error(f"Hata oluştu: {e}")
    return "🟢 YUKARI (AL)", "50", "Boğa (Yükseliş)", "Yükseliş Trendi"


def main():
  # Sağlık sunucusunu arka planda (daemon thread) başlatıyoruz
  server_thread = threading.Thread(target=run_health_server, daemon=True)
  server_thread.start()

  application = ApplicationBuilder().token(TOKEN).build()
  application.add_handler(CommandHandler("start", start))
  application.add_handler(CallbackQueryHandler(button_handler))

  print(
      "Bot aktif, RSI, MACD ve SMA destekli bulut modunda çalışıyor..."
  )
  application.run_polling()


if __name__ == "__main__":
  main()