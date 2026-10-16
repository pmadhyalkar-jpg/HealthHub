"""Email delivery helpers. SMTP is optional in local development and required for live email delivery."""
import os
import smtplib
from email.message import EmailMessage
from flask import current_app


def send_email(to_address: str, subject: str, text_body: str, html_body: str | None = None) -> bool:
    host = os.getenv('SMTP_HOST', '').strip()
    if not host:
        current_app.logger.warning('SMTP is not configured; email to %s was not delivered. Subject: %s', to_address, subject)
        return False
    port = int(os.getenv('SMTP_PORT', '587'))
    username = os.getenv('SMTP_USERNAME', '')
    password = os.getenv('SMTP_PASSWORD', '')
    sender = os.getenv('SMTP_FROM', username)
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to_address
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype='html')
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            if os.getenv('SMTP_USE_TLS', 'true').lower() in ('1', 'true', 'yes'):
                smtp.starttls()
                smtp.ehlo()
            if username:
                smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception:
        current_app.logger.exception('Email delivery failed for %s', to_address)
        return False


def send_appointment_confirmation(patient_email: str, patient_name: str, doctor_email: str | None,
                                  doctor_name: str, appointment_id: int, appointment_date: str,
                                  appointment_time: str, amount: float) -> None:
    subject = f'HealthHub appointment confirmed — #{appointment_id}'
    body = (f"Hello {patient_name},\n\nYour HealthHub appointment is confirmed.\n"
            f"Doctor: {doctor_name}\nDate: {appointment_date}\nTime: {appointment_time}\n"
            f"Consultation fee: ₹{amount:.2f}\nReference: #{appointment_id}\n\n"
            "Please arrive on time. For changes, use your HealthHub account and review the cancellation policy.\n\nHealthHub")
    send_email(patient_email, subject, body)
    if doctor_email:
        send_email(doctor_email, f'New HealthHub appointment — #{appointment_id}',
                   f"Hello Dr. {doctor_name},\n\nA new appointment has been booked.\n"
                   f"Date: {appointment_date}\nTime: {appointment_time}\nReference: #{appointment_id}\n\nHealthHub")
