import asyncio
import logging
from datetime import datetime
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = "9058550581:AAFxXj6DBwIFS9oxyw3RRpsPkgWn6j2S0qo"
CHAT_ID = 8332918874
SIGNAL_MODE = "sensitive"

TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "AMD", "MU",
    "ASML", "PLTR", "ORCL", "CSCO", "INTC", "AMAT", "LRCX", "KLAC",
    "PANW", "CRWD", "ANET", "DELL", "IBM", "CRM", "ADBE", "NOW",
    "INTU", "QCOM", "TXN", "SNPS", "CDNS"
]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="UTC")

def get_signals(ticker: str) -> list[str]:
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 60:
            return []

        df["RSI"] = ta.rsi(df["Close"], length=14)
        macd = ta.macd(df["Close"])
        df = pd.concat([df, macd], axis=1)
        df["EMA9"] = ta.ema(df["Close"], length=9)
        df["EMA21"] = ta.ema(df["Close"], length=21)
        df["EMA50"] = ta.ema(df["Close"], length=50)
        df["Volume_MA"] = df["Volume"].rolling(20).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []
        price = float(last["Close"])
        rsi = float(last["RSI"])
        macd_line = float(last["MACD_12_26_9"])
        signal_line = float(last["MACDs_12_26_9"])
        hist = float(last["MACDh_12_26_9"])
        ema9 = float(last["EMA9"])
        ema21 = float(last["EMA21"])
        ema50 = float(last["EMA50"])
        vol = float(last["Volume"])
        vol_ma = float(last["Volume_MA"])

        buy_score = 0
        reasons = []

        if rsi < 35:
            buy_score += 2
            reasons.append(f"RSI={rsi:.1f} (перепродан)")
        elif rsi < 45:
            buy_score += 1
            reasons.append(f"RSI={rsi:.1f}")

        if macd_line > signal_line and prev["MACD_12_26_9"] <= prev["MACDs_12_26_9"]:
            buy_score += 2
            reasons.append("MACD бычий кросс")
        elif macd_line > signal_line and hist > 0:
            buy_score += 1
            reasons.append("MACD выше сигнала")

        if ema9 > ema21 > ema50:
            buy_score += 2
            reasons.append("Сильный восходящий тренд (EMA)")
        elif ema9 > ema21:
            buy_score += 1
            reasons.append("Краткосрочный тренд вверх")

        if vol > vol_ma * 1.3:
            buy_score += 1
            reasons.append("Повышенный объём")

        sell_score = 0
        sell_reasons = []

        if rsi > 70:
            sell_score += 2
            sell_reasons.append(f"RSI={rsi:.1f} (перекуплен)")
        elif rsi > 60:
            sell_score += 1
            sell_reasons.append(f"RSI={rsi:.1f}")

        if macd_line < signal_line and prev["MACD_12_26_9"] >= prev["MACDs_12_26_9"]:
            sell_score += 2
            sell_reasons.append("MACD медвежий кросс")
        elif macd_line < signal_line and hist < 0:
            sell_score += 1
            sell_reasons.append("MACD ниже сигнала")

        if ema9 < ema21 < ema50:
            sell_score += 2
            sell_reasons.append("Сильный нисходящий тренд")
        elif ema9 < ema21:
            sell_score += 1
            sell_reasons.append("Краткосрочный тренд вниз")

        if SIGNAL_MODE == "strong":
            buy_threshold = 4
            sell_threshold = 4
        else:
            buy_threshold = 3
            sell_threshold = 3

        result = []
        if buy_score >= buy_threshold:
            result.append(
                f"🟢 <b>BUY {ticker}</b>\n"
                f"Цена: ${price:.2f}\n"
                f"Сила: {buy_score}/7\n"
                f"{' | '.join(reasons)}"
            )
        if sell_score >= sell_threshold:
            result.append(
                f"🔴 <b>SELL {ticker}</b>\n"
                f"Цена: ${price:.2f}\n"
                f"Сила: {sell_score}/7\n"
                f"{' | '.join(sell_reasons)}"
            )

        return result

    except Exception as e:
        logging.error(f"Ошибка по {ticker}: {e}")
        return []

async def check_market():
    logging.info("Запуск проверки рынка...")
    all_signals = []

    for ticker in TICKERS:
        signals = get_signals(ticker)
        all_signals.extend(signals)
        await asyncio.sleep(1.5)

    if all_signals:
        header = f"📊 <b>Сигналы</b> ({datetime.utcnow().strftime('%d.%m %H:%M')} UTC)\nРежим: {SIGNAL_MODE}\n\n"
        text = header + "\n\n".join(all_signals)
        
        if len(text) > 4000:
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for chunk in chunks:
                await bot.send_message(CHAT_ID, chunk, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(CHAT_ID, text, parse_mode=ParseMode.HTML)
    else:
        logging.info("Сильных сигналов нет")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Бот запущен ✅\n"
        f"Режим: <b>{SIGNAL_MODE}</b>\n"
        "Проверка каждые 30 минут\n\n"
        "Команды:\n"
        "/check — проверить рынок прямо сейчас\n"
        "/mode strong — сильные сигналы\n"
        "/mode sensitive — больше сигналов",
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("Проверяю рынок... Это займёт ~1 минуту")
    await check_market()
    await message.answer("Готово")

@dp.message(Command("mode"))
async def cmd_mode(message: types.Message):
    global SIGNAL_MODE
    args = message.text.split()
    if len(args) > 1 and args[1] in ["strong", "sensitive"]:
        SIGNAL_MODE = args[1]
        await message.answer(f"Режим изменён на: <b>{SIGNAL_MODE}</b>", parse_mode=ParseMode.HTML)
    else:
        await message.answer("Используй: /mode strong или /mode sensitive")

async def main():
    scheduler.add_job(check_market, "interval", minutes=30)
    scheduler.start()
    await check_market()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())