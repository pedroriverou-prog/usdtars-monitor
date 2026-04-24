import os
import time
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
THRESHOLD_PCT = float(os.environ.get("THRESHOLD_PCT", "3.0"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

last_alert_time = 0
ALERT_COOLDOWN = 1800


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


def fetch_ars_price() -> float | None:
    """USDT/ARS via criptoya.com — agrega precios de múltiples exchanges."""
    sources = [
        ("https://criptoya.com/api/usdt/ars/1", ["totalAsk", "totalBid", "ask", "bid"]),
        ("https://api.bluelytics.com.ar/v2/latest", None),  # fallback dólar blue
    ]
    # Fuente 1: criptoya
    try:
        res = requests.get("https://criptoya.com/api/usdt/ars/1", timeout=10)
        res.raise_for_status()
        data = res.json()
        # Busca el precio en distintos exchanges conocidos
        for exchange in ["lemoncash", "ripio", "belo", "buenbit", "satoshitango"]:
            if exchange in data:
                price = data[exchange].get("totalAsk") or data[exchange].get("ask")
                if price:
                    logging.info(f"Precio ARS obtenido de criptoya/{exchange}: {price}")
                    return float(price)
    except Exception as e:
        logging.warning(f"Error criptoya: {e}")

    # Fuente 2: dolarito
    try:
        res = requests.get("https://api.dolarito.ar/api/frontend/usdt", timeout=10)
        res.raise_for_status()
        data = res.json()
        price = data.get("sell") or data.get("buy")
        if price:
            logging.info(f"Precio ARS obtenido de dolarito: {price}")
            return float(price)
    except Exception as e:
        logging.warning(f"Error dolarito: {e}")

    # Fuente 3: bluelytics (dólar blue como referencia base)
    try:
        res = requests.get("https://api.bluelytics.com.ar/v2/latest", timeout=10)
        res.raise_for_status()
        data = res.json()
        price = data.get("blue", {}).get("value_sell")
        if price:
            logging.info(f"Precio ARS obtenido de bluelytics (blue): {price}")
            return float(price)
    except Exception as e:
        logging.warning(f"Error bluelytics: {e}")

    return None


def fetch_p2p_price() -> float | None:
    """USDT/ARS P2P via criptoya — promedio de vendors P2P."""
    try:
        res = requests.get("https://criptoya.com/api/usdt/ars/1", timeout=10)
        res.raise_for_status()
        data = res.json()
        # Busca exchanges con mayor spread (más parecidos a P2P)
        for exchange in ["fiwind", "decrypto", "tiendacrypto", "bitso"]:
            if exchange in data:
                price = data[exchange].get("totalAsk") or data[exchange].get("ask")
                if price:
                    logging.info(f"Precio P2P obtenido de criptoya/{exchange}: {price}")
                    return float(price)
    except Exception as e:
        logging.warning(f"Error P2P criptoya: {e}")
    return None


def fetch_ves_rate() -> float | None:
    """Tasa de referencia USD/VES via exchangerate.host (no requiere key)."""
    try:
        res = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=10,
        )
        res.raise_for_status()
        data = res.json()
        ves = data.get("rates", {}).get("VES")
        if ves:
            return float(ves)
    except Exception as e:
        logging.warning(f"Error VES er-api: {e}")

    # Fallback
    try:
        res = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=10,
        )
        res.raise_for_status()
        ves = res.json().get("rates", {}).get("VES")
        if ves:
            return float(ves)
    except Exception as e:
        logging.warning(f"Error VES fallback: {e}")

    return None


def calculate_spread(spot: float, p2p: float) -> float:
    return ((p2p - spot) / spot) * 100


def format_alert(spot, p2p, ves, spread) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    status = "🟢 <b>OPERAR AHORA</b>" if spread >= THRESHOLD_PCT else "🔴 Spread bajo umbral"
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
        spot = fetch_ars_price()
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
