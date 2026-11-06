# Campaña de correos — Libreta de Cobro

Script para el envío automático de correos de marketing presentando
**Libreta de Cobro** a negocios que venden a crédito o dan fiado.

## Requisitos

- Python 3.10 o superior (no usa librerías externas).
- Un buzón de **Hostinger Email** (`info@libretadecobro.com`). El usuario
  SMTP es la dirección completa y la contraseña es la del buzón:
  1. En hPanel entra a **Correos → Cuentas de correo** y verifica que el
     buzón `info@libretadecobro.com` exista (si no recuerdas la contraseña,
     cámbiala desde ahí).
  2. En **Correos → Configuración de clientes de correo** (o la sección de
     DNS del correo) confirma que **SPF, DKIM y DMARC** aparezcan en verde.
     Sin DKIM los correos tienen más probabilidad de caer en spam.
  3. Revisa el **límite de envío diario** de tu plan en hPanel: es por
     buzón y en ventana móvil de 24 horas (p. ej. 100/día en el correo
     gratuito incluido con el hosting, 1000/día en Business Starter).

## Archivos

| Archivo          | Descripción                                                        |
|------------------|--------------------------------------------------------------------|
| `send_campaign.py` | Script principal de envío.                                       |
| `.env.example`   | Plantilla de configuración SMTP (copiar como `.env`).              |
| `.env`           | Tu configuración real con la contraseña. **No se sube a git.**     |
| `template.html`  | Cuerpo del correo en HTML (lo que ve el cliente).                  |
| `template.txt`   | Versión en texto plano (mejora la entregabilidad; opcional).       |
| `recipients.csv` | Lista de destinatarios: **un correo por línea**.                   |
| `sent.log`       | Se genera al enviar: correos ya enviados (permite reanudar).       |
| `campaign.log`   | Se genera al ejecutar: registro completo de la corrida.            |

## Configuración

La configuración se lee del archivo `.env` que está junto al script.
Créalo una sola vez a partir de la plantilla:

```bash
cp .env.example .env
chmod 600 .env          # solo tu usuario puede leerlo
nano .env               # escribe la contraseña del buzón en SMTP_PASSWORD
```

Si una variable también está exportada en la terminal (`export ...`), esa
tiene prioridad sobre el `.env`. No pongas comentarios al final de una
línea del `.env`: se tomarían como parte del valor.

| Variable           | Obligatoria | Default                   | Descripción                          |
|--------------------|-------------|---------------------------|--------------------------------------|
| `SMTP_PASSWORD`    | **Sí**      | —                         | Contraseña del buzón de Hostinger.   |
| `APP_MAIL_FROM`    | No          | `info@libretadecobro.com` | Remitente.                           |
| `SMTP_USER`        | No          | igual a `APP_MAIL_FROM`   | Usuario SMTP (dirección completa).   |
| `SPRING_MAIL_HOST` | No          | `smtp.hostinger.com`      | Servidor SMTP.                       |
| `SPRING_MAIL_PORT` | No          | `465`                     | Puerto SMTP.                         |
| `SMTP_SECURITY`    | No          | `ssl` si el puerto es 465, si no `starttls` | Tipo de cifrado.   |
| `APP_MAIL_FROM_NAME` | No        | `Libreta de Cobro`        | Nombre visible del remitente.        |
| `MAIL_DELAY_SECONDS` | No        | `2`                       | Pausa en segundos entre correos.     |
| `MAIL_RECONNECT_EVERY` | No      | `50`                      | Reconexión SMTP cada N envíos.       |
| `MAIL_MAX_CONSECUTIVE_ERRORS` | No | `5`                     | Detiene la campaña tras N fallos seguidos. |

Para volver a usar Gmail u otro proveedor basta con cambiar en el `.env`
`SPRING_MAIL_HOST`, `SPRING_MAIL_PORT` (`587` → `starttls`), `SMTP_USER`
y `SMTP_PASSWORD`.

## Uso

```bash
cd /home/conor/eclipse-workspace/libretacobro-marketing

# 1. Configurar las credenciales (una sola vez; ver "Configuración")
cp .env.example .env && chmod 600 .env && nano .env

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
  cada 50 envíos, para no activar los límites anti-spam del proveedor.
- **Límite alcanzado**: si el servidor responde que se llegó al límite de
  envío, o fallan 5 envíos seguidos, la campaña se detiene (en lugar de
  recorrer toda la lista acumulando errores). Vuelve a ejecutarla más
  tarde y continuará donde quedó.
- **Conexión cerrada**: si el servidor corta la conexión a mitad de la
  campaña, el script se reconecta y reintenta ese correo.
- **Registro**: todo se guarda en `campaign.log` con el detalle de
  enviados y fallidos.

## Límites de Hostinger y buenas prácticas

- Hostinger limita los envíos **por buzón** en una ventana móvil de
  24 horas: el correo gratuito incluido con el hosting permite unos
  **100/día** y Business Starter **1000/día** (confirma el de tu plan en
  hPanel; Hostinger puede cambiarlo sin aviso). Si la lista supera el
  límite, divide el envío en varios días (el `sent.log` hace que puedas
  relanzar sin duplicar).
- El correo de Hostinger está pensado para correo de negocio, no para
  marketing masivo: muchos rebotes o quejas de spam pueden hacer que
  suspendan el envío del buzón. Mantén la lista limpia (quita direcciones
  que rebotan) y atiende las bajas.
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
