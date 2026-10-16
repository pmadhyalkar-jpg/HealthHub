# HealthHub — Healthcare & Wellness Web Application

HealthHub is a Flask + MySQL web application with patient and doctor accounts, credential review, appointment scheduling, email verification, wellness information, and a simulated checkout flow.

> **Important:** Checkout is intentionally simulated. It does not collect or transfer real money and does not connect to UPI, cards, banks, or a payment gateway. Doctor directory listings are only as trustworthy as the records and verification performed by the site administrator. Health information is educational and does not replace medical advice.

## Requirements

- Python 3.10+
- MySQL 8.0+
- A modern browser
- SMTP credentials if you want email verification and appointment emails delivered to real inboxes

## Setup on Windows / PowerShell

1. Extract the ZIP to a folder such as `D:\HealthHub`.
2. Open PowerShell in the extracted `New_MINI_Project` folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r backend\requirements.txt
   ```

4. Create the database schema in MySQL Workbench. Open and run `database/schema.sql`. This creates the `healthhub` database and tables.
5. Run `database/seed_wellness_content.sql` once to add yoga poses and symptom guidance. It does not create login accounts or fake doctors/patients.
6. Copy the environment example:

   ```powershell
   Copy-Item backend\.env.example backend\.env
   ```

   Edit `backend\.env` and set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`. Change `SECRET_KEY` to a long random value.
7. For email delivery, configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM`. For Gmail, use an App Password, not your normal account password. Set `PUBLIC_BASE_URL` to the base URL where HealthHub is served.
8. Start HealthHub from the project root:

   ```powershell
   python -m backend.app
   ```

9. Open `http://127.0.0.1:5000` in your browser.
10. Register a patient or doctor with an email address you control. Verify the email from the received message, then sign in. Doctor profiles remain hidden from patients until an administrator reviews the uploaded credentials and verifies the profile.

### Local email verification without SMTP

If SMTP is not configured, the account is still created but no email is delivered. For local development only, the verification URL is written to the Flask terminal output. Open that URL in the same local app to verify the account. Configure SMTP for realistic email delivery.

### Create the first administrator

Run this from the project root, using an email address you control and a strong password:

```powershell
python scripts\create_admin.py --name "HealthHub Administrator" --email "your-real-email@example.com" --password "choose-a-strong-password"
```

The administrator account is marked as email-verified because it is explicitly provisioned by this command. Never use a shared/default password.

## Existing database upgrade

If you already created the earlier HealthHub schema, back up your database first, then run `database/migrations/20261014_healthhub_enhancements.sql` once in MySQL Workbench. The migration adds email verification fields, yoga steps, and the simulated payments table. Then run `database/seed_wellness_content.sql` once if you need wellness content. Do not run the migration more than once because the `ALTER TABLE` statements are intended for a pre-enhancement schema.

## Main features

- Email ownership verification before login; hashed passwords and expiring one-time verification tokens.
- Public doctor search and profile endpoints return only active, verified doctors.
- Searchable doctor directory and symptom guides.
- Yoga pose illustrations, step-by-step instructions, safety notes, and YouTube tutorial searches.
- Appointment availability based on doctor schedules, with database uniqueness protection against overlapping active slots.
- Checkout with **Simulate Successful Payment**, **Simulate Failed Payment**, and **Cancel Checkout**. Test transactions are persisted in MySQL.
- Successful simulated payment confirms the appointment and triggers a patient confirmation email; a doctor notification is attempted if configured.
- Unpaid checkout reservations are released after 15 minutes when availability is queried.
- Responsive shared navigation, footer, and medical disclaimer.

## Testing

From the project root after installing requirements:

```powershell
python -m compileall backend scripts
python -m pytest -q
```

The included integrity tests check core project safeguards and required assets. Full end-to-end testing of authentication, booking, payment-state transitions, and email delivery requires a running MySQL server, the configured schema, and SMTP settings.

## Before any real-world launch

This ZIP is a development project, not a production-certified medical service. Before using it with real patients, perform a professional security review, privacy and legal review, deployment over HTTPS, backup and monitoring setup, robust rate limiting, audit and retention policies, and operational verification of doctor credentials. The simulated checkout must be replaced with an approved payment provider and its server-side payment verification before collecting money.
