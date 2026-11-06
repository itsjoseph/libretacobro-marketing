#!/usr/bin/env python3
"""
Envío automático de correos para campañas de marketing de Libreta de Cobro.

La configuración se lee de variables de entorno o de un archivo .env junto
al script (ver .env.example). Las variables ya exportadas en la terminal
tienen prioridad sobre el .env.

Variables:
  APP_MAIL_FROM     Remitente           (default: info@libretadecobro.com)
  SMTP_USER         Usuario SMTP        (default: igual a APP_MAIL_FROM)
  SMTP_PASSWORD     Contraseña SMTP     (obligatoria; en Hostinger es la del buzón)
  SPRING_MAIL_HOST  Servidor SMTP       (default: smtp.hostinger.com)
  SPRING_MAIL_PORT  Puerto SMTP         (default: 465)
  SMTP_SECURITY     ssl | starttls      (default: ssl si el puerto es 465, si no starttls)

Uso:
  cp .env.example .env    # y escribe la contraseña del buzón en SMTP_PASSWORD
  python3 send_campaign.py --subject "Novedades de agosto" \
      --template template.html --recipients recipients.csv

  # Simulacro sin enviar nada:
  python3 send_campaign.py --subject "Prueba" --dry-run
"""

import argparse
import logging
import os
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from string import Template


def load_env_file(path: Path) -> None:
    """Carga líneas KEY=valor de un archivo .env (sin librerías externas).
    No pisa variables ya definidas en el entorno. No admite comentarios al
    final de la línea, para que una contraseña con '#' se lea completa."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env_file(Path(__file__).resolve().parent / ".env")

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
APP_MAIL_FROM = os.environ.get("APP_MAIL_FROM", "info@libretadecobro.com")
SMTP_USER = os.environ.get("SMTP_USER") or APP_MAIL_FROM
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SPRING_MAIL_HOST = os.environ.get("SPRING_MAIL_HOST", "smtp.hostinger.com")
SPRING_MAIL_PORT = int(os.environ.get("SPRING_MAIL_PORT", "465"))
SMTP_SECURITY = os.environ.get(
    "SMTP_SECURITY", "ssl" if SPRING_MAIL_PORT == 465 else "starttls"
).strip().lower()
if SMTP_SECURITY not in ("ssl", "starttls"):
    raise SystemExit(f"SMTP_SECURITY debe ser 'ssl' o 'starttls', no '{SMTP_SECURITY}'.")

FROM_NAME = os.environ.get("APP_MAIL_FROM_NAME", "Libreta de Cobro")

# Pausa entre correos para no exceder los límites del proveedor.
# Hostinger: el límite diario es por buzón y depende del plan (ver hPanel).
DELAY_SECONDS = float(os.environ.get("MAIL_DELAY_SECONDS", "2"))

# Cada cuántos envíos se reconecta al servidor (evita cortes por sesión larga).
RECONNECT_EVERY = int(os.environ.get("MAIL_RECONNECT_EVERY", "50"))

# Si fallan tantos envíos seguidos, se detiene la campaña en vez de recorrer
# toda la lista acumulando errores.
MAX_CONSECUTIVE_ERRORS = int(os.environ.get("MAIL_MAX_CONSECUTIVE_ERRORS", "5"))

# Textos con los que los servidores avisan que se alcanzó el límite de envío.
LIMIT_HINTS = ("limit", "quota", "too many", "rate")

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
    context = ssl.create_default_context()
    if SMTP_SECURITY == "ssl":
        server = smtplib.SMTP_SSL(SPRING_MAIL_HOST, SPRING_MAIL_PORT, timeout=30, context=context)
        server.ehlo()
    else:
        server = smtplib.SMTP(SPRING_MAIL_HOST, SPRING_MAIL_PORT, timeout=30)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
    server.login(SMTP_USER, SMTP_PASSWORD)
    return server


def close_quietly(server: smtplib.SMTP) -> None:
    try:
        server.quit()
    except Exception:
        server.close()


def reconnect(server: smtplib.SMTP) -> smtplib.SMTP:
    close_quietly(server)
    return connect()


def is_limit_error(exc: Exception) -> bool:
    return any(hint in str(exc).lower() for hint in LIMIT_HINTS)


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
        raise SystemExit("Falta SMTP_PASSWORD (en el archivo .env o como variable de entorno).")

    try:
        server = connect()
    except smtplib.SMTPAuthenticationError as exc:
        raise SystemExit(f"El servidor rechazó el usuario/contraseña de {SMTP_USER}: {exc}")
    log.info("Conectado a %s:%s (%s) como %s", SPRING_MAIL_HOST, SPRING_MAIL_PORT,
             SMTP_SECURITY.upper(), SMTP_USER)

    ok, failed, consecutive_errors = 0, 0, 0
    try:
        with sent_log_path.open("a", encoding="utf-8") as sent_log:
            for i, recipient in enumerate(pending, start=1):
                msg = build_message(subject, html_tpl, text_tpl, recipient)
                try:
                    if i > 1 and (i - 1) % RECONNECT_EVERY == 0:
                        server = reconnect(server)
                        log.info("Reconexión SMTP tras %d envíos", i - 1)
                    try:
                        server.send_message(msg)
                    except smtplib.SMTPServerDisconnected:
                        log.warning("El servidor cerró la conexión; reconectando...")
                        server = reconnect(server)
                        server.send_message(msg)
                except smtplib.SMTPRecipientsRefused as exc:
                    failed += 1
                    consecutive_errors += 1
                    log.error("(%d/%d) Rechazado %s: %s", i, len(pending), recipient["email"], exc)
                except OSError as exc:  # SMTPException, timeouts y errores de red
                    failed += 1
                    consecutive_errors += 1
                    log.error("(%d/%d) Error con %s: %s", i, len(pending), recipient["email"], exc)
                    if is_limit_error(exc):
                        log.error("El servidor indica que se alcanzó el límite de envío. "
                                  "Campaña detenida: vuelve a ejecutar el script más tarde "
                                  "y continuará donde quedó (sent.log).")
                        break
                else:
                    ok += 1
                    consecutive_errors = 0
                    sent_log.write(recipient["email"].lower() + "\n")
                    sent_log.flush()
                    log.info("(%d/%d) Enviado a %s", i, len(pending), recipient["email"])

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    log.error("%d errores seguidos. Campaña detenida: revisa campaign.log "
                              "y vuelve a ejecutar el script para continuar.", consecutive_errors)
                    break
                if i < len(pending):
                    time.sleep(DELAY_SECONDS)
    finally:
        close_quietly(server)

    log.info("Campaña terminada: %d enviados, %d fallidos, %d omitidos (ya enviados antes). "
             "Quedan %d por enviar en la próxima ejecución.",
             ok, failed, len(recipients) - len(pending), len(pending) - ok)


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
