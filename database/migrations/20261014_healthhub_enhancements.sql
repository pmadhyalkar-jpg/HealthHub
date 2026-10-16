-- Run once against an existing HealthHub database. Back up the database first.
USE healthhub;
ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN email_verification_token_hash CHAR(64) NULL;
ALTER TABLE users ADD COLUMN email_verification_expires DATETIME NULL;
ALTER TABLE yoga_poses ADD COLUMN steps TEXT NULL;
UPDATE yoga_poses SET steps='Follow the posture gently, breathe naturally, and stop if uncomfortable.' WHERE steps IS NULL;
ALTER TABLE yoga_poses MODIFY COLUMN steps TEXT NOT NULL;
CREATE TABLE IF NOT EXISTS payments (
 id INT AUTO_INCREMENT PRIMARY KEY, appointment_id INT NOT NULL, patient_id INT NOT NULL,
 amount DECIMAL(10,2) NOT NULL, currency CHAR(3) NOT NULL DEFAULT 'INR',
 provider ENUM('simulated') NOT NULL DEFAULT 'simulated', transaction_reference VARCHAR(80) NOT NULL UNIQUE,
 status ENUM('pending','succeeded','failed','cancelled','refunded') NOT NULL DEFAULT 'pending',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, processed_at DATETIME NULL,
 CONSTRAINT fk_payments_appointment FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
 CONSTRAINT fk_payments_patient FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
 INDEX idx_payments_patient (patient_id), INDEX idx_payments_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
