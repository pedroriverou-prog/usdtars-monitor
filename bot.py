import os
import time
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
THRESHOLD_PCT = float(os.environ.get("THRESHOLD_PCT", "0.2"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

last_spot = None
last_p2p = None
last_ves = None
last_alert_time = 0
ALERT_COOLDOWN = 300


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        logging.info("Mensaje enviado a Telegram.")
    except Exception as e:
        logging.error(f"Error enviando Telegram: {e}")


def fetch_spot_price() -> float | None:
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


def fetch_p2p_ars_price() -> float | None:
    try:
        res = requests.get("https://criptoya.com/api/usdt/ars/1", timeout=10)
        res.raise_for_status()
        data = res.json()
        for exchange in ["fiwind", "decrypto", "tiendacrypto", "bitso"]:
            if exchange in data:
                price = data[exchange].get("totalAsk") or data[exchange].get("ask")
                if price:
                    logging.info(f"P2P ARS de criptoya/{exchange}: {price}")
                    return float(price)
    except Exception as e:
        logging.warning(f"Error P2P ARS: {e}")
    return None


def fetch_ves_rate() -> float | None:
    # Fuente 1: dolarapi.com (paralelo venezolano)
    try:
        res = requests.get(
            "https://ve.dolarapi.com/v1/dolares/paralelo",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        res.raise_for_status()
        data = res.json()
        price = data.get("promedio") or data.get("venta")
        if price:
            logging.info(f"VES paralelo/dolarapi: {price}")
            return float(price)
    except Exception as e:
        logging.warning(f"Error dolarapi: {e}")

    # Fallback: open.er-api.com
    try:
        res = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        res.raise_for_status()
        ves = res.json().get("rates", {}).get("VES")
        if ves:
            logging.info(f"VES de er-api: {ves}")
            return float(ves)
    except Exception as e:
        logging.warning(f"Error VES fallback: {e}")

    return None


def pct_change(old: float, new: float) -> float:
    return ((new - old) / old) * 100


def direction(change: float) -> str:
    return "📈 SUBE" if change > 0 else "📉 BAJA"


def format_alert(tipo: str, moneda: str, anterior: float, actual: float, cambio: float) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    signo = "+" if cambio > 0 else ""
    simbolo = "Bs" if moneda == "VES" else "$"
    return (
        f"⚡ <b>Variación {tipo} — {now}</b>\n\n"
        f"{direction(cambio)}\n\n"
        f"Anterior: <b>{simbolo}{anterior:,.2f}</b>\n"
        f"Actual:   <b>{simbolo}{actual:,.2f}</b>\n\n"
        f"Cambio: <b>{signo}{cambio:.2f}%</b>\n"
        f"Umbral: ±{THRESHOLD_PCT}%"
    )


def check_and_alert(tipo, moneda, actual, anterior, now):
    global last_alert_time
    if anterior is None or actual is None:
        return actual
    cambio = pct_change(anterior, actual)
    if abs(cambio) >= THRESHOLD_PCT and (now - last_alert_time) > ALERT_COOLDOWN:
        send_telegram(format_alert(tipo, moneda, anterior, actual, cambio))
        last_alert_time = now
        logging.info(f"Alerta {tipo}: {cambio:.2f}%")
    return actual


def main():
    global last_spot, last_p2p, last_ves

    logging.info("Bot iniciado. Umbral: %.2f%% | Intervalo: %ds", THRESHOLD_PCT, CHECK_INTERVAL)
    send_telegram(
        f"✅ <b>Bot de variación iniciado</b>\n\n"
        f"📊 Monitoreando:\n"
        f"  • USDT/ARS Spot\n"
        f"  • USDT/ARS P2P\n"
        f"  • USD/VES Paralelo\n\n"
        f"⚡ Alerta si cambia ±{THRESHOLD_PCT}%\n"
        f"🔁 Frecuencia: cada {CHECK_INTERVAL}s"
    )

    while True:
        now = time.time()
        spot = fetch_spot_price()
        p2p = fetch_p2p_ars_price()
        ves = fetch_ves_rate()

        last_spot = check_and_alert("USDT/ARS Spot", "ARS", spot, last_spot, now)
        last_p2p = check_and_alert("USDT/ARS P2P", "ARS", p2p, last_p2p, now)
        last_ves = check_and_alert("USD/VES Paralelo", "VES", ves, last_ves, now)

        if not any([spot, p2p, ves]):
            logging.warning("No se pudieron obtener precios.")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
