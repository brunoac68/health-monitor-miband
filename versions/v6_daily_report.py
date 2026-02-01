import sqlite3
from pathlib import Path
from datetime import datetime, date
import requests

# =========================
# CONFIGURAÇÃO
# =========================

DB_PATH = Path("health.db")

NTFY_SERVER = "https://ntfy.sh"
NTFY_TOPIC = "vo-saude-bruno"

# =========================
# RELATÓRIO
# =========================

def get_daily_stats(target_date: date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) as total,
            AVG(bpm) as avg_bpm,
            MIN(bpm) as min_bpm,
            MAX(bpm) as max_bpm
        FROM heart_rate
        WHERE date(timestamp) = ?
    """, (target_date.isoformat(),))

    row = cur.fetchone()
    conn.close()

    if not row or row[0] == 0:
        return None

    return {
        "total": int(row[0]),
        "avg": round(row[1], 1),
        "min": int(row[2]),
        "max": int(row[3])
    }

def send_ntfy_report(message):
    try:
        requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=message.encode("utf-8", errors="ignore"),
            headers={
                "Title": "RELATORIO DIARIO SAUDE",
                "Priority": "default",
                "Tags": "bar_chart,heart"
            },
            timeout=5
        )
    except Exception as e:
        print(f"Erro ao enviar relatório ntfy: {e}")

# =========================
# MAIN
# =========================

def main():
    today = date.today()
    stats = get_daily_stats(today)

    if not stats:
        print("Nenhum dado encontrado para hoje.")
        return

    report = (
        "📊 RELATÓRIO DIÁRIO – SAÚDE\n"
        f"📅 Data: {today.strftime('%d/%m/%Y')}\n\n"
        f"❤️ Média BPM: {stats['avg']}\n"
        f"⬇️ Mínimo BPM: {stats['min']}\n"
        f"⬆️ Máximo BPM: {stats['max']}\n"
        f"📈 Total de medições: {stats['total']}"
    )

    print(report)
    send_ntfy_report(report)

if __name__ == "__main__":
    main()
