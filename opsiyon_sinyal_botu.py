from datetime import datetime
import logging
import os
import sys
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import ta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# -------------------------------------------------------------
# KONFİGÜRASYON VE API ANAHTARLARI
# -------------------------------------------------------------
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "c718f65c0b984c24880ec35fc2dc557b")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8964838160:AAHIGLdgUEpaghwbPJWrKOC0KkGltxw-4lQ")

if not TELEGRAM_BOT_TOKEN:
    logging.critical("❌ HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
    sys.exit(1)

PARITE_HARITASI = {
    "USD/JPY": "USD/JPY",
    "USD/MXN": "USD/MXN",
    "USD/NOK": "USD/NOK",
    "USD/SGD": "USD/SGD",
    "AUD/CAD": "AUD/CAD",
    "AUD/CHF": "AUD/CHF",
    "AUD/JPY": "AUD/JPY",
    "AUD/NZD": "AUD/NZD",
    "AUD/USD": "AUD/USD",
    "CAD/CHF": "CAD/CHF",
    "CAD/JPY": "CAD/JPY",
    "CHF/JPY": "CHF/JPY",
    "EUR/AUD": "EUR/AUD",
    "EUR/CAD": "EUR/CAD",
    "EUR/CHF": "EUR/CHF",
    "EUR/GBP": "EUR/GBP",
    "EUR/JPY": "EUR/JPY",
    "EUR/NZD": "EUR/NZD",
    "EUR/USD": "EUR/USD",
    "GBP/AUD": "GBP/AUD",
    "GBP/CAD": "GBP/CAD",
    "GBP/CHF": "GBP/CHF",
    "GBP/JPY": "GBP/JPY",
    "GBP/NZD": "GBP/NZD",
    "GBP/USD": "GBP/USD",
    "NZD/CAD": "NZD/CAD",
    "NZD/CHF": "NZD/CHF",
    "NZD/JPY": "NZD/JPY",
    "NZD/USD": "NZD/USD",
    "USD/CAD": "USD/CAD",
    "USD/CHF": "USD/CHF",
}

INDEX_TO_NAME = list(PARITE_HARITASI.keys())
NAME_TO_INDEX = {name: i for i, name in enumerate(INDEX_TO_NAME)}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


# -------------------------------------------------------------
# TEKNİK ANALİZ MOTORU (Twelve Data Gerçek Veri & Rate Limit Koruması)
# -------------------------------------------------------------
def teknik_analiz_yap(symbol, vade_dakika=2):
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=30&apikey={TWELVEDATA_API_KEY}"
        response = requests.get(url, timeout=10).json()
        
        # 1. API İstek Sınırı (Rate Limit - 429) ve Hata Kontrolü
        if "code" in response:
            code = str(response["code"])
            if code == "429" or "limit" in str(response.get("message", "")).lower():
                return "⚪ NÖTR (BEKLE)", f"⏰ Zaman: {datetime.now().strftime('%H:%M:%S')}\n⚠️ API istek sınırına (Rate Limit) ulaşıldı! Lütfen biraz bekleyin."
            elif code != "200":
                return "⚪ NÖTR (BEKLE)", f"⏰ Zaman: {datetime.now().strftime('%H:%M:%S')}\n⚠️ API Hatası: {response.get('message', 'Bilinmeyen hata')}"

        if "values" not in response or not response["values"]:
            return "⚪ NÖTR (BEKLE)", f"⏰ Zaman: {datetime.now().strftime('%H:%M:%S')}\n⚠️ Fiyat verisi alınamadı."

        values = response["values"][::-1]
        closes = [float(item["close"]) for item in values]
        canli_fiyat = closes[-1]

        df = pd.DataFrame({"close": closes}, dtype=float)

        # 1. RSI (14)
        try:
            rsi_series = ta.momentum.rsi(df["close"], window=14)
            rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else 50.0
        except Exception:
            rsi = 50.0

        # 2. SMA (20)
        try:
            sma_series = ta.trend.sma_indicator(df["close"], window=min(len(df), 20))
            sma_20 = float(sma_series.iloc[-1]) if not sma_series.empty and not pd.isna(sma_series.iloc[-1]) else canli_fiyat
        except Exception:
            sma_20 = canli_fiyat

        # 3. Bollinger Bands
        try:
            bollinger = ta.volatility.BollingerBands(df["close"], window=min(len(df), 20), window_dev=2)
            bb_high = float(bollinger.bollinger_hband().iloc[-1])
            bb_low = float(bollinger.bollinger_lband().iloc[-1])
        except Exception:
            bb_high, bb_low = canli_fiyat * 1.002, canli_fiyat * 0.998

        # 4. Alligator
        try:
            jaw = float(ta.trend.sma_indicator(df["close"], window=min(len(df), 13)).iloc[-1])
            teeth = float(ta.trend.sma_indicator(df["close"], window=min(len(df), 8)).iloc[-1])
            lips = float(ta.trend.sma_indicator(df["close"], window=min(len(df), 5)).iloc[-1])
        except Exception:
            jaw, teeth, lips = canli_fiyat, canli_fiyat, canli_fiyat

        yukari_puan = 0
        asagi_puan = 0

        if rsi < 40:
            yukari_puan += 2
        elif rsi > 60:
            asagi_puan += 2

        if canli_fiyat > sma_20:
            yukari_puan += 1
        else:
            asagi_puan += 1

        if canli_fiyat <= bb_low:
            yukari_puan += 2
        elif canli_fiyat >= bb_high:
            asagi_puan += 2

        alligator_durum = "⚪ Nötr / Karışık"
        if not (pd.isna(lips) or pd.isna(teeth) or pd.isna(jaw)):
            if lips > teeth > jaw:
                yukari_puan += 2
                alligator_durum = "🟢 YUKARI Trend"
            elif lips < teeth < jaw:
                asagi_puan += 2
                alligator_durum = "🔴 AŞAĞI Trend"

        if yukari_puan >= 4 and yukari_puan > asagi_puan:
            karar = "🟢 YUKARI (AL)"
        elif asagi_puan >= 4 and asagi_puan > yukari_puan:
            karar = "🔴 AŞAĞI (SAT)"
        else:
            karar = "⚪ NÖTR (BEKLE)"

        turkiye_zaman = datetime.now(ZoneInfo("Europe/Istanbul"))
        su_an = turkiye_zaman.strftime("%H:%M:%S")

        detay = (
            f"⏰ Analiz/Giriş Saati: {su_an}\n"
            f"💵 Canlı Fiyat: {canli_fiyat:.5f}\n"
            f"🔹 RSI (14): {rsi:.2f}\n"
            f"🔹 SMA (20): {sma_20:.5f}\n"
            f"🔹 Bollinger Alt/Üst: {bb_low:.5f} / {bb_high:.5f}\n"
            f"🔹 Alligator Durumu: {alligator_durum}\n\n"
            f"🎯 SİNYAL KARARI: {karar}"
        )

        return karar, detay
    except Exception as e:
        logging.error(f"Teknik analiz hesaplama hatası: {e}")
        return "⚪ NÖTR (BEKLE)", f"⏰ Zaman: {datetime.now().strftime('%H:%M:%S')}\n⚠️ Sistem hatası oluştu, lütfen tekrar deneyin."


# -------------------------------------------------------------
# TELEGRAM ARAYÜZÜ VE BUTONLAR
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    row = []

    for idx, name in enumerate(INDEX_TO_NAME):
        row.append(InlineKeyboardButton(name, callback_data=f"p_{idx}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 İkili Opsiyon Sinyal Botu (Twelve Data)\n\n"
        "Lütfen analiz etmek istediğiniz pariteyi seçin:",
        reply_markup=reply_markup,
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    try:
        if data.startswith("p_"):
            idx = int(data.replace("p_", ""))
            parite_adi = INDEX_TO_NAME[idx]
            symbol = PARITE_HARITASI[parite_adi]

            context.user_data["secilen_kod"] = symbol
            context.user_data["secilen_ad"] = parite_adi

            keyboard = [
                [
                    InlineKeyboardButton("⏱ 2 Dakika", callback_data="t_2"),
                    InlineKeyboardButton("⏱️ 3 Dakika", callback_data="t_3"),
                    InlineKeyboardButton("⏱️ 5 Dakika", callback_data="t_5"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=f"📌 Seçilen Parite: {parite_adi}\n\nLütfen işlem vadesini seçin:",
                reply_markup=reply_markup,
            )

        elif data.startswith("t_"):
            vade_dakika = int(data.replace("t_", ""))
            symbol = context.user_data.get("secilen_kod")
            parite_adi = context.user_data.get("secilen_ad")

            if not symbol:
                await query.edit_message_text("⚠️ Seçim zaman aşına uğradı. Lütfen /start yazarak tekrar başlayın.")
                return

            karar, detay = teknik_analiz_yap(symbol, vade_dakika=vade_dakika)

            mesaj = (
                f"📊 ANALİZ RAPORU ({parite_adi})\n"
                f"⏱ Vade Süresi: {vade_dakika} Dakika\n\n"
                f"{detay}"
            )
            await query.edit_message_text(text=mesaj)
            
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            logging.error(f"Telegram BadRequest hatası: {e}")
    except Exception as e:
        logging.warning(f"Buton işleme hatası: {e}")


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    logging.info("🤖 USD/JPY eklendi, bot çalışmaya hazır!")
    app.run_polling()
