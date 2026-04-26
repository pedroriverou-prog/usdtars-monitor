import os
import time
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
THRESHOLD_PCT = float(os.environ.get("THRESHOLD_PCT", "0.5"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

# Precios anteriores para comparar
last_spot = None
last_p2p = None
last_alert_time = 0
ALERT_COOLDOWN = 300  # 5 minutos entre alertas del mismo tipo


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
    """USDT/ARS Spot via criptoya."""
    try:
        res = requests.get("https://criptoya.com/api/usdt/ars/1", timeout=10)
        res.raise_for_status()
        data = res.json()
        for exchange in ["lemoncash", "ripio", "belo", "buenbit", "satoshitango"]:
            if exchange in data:
                price = data[exchange].get("totalAsk") or data[exchange].get("ask")
                if price:
                    logging.info(f"Spot de criptoya/{exchange}: {price}")
                    return float(price)
    except Exception as e:
        logging.warning(f"Error spot: {e}")
    return None


def fetch_p2p_price() -> float | None:
    """USDT/ARS P2P via criptoya."""
    try:
        res = requests.get("https://criptoya.com/api/usdt/ars/1", timeout=10)
        res.raise_for_status()
        data = res.json()
        for exchange in ["fiwind", "decrypto", "tiendacrypto", "bitso"]:
            if exchange in data:
                price = data[exchange].get("totalAsk") or data[exchange].get("ask")
                if price:
                    logging.info(f"P2P de criptoya/{exchange}: {price}")
                    return float(price)
    except Exception as e:
        logging.warning(f"Error P2P: {e}")
    return None


def pct_change(old: float, new: float) -> float:
    return ((new - old) / old) * 100


def direction(change: float) -> str:
    return "📈 SUBE" if change > 0 else "📉 BAJA"


def format_alert(tipo: str, precio_anterior: float, precio_actual: float, cambio: float) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    signo = "+" if cambio > 0 else ""
    return (
        f"⚡ <b>Variación USDT/{tipo} — {now}</b>\n\n"
        f"{direction(cambio)}\n\n"
        f"Anterior: <b>${precio_anterior:,.0f}</b>\n"
        f"Actual:   <b>${precio_actual:,.0f}</b>\n\n"
        f"Cambio: <b>{signo}{cambio:.2f}%</b>\n"
        f"Umbral configurado: {THRESHOLD_PCT}%"
    )


def main():
    global last_spot, last_p2p, last_alert_time

    logging.info("Bot iniciado. Umbral: %.2f%% | Intervalo: %ds", THRESHOLD_PCT, CHECK_INTERVAL)
    send_telegram(
        f"✅ <b>Bot de variación iniciado</b>\n"
        f"Monitoreo: USDT Spot y P2P (ARS)\n"
        f"Alerta si cambia ±{THRESHOLD_PCT}%\n"
        f"Frecuencia: cada {CHECK_INTERVAL}s"
    )

    while True:
        spot = fetch_spot_price()
        p2p = fetch_p2p_price()
        now = time.time()

        # Chequear variación Spot
        if spot:
            if last_spot is not None:
                cambio_spot = pct_change(last_spot, spot)
                if abs(cambio_spot) >= THRESHOLD_PCT and (now - last_alert_time) > ALERT_COOLDOWN:
                    msg = format_alert("Spot", last_spot, spot, cambio_spot)
                    send_telegram(msg)
                    last_alert_time = now
                    logging.info(f"Alerta Spot enviada: {cambio_spot:.2f}%")
            last_spot = spot

        # Chequear variación P2P
        if p2p:
            if last_p2p is not None:
                cambio_p2p = pct_change(last_p2p, p2p)
                if abs(cambio_p2p) >= THRESHOLD_PCT and (now - last_alert_time) > ALERT_COOLDOWN:
                    msg = format_alert("P2P", last_p2p, p2p, cambio_p2p)
                    send_telegram(msg)
                    last_alert_time = now
                    logging.info(f"Alerta P2P enviada: {cambio_p2p:.2f}%")
            last_p2p = p2p

        if not spot and not p2p:
            logging.warning("No se pudieron obtener precios.")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
