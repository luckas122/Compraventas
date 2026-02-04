# app/email_helper.py
from typing import List, Optional
import os, smtplib, socket
from email.message import EmailMessage
from app.config import load as load_config

def send_mail_with_attachments(subject: str, body: str,
                               recipients: List[str],
                               attachments: Optional[List[str]] = None) -> None:
    """
    Envío SMTP con diagnóstico y fallback:
    1) INTENTA: host:587 + STARTTLS
    2) FALLBACK: host:465 + SSL
    Lanza excepción descriptiva si falla.
    """
    cfg = load_config()
    e = (cfg.get("email") or {})
    smtp = (e.get("smtp") or {})

    host = (smtp.get("host") or "").strip()
    port = int(smtp.get("port") or 587)
    use_tls = bool(smtp.get("use_tls", True))
    user = (smtp.get("username") or "").strip()
    pwd  = smtp.get("password") or ""
    sender = (e.get("sender") or user or "").strip()
    bcc = e.get("bcc") or []

    if not host:
        raise RuntimeError("SMTP: faltan 'host/puerto'.")
    if not sender:
        raise RuntimeError("SMTP: faltan 'sender/username'.")
    if not user or not pwd:
        raise RuntimeError("SMTP: faltan 'username/password'.")
    if not recipients:
        raise RuntimeError("No hay destinatarios configurados.")

    msg = EmailMessage()
    msg["Subject"] = subject or "Reporte"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg.set_content(body or "")

    for path in (attachments or []):
        with open(path, "rb") as f:
            data = f.read()
        msg.add_attachment(data, maintype="application",
                           subtype="octet-stream",
                           filename=os.path.basename(path))

    socket.setdefaulttimeout(15)

    last_error = None
    # 1) 587 STARTTLS si así está configurado
    try:
        if use_tls and port == 587:
            s = smtplib.SMTP(host, 587, timeout=15)
            s.ehlo(); s.starttls(); s.ehlo()
        else:
            s = smtplib.SMTP(host, port, timeout=15)
        s.login(user, pwd)
        s.send_message(msg)
        s.quit()
        return
    except (smtplib.SMTPConnectError, socket.timeout, OSError) as ex:
        last_error = ex
    except smtplib.SMTPAuthenticationError as ex:
        raise RuntimeError("SMTP: autenticación fallida. En Gmail usá 'Contraseña de aplicación'.") from ex
    except Exception as ex:
        last_error = ex

    # 2) Fallback SSL 465
    try:
        s = smtplib.SMTP_SSL(host, 465, timeout=15)
        s.login(user, pwd)
        s.send_message(msg)
        s.quit()
        return
    except smtplib.SMTPAuthenticationError as ex:
        raise RuntimeError("SMTP: autenticación fallida (SSL 465). Verificá usuario/contraseña de aplicación.") from ex
    except Exception as ex:
        raise RuntimeError(f"No se pudo conectar al SMTP ({host}). "
                           f"Probá revisar firewall/red o usar 465/587. "
                           f"Detalle 587->465: {last_error} / {ex}")
        
        
     # 
# --- Pegar al final de app/email_helper.py ---

def send_historial_via_email(subject_prefix=None, body="", attachments=None, recipients=None):
    """
    Wrapper robusto para enviar el Historial usando la config en app_config.json.
    Retorna (ok: bool, err: str|None).
    Se considera envío OK si no hay excepción al llamar a send_mail_with_attachments.
    """
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
    except Exception:
        ZoneInfo = None

    from app.config import load as load_config
    cfg = load_config() or {}

    email_cfg = (cfg.get("email") or {})
    recips = list(recipients or email_cfg.get("recipients") or [])
    if not recips:
        return False, "No hay destinatarios configurados (email.recipients)."

    subj_pref = subject_prefix if subject_prefix is not None else (email_cfg.get("subject_prefix") or "[Historial]")
    tzid = ((cfg.get("general") or {}).get("timezone") or "America/Argentina/Buenos_Aires")
    now = datetime.now(ZoneInfo(tzid)) if ZoneInfo else datetime.now()
    subject = f"{subj_pref} {now.strftime('%Y-%m-%d')}"

    # attachments puede ser None o lista
    attachments = attachments or []

    try:
        # send_mail_with_attachments está importado en tu main_window; lo usamos aquí.
        # Debe estar definido en app.email_helper o importable desde la cabecera del módulo.
        from app.email_helper import send_mail_with_attachments as _send
    except Exception:
        # Intentamos buscar en el módulo top-level si fue importado con otro nombre
        try:
            from app import email_helper as _eh
            _send = getattr(_eh, "send_mail_with_attachments", None)
        except Exception:
            _send = None

    if not _send:
        # No encontramos el helper; devolvemos error claro.
        return False, "No se encontró la función send_mail_with_attachments en app.email_helper."

    try:
        res = _send(subject, body, recips, attachments)
        # Comportamiento tolerante: si devuelve True => ok.
        # Si devuelve None (comportamiento habitual en algunos helpers), lo consideramos OK si no saltó excepción.
        if res is True or res is None:
            print(f"[email-helper] enviado OK a {recips} (subject='{subject}').")
            return True, None
        else:
            # Si devuelve False o cadena de error, lo reportamos
            if isinstance(res, str):
                return False, res
            return False, "send_mail_with_attachments retornó falsy."
    except Exception as ex:
        # Capturamos cualquier excepción y la devolvemos como mensaje de error
        import traceback
        tb = traceback.format_exc()
        print(f"[email-helper] excepción enviando correo: {ex}\n{tb}")
        return False, str(ex)

