-- =====================================================================
-- HEALTHHUB DATABASE SCHEMA
-- Healthcare & Wellness Web Application
-- Persistent MySQL 8.0+ Database Definition
-- =====================================================================

CREATE DATABASE IF NOT EXISTS healthhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE healthhub;

-- ---------------------------------------------------------------------
-- 1. USERS TABLE
-- Core credentials, roles, and account statuses
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(191) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('patient', 'doctor', 'admin') NOT NULL DEFAULT 'patient',
    status ENUM('active', 'inactive', 'suspended') NOT NULL DEFAULT 'active',
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verification_token_hash CHAR(64) NULL,
    email_verification_expires DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_role (role),
    INDEX idx_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 2. PATIENTS TABLE
-- Patient profile fields
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    phone VARCHAR(20) NULL,
    gender ENUM('male', 'female', 'other', 'prefer_not_to_say') DEFAULT 'prefer_not_to_say',
    date_of_birth DATE NULL,
    blood_group VARCHAR(10) NULL,
    emergency_contact VARCHAR(20) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_patients_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 3. DOCTORS TABLE
-- Medical specialization, credentials, consultation fee (INR), location
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doctors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    specialization VARCHAR(100) NOT NULL,
    qualification VARCHAR(150) NOT NULL,
    experience_years INT NOT NULL DEFAULT 0,
    consultation_fee DECIMAL(10,2) NOT NULL DEFAULT 500.00,
    clinic_address VARCHAR(255) NULL,
    city VARCHAR(100) NOT NULL,
    bio TEXT NULL,
    profile_image VARCHAR(255) NULL,
    verification_status ENUM('pending', 'verified', 'rejected') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_doctors_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_doctor_verification (verification_status),
    INDEX idx_doctor_specialization (specialization),
    INDEX idx_doctor_city (city)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 4. DOCTOR CERTIFICATES TABLE
-- Secure private certificate tracking with admin audit metadata
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doctor_certificates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id INT NOT NULL,
    certificate_type VARCHAR(100) NOT NULL DEFAULT 'Medical Registration / Degree Certificate',
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    file_size INT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    status ENUM('pending', 'verified', 'rejected') NOT NULL DEFAULT 'pending',
    reviewed_by INT NULL,
    review_date DATETIME NULL,
    rejection_reason TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_certificates_doctor FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    CONSTRAINT fk_certificates_admin FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_cert_doctor (doctor_id),
    INDEX idx_cert_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 5. DOCTOR AVAILABILITY TABLE
-- Weekly recurring schedule and consultation slot definitions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doctor_availability (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id INT NOT NULL,
    day_of_week ENUM('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday') NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_duration_minutes INT NOT NULL DEFAULT 30,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_availability_doctor FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    INDEX idx_avail_doc_day (doctor_id, day_of_week, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 6. APPOINTMENTS TABLE
-- Bookings with strict concurrency protection against double-booking
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    status ENUM('pending', 'confirmed', 'cancelled', 'completed', 'rejected') NOT NULL DEFAULT 'pending',
    reason VARCHAR(255) NULL,
    notes TEXT NULL,
    -- Generated virtual key: ensures no two active bookings for the same doctor/date/time
    active_booking_key VARCHAR(100) GENERATED ALWAYS AS (
        IF(status IN ('pending', 'confirmed'), CONCAT(doctor_id, '_', appointment_date, '_', appointment_time), NULL)
    ) VIRTUAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_appointments_patient FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    CONSTRAINT fk_appointments_doctor FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    UNIQUE KEY uq_active_slot (active_booking_key),
    INDEX idx_appt_patient (patient_id),
    INDEX idx_appt_doctor (doctor_id),
    INDEX idx_appt_date (appointment_date, appointment_time),
    INDEX idx_appt_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 7. PAYMENT RECORDS
-- Simulated checkout records; these do not represent real money movement.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL,
    patient_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    provider ENUM('simulated') NOT NULL DEFAULT 'simulated',
    transaction_reference VARCHAR(80) NOT NULL UNIQUE,
    status ENUM('pending', 'succeeded', 'failed', 'cancelled', 'refunded') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at DATETIME NULL,
    CONSTRAINT fk_payments_appointment FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
    CONSTRAINT fk_payments_patient FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_payments_patient (patient_id),
    INDEX idx_payments_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 8. FEEDBACK TABLE
-- Verified patient reviews and ratings (1 to 5 stars)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(191) NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    message TEXT NOT NULL,
    status ENUM('published', 'hidden') NOT NULL DEFAULT 'published',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_feedback_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 9. CONTACT MESSAGES TABLE
-- Inquiries from the contact page with admin response tracking
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contact_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(191) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    status ENUM('unread', 'read', 'responded', 'archived') NOT NULL DEFAULT 'unread',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_contact_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 9. SYMPTOMS & HEALTH GUIDANCE TABLE
-- Educational, non-diagnostic symptom guides with safety warnings
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS symptoms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    self_care_guidance TEXT NOT NULL,
    warning_signs TEXT NOT NULL,
    disclaimer TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_symptoms_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 10. HOME REMEDIES TABLE
-- Natural wellness tips, preparation, precautions & contraindications
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS home_remedies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    preparation TEXT NOT NULL,
    safety_notes TEXT NOT NULL,
    contraindications TEXT NULL,
    publication_status ENUM('published', 'draft') DEFAULT 'published',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_remedies_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 12. YOGA POSES TABLE
-- Verified yoga practices, benefits, precautions & editable video URLs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS yoga_poses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    category VARCHAR(100) NOT NULL,
    difficulty ENUM('Beginner', 'Intermediate', 'Advanced') NOT NULL DEFAULT 'Beginner',
    description TEXT NOT NULL,
    benefits TEXT NOT NULL,
    safety_notes TEXT NOT NULL,
    steps TEXT NOT NULL,
    image_url VARCHAR(255) NOT NULL,
    video_url VARCHAR(255) NOT NULL,
    display_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_yoga_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 12. VITAMINS & MINERALS TABLE
-- Educational nutritional facts, food sources & deficiency indicators
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vitamins_minerals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    nutrient_type ENUM('Vitamin', 'Mineral', 'Electrolyte') NOT NULL,
    function_description TEXT NOT NULL,
    food_sources TEXT NOT NULL,
    deficiency_symptoms TEXT NOT NULL,
    safe_guidance TEXT NOT NULL,
    safety_disclaimer TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_nutrient_type (nutrient_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 13. ARTICLES TABLE
-- Educational health, preventive care, and wellness articles
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    slug VARCHAR(200) NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    content MEDIUMTEXT NOT NULL,
    category VARCHAR(100) NOT NULL,
    author_name VARCHAR(100) NOT NULL,
    read_time VARCHAR(50) DEFAULT '5 min read',
    publication_status ENUM('published', 'draft') DEFAULT 'published',
    published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_articles_status (publication_status),
    INDEX idx_articles_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 14. FAQS TABLE
-- Frequently asked questions covering registration, appointments, privacy
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS faqs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    display_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_faqs_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 15. AUDIT LOGS TABLE
-- Traceability for sensitive administrative actions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id INT NULL,
    details TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_admin FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
