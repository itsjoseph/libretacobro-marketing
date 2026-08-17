#!/usr/bin/env python3
"""
Envío automático de correos para campañas de marketing de Libreta de Cobro.

Variables de entorno:
  APP_MAIL_FROM     Remitente           (default: info@libretadecobro.com)
  SMTP_PASSWORD     Contraseña SMTP     (obligatoria; en Gmail usar App Password)
  SPRING_MAIL_HOST  Servidor SMTP       (default: smtp.gmail.com)
  SPRING_MAIL_PORT  Puerto SMTP         (default: 587)

Uso:
  export SMTP_PASSWORD='xxxx xxxx xxxx xxxx'
  python3 send_campaign.py --subject "Novedades de agosto" \
      --template template.html --recipients recipients.csv

  # Simulacro sin enviar nada:
  python3 send_campaign.py --subject "Prueba" --dry-run
"""

import argparse
import logging
import os
import smtplib
import sys
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from string import Template

# ---------------------------------------------------------------------------
# Configuración desde variables de entorno
# ---------------------------------------------------------------------------
APP_MAIL_FROM = os.environ.get("APP_MAIL_FROM", "info@libretadecobro.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SPRING_MAIL_HOST = os.environ.get("SPRING_MAIL_HOST", "smtp.gmail.com")
SPRING_MAIL_PORT = int(os.environ.get("SPRING_MAIL_PORT", "587"))

FROM_NAME = os.environ.get("APP_MAIL_FROM_NAME", "Libreta de Cobro")

# Pausa entre correos para no exceder los límites del proveedor.
# Gmail: ~500/día en cuentas gratuitas, ~2000/día en Google Workspace.
DELAY_SECONDS = float(os.environ.get("MAIL_DELAY_SECONDS", "2"))

# Cada cuántos envíos se reconecta al servidor (evita cortes por sesión larga).
RECONNECT_EVERY = int(os.environ.get("MAIL_RECONNECT_EVERY", "50"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("campaign.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("campaign")


def load_recipients(list_path: Path) -> list[dict]:
    """Lee la lista de destinatarios: un correo por línea (se ignora una
    cabecera 'email' opcional). Normaliza a minúsculas y elimina duplicados."""
    recipients: list[dict] = []
    seen: set[str] = set()
    total = 0
    for line in list_path.read_text(encoding="utf-8").splitlines():
        value = line.strip().strip(",;")
        if not value or value.lower() == "email":
            continue
        total += 1
        if "@" not in value:
            log.warning("Línea ignorada (no parece un correo): %s", value)
            continue
        email = value.lower()
        if email in seen:
            continue
        seen.add(email)
        recipients.append({"email": email})
    log.info("Destinatarios cargados: %d (de %d líneas)", len(recipients), total)
    return recipients


def load_sent_log(path: Path) -> set[str]:
    """Correos ya enviados en ejecuciones anteriores (para poder reanudar)."""
    if not path.exists():
        return set()
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def build_message(subject: str, html_tpl: Template, text_tpl: Template, recipient: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((FROM_NAME, APP_MAIL_FROM))
    msg["To"] = recipient["email"]
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=APP_MAIL_FROM.split("@")[-1])
    # Cabecera estándar para que los clientes de correo ofrezcan darse de baja.
    msg["List-Unsubscribe"] = f"<mailto:{APP_MAIL_FROM}?subject=BAJA>"

    variables = {"email": recipient["email"], **recipient}
    msg.set_content(text_tpl.safe_substitute(variables))
    msg.add_alternative(html_tpl.safe_substitute(variables), subtype="html")
    return msg


def connect() -> smtplib.SMTP:
    server = smtplib.SMTP(SPRING_MAIL_HOST, SPRING_MAIL_PORT, timeout=30)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(APP_MAIL_FROM, SMTP_PASSWORD)
    return server


def run_campaign(subject: str, template_path: Path, text_path: Path | None,
                 recipients_path: Path, dry_run: bool) -> None:
    html_tpl = Template(template_path.read_text(encoding="utf-8"))
    if text_path and text_path.exists():
        text_tpl = Template(text_path.read_text(encoding="utf-8"))
    else:
        text_tpl = Template("Hola,\n\nAbre este correo en un cliente compatible con HTML.\n\n"
                            f"Para darte de baja responde con asunto BAJA a {APP_MAIL_FROM}.")

    recipients = load_recipients(recipients_path)
    sent_log_path = Path("sent.log")
    already_sent = load_sent_log(sent_log_path)
    pending = [r for r in recipients if r["email"].lower() not in already_sent]
    if already_sent:
        log.info("Se omiten %d correos ya enviados (sent.log)", len(recipients) - len(pending))

    if dry_run:
        for r in pending:
            log.info("[DRY-RUN] Se enviaría a %s", r["email"])
        log.info("[DRY-RUN] Total: %d correos. No se envió nada.", len(pending))
        return

    if not SMTP_PASSWORD:
        raise SystemExit("Falta la variable de entorno SMTP_PASSWORD.")

    server = connect()
    log.info("Conectado a %s:%s como %s", SPRING_MAIL_HOST, SPRING_MAIL_PORT, APP_MAIL_FROM)

    ok, failed = 0, 0
    try:
        with sent_log_path.open("a", encoding="utf-8") as sent_log:
            for i, recipient in enumerate(pending, start=1):
                if i > 1 and (i - 1) % RECONNECT_EVERY == 0:
                    server.quit()
                    server = connect()
                    log.info("Reconexión SMTP tras %d envíos", i - 1)
                try:
                    msg = build_message(subject, html_tpl, text_tpl, recipient)
                    server.send_message(msg)
                    ok += 1
                    sent_log.write(recipient["email"].lower() + "\n")
                    sent_log.flush()
                    log.info("(%d/%d) Enviado a %s", i, len(pending), recipient["email"])
                except smtplib.SMTPRecipientsRefused as exc:
                    failed += 1
                    log.error("(%d/%d) Rechazado %s: %s", i, len(pending), recipient["email"], exc)
                except smtplib.SMTPException as exc:
                    failed += 1
                    log.error("(%d/%d) Error con %s: %s", i, len(pending), recipient["email"], exc)
                if i < len(pending):
                    time.sleep(DELAY_SECONDS)
    finally:
        try:
            server.quit()
        except Exception:
            pass

    log.info("Campaña terminada: %d enviados, %d fallidos, %d omitidos.",
             ok, failed, len(recipients) - len(pending))


def main() -> None:
    parser = argparse.ArgumentParser(description="Envío de campaña de marketing por correo.")
    parser.add_argument("--subject", required=True, help="Asunto del correo")
    parser.add_argument("--template", default="template.html", type=Path,
                        help="Plantilla HTML (default: template.html)")
    parser.add_argument("--text-template", default=Path("template.txt"), type=Path,
                        help="Plantilla de texto plano opcional (default: template.txt)")
    parser.add_argument("--recipients", default=Path("recipients.csv"), type=Path,
                        help="Lista de correos, uno por línea (default: recipients.csv)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simula el envío sin conectar al servidor SMTP")
    args = parser.parse_args()

    if not args.template.exists():
        raise SystemExit(f"No existe la plantilla {args.template}")
    if not args.recipients.exists():
        raise SystemExit(f"No existe el archivo de destinatarios {args.recipients}")

    run_campaign(args.subject, args.template, args.text_template, args.recipients, args.dry_run)


if __name__ == "__main__":
    main()
