# Campaña de correos — Libreta de Cobro

Script para el envío automático de correos de marketing presentando
**Libreta de Cobro** a negocios que venden a crédito o dan fiado.

## Requisitos

- Python 3.10 o superior (no usa librerías externas).
- Una cuenta de Gmail con **verificación en dos pasos** activada y una
  **contraseña de aplicación** (App Password). La contraseña normal de la
  cuenta no funciona:
  1. Entra a <https://myaccount.google.com/security> con la cuenta
     `info@libretadecobro.com`.
  2. Activa la verificación en dos pasos si no está activa.
  3. En <https://myaccount.google.com/apppasswords> genera una contraseña
     de aplicación. Google mostrará una clave de 16 caracteres — esa es la
     que se usa como `SMTP_PASSWORD`.

## Archivos

| Archivo          | Descripción                                                        |
|------------------|--------------------------------------------------------------------|
| `send_campaign.py` | Script principal de envío.                                       |
| `template.html`  | Cuerpo del correo en HTML (lo que ve el cliente).                  |
| `template.txt`   | Versión en texto plano (mejora la entregabilidad; opcional).       |
| `recipients.csv` | Lista de destinatarios: **un correo por línea**.                   |
| `sent.log`       | Se genera al enviar: correos ya enviados (permite reanudar).       |
| `campaign.log`   | Se genera al ejecutar: registro completo de la corrida.            |

## Configuración

Variables de entorno:

| Variable           | Obligatoria | Default                   | Descripción                          |
|--------------------|-------------|---------------------------|--------------------------------------|
| `SMTP_PASSWORD`    | **Sí**      | —                         | Contraseña de aplicación de Gmail.   |
| `APP_MAIL_FROM`    | No          | `info@libretadecobro.com` | Remitente (y usuario SMTP).          |
| `SPRING_MAIL_HOST` | No          | `smtp.gmail.com`          | Servidor SMTP.                       |
| `SPRING_MAIL_PORT` | No          | `587`                     | Puerto SMTP (STARTTLS).              |
| `APP_MAIL_FROM_NAME` | No        | `Libreta de Cobro`        | Nombre visible del remitente.        |
| `MAIL_DELAY_SECONDS` | No        | `2`                       | Pausa en segundos entre correos.     |
| `MAIL_RECONNECT_EVERY` | No      | `50`                      | Reconexión SMTP cada N envíos.       |

## Uso

```bash
cd /home/conor/eclipse-workspace/libretacobro-marketing

# 1. Configurar la contraseña (solo dura mientras la terminal esté abierta)
export SMTP_PASSWORD='xxxx xxxx xxxx xxxx'

# 2. Simulacro: muestra a quién se enviaría, sin enviar nada
python3 send_campaign.py --subject "Prueba" --dry-run

# 3. Prueba real a ti mismo antes de la campaña (recomendado)
echo "tucorreo@gmail.com" > prueba.csv
python3 send_campaign.py \
    --subject "¿Das crédito a tus clientes? Esto te puede servir" \
    --recipients prueba.csv

# 4. Envío de la campaña completa
python3 send_campaign.py \
    --subject "¿Das crédito a tus clientes? Esto te puede servir"
```

Opciones disponibles:

```
--subject         Asunto del correo (obligatorio)
--template        Plantilla HTML          (default: template.html)
--text-template   Plantilla texto plano   (default: template.txt)
--recipients      Lista de correos        (default: recipients.csv)
--dry-run         Simula sin conectar al servidor
```

## Cómo funciona

- **Lista de destinatarios**: un correo por línea en `recipients.csv`.
  Se ignoran líneas vacías y duplicados; las direcciones se normalizan a
  minúsculas.
- **Personalización**: dentro de las plantillas puedes usar `$email`,
  que se reemplaza por la dirección del destinatario.
- **Reanudación**: cada envío exitoso queda registrado en `sent.log`.
  Si el script se interrumpe (corte de luz, error de red), al volver a
  ejecutarlo omite los ya enviados y continúa donde quedó. Para lanzar
  una campaña nueva desde cero, borra `sent.log`.
- **Ritmo**: pausa de 2 segundos entre correos y reconexión al servidor
  cada 50 envíos, para no activar los límites anti-spam de Gmail.
- **Registro**: todo se guarda en `campaign.log` con el detalle de
  enviados y fallidos.

## Límites de Gmail y buenas prácticas

- Gmail permite **~500 correos/día** en cuentas gratuitas y **~2000/día**
  en Google Workspace. Si la lista supera el límite, divide el envío en
  varios días (el `sent.log` hace que puedas relanzar sin duplicar).
- Envía primero una prueba a tu propio correo y revisa que no caiga en
  spam, que las imágenes/colores se vean bien y que los enlaces funcionen.
- **Atiende las bajas**: si alguien responde con asunto `BAJA`, elimina
  su dirección de `recipients.csv` antes de la siguiente campaña.
- Para volúmenes grandes o envíos frecuentes conviene un servicio
  transaccional (Amazon SES, SendGrid, Brevo): solo cambia
  `SPRING_MAIL_HOST`, `SPRING_MAIL_PORT` y las credenciales.

## Editar el contenido del correo

- `template.html` — ábrelo en un navegador para previsualizarlo. El color
  principal es `#0F325A` (aparece en encabezado, botón y pie de contacto).
- `template.txt` — mantenlo sincronizado con el HTML: es lo que ven los
  clientes de correo sin HTML y ayuda a no caer en spam.
- Datos de contacto actuales: tel. +52 775 179 5049,
  info@libretadecobro.com, www.libretadecobro.com.
