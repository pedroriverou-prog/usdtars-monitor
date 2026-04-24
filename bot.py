import os
import time
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
THRESHOLD_PCT = float(os.environ.get("THRESHOLD_PCT", "3.0"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))  # segundos

last_alert_time = 0
ALERT_COOLDOWN = 1800  # no repetir alerta por 30 minutos


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logging.info("Mensaje enviado a Telegram.")
    except Exception as e:
        logging.error(f"Error enviando Telegram: {e}")


def fetch_spot_price() -> float | None:
    """USDT/ARS precio spot en Binance."""
    try:
        res = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "USDTARS"},
            timeout=10,
        )
        res.raise_for_status()
        return float(res.json()["price"])
    except Exception as e:
        logging.warning(f"Error spot: {e}")
        return None


def fetch_p2p_price() -> float | None:
    """USDT/ARS mejor precio P2P en Binance (compra)."""
    try:
        body = {
            "asset": "USDT",
            "fiat": "ARS",
            "merchantCheck": False,
            "page": 1,
            "payTypes": [],
            "publisherType": None,
            "rows": 5,
            "tradeType": "BUY",
        }
        res = requests.post(
            "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search",
            json=body,
            timeout=10,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("data"):
            return float(data["data"][0]["adv"]["price"])
    except Exception as e:
        logging.warning(f"Error P2P: {e}")
    return None


def fetch_ves_rate() -> float | None:
    """Tasa de referencia USD/VES."""
    try:
        res = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=10,
        )
        res.raise_for_status()
        return res.json().get("rates", {}).get("VES")
    except Exception as e:
        logging.warning(f"Error VES: {e}")
        return None


def calculate_spread(spot: float, p2p: float) -> float:
    return ((p2p - spot) / spot) * 100


def format_alert(spot, p2p, ves, spread) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    status = "🟢 <b>OPERAR AHORA</b>" if spread >= THRESHOLD_PCT else "🔴 Spread bajo"
    return (
        f"📊 <b>Monitor USDT — {now}</b>\n\n"
        f"🇦🇷 Spot (ARS): <b>${spot:,.0f}</b>\n"
        f"🇦🇷 P2P  (ARS): <b>${p2p:,.0f}</b>\n"
        f"🇻🇪 Ref  (VES): <b>Bs {ves:,.0f}</b>\n\n"
        f"📈 Spread: <b>{spread:.2f}%</b>\n"
        f"⚡ Umbral: {THRESHOLD_PCT}%\n\n"
        f"{status}"
    )


def main():
    global last_alert_time

    logging.info("Bot iniciado. Umbral: %.1f%% | Intervalo: %ds", THRESHOLD_PCT, CHECK_INTERVAL)
    send_telegram(
        f"✅ <b>Bot iniciado</b>\nMonitoreando USDT/ARS cada {CHECK_INTERVAL}s\nUmbral de alerta: {THRESHOLD_PCT}%"
    )

    while True:
        spot = fetch_spot_price()
        p2p = fetch_p2p_price()
        ves = fetch_ves_rate()

        if spot and p2p and ves:
            spread = calculate_spread(spot, p2p)
            logging.info("Spot: %.0f | P2P: %.0f | VES: %.0f | Spread: %.2f%%", spot, p2p, ves, spread)

            now = time.time()
            if spread >= THRESHOLD_PCT and (now - last_alert_time) > ALERT_COOLDOWN:
                msg = format_alert(spot, p2p, ves, spread)
                send_telegram(msg)
                last_alert_time = now
        else:
            logging.warning("No se pudieron obtener todos los precios.")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
