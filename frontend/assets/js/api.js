/**
 * HealthHub Common Client API & UI Framework
 * Handles Fetch requests, CSRF injection, Auth session state, Navbar and Footer rendering.
 */

const HealthHub = {
  csrfToken: null,

  async getCsrfToken() {
    if (this.csrfToken) return this.csrfToken;
    try {
      const res = await fetch('/api/csrf-token');
      if (res.ok) {
        const data = await res.json();
        this.csrfToken = data.csrf_token;
        return this.csrfToken;
      }
    } catch (e) {
      console.warn('Could not fetch CSRF token:', e);
    }
    return '';
  },

  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('/') ? endpoint : `/api/${endpoint}`;
    const headers = options.headers || {};

    if (!options.isFormData && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes((options.method || 'GET').toUpperCase())) {
      const token = await this.getCsrfToken();
      if (token) {
        headers['X-CSRFToken'] = token;
      }
    }

    const config = {
      ...options,
      headers
    };

    try {
      const response = await fetch(url, config);
      const isJson = (response.headers.get('content-type') || '').includes('application/json');
      const data = isJson ? await response.json() : await response.text();

      if (!response.ok) {
        const errorMsg = (data && data.error) ? data.error : (typeof data === 'string' ? data : 'Request failed');
        const err = new Error(errorMsg);
        err.status = response.status;
        err.data = data;
        throw err;
      }

      return data;
    } catch (err) {
      console.error(`API Error on ${url}:`, err);
      throw err;
    }
  },

  // Auth Helpers
  async getCurrentUser() {
    try {
      const data = await this.request('/api/auth/me');
      return data.user || null;
    } catch (e) {
      return null;
    }
  },

  async logout() {
    try {
      await this.request('/api/auth/logout', { method: 'POST' });
    } catch (e) {
      console.warn('Logout request error:', e);
    } finally {
      window.location.href = 'login.html';
    }
  },

  getUrlParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
  },

  // UI Helpers
  renderDisclaimerBanner(targetId = 'disclaimer-banner-placeholder') {
    const el = document.getElementById(targetId);
    if (!el) return;
    el.innerHTML = `
      <div class="disclaimer-banner">
        <i class="fas fa-info-circle"></i>
        <span>HealthHub offers general wellness information and appointment tools. It does not replace professional medical advice. In an emergency, call 112 or contact your local emergency service.</span>
      </div>
    `;
  },

  async renderNavbar(activePage = '') {
    const navPlaceholder = document.getElementById('navbar-placeholder');
    if (!navPlaceholder) return;

    let user = null;
    try {
      user = await this.getCurrentUser();
    } catch (e) {
      user = null;
    }

    let authLinks = '';
    if (user) {
      let dashUrl = 'patient-dashboard.html';
      let roleLabel = 'Patient';
      if (user.role === 'doctor') {
        dashUrl = 'doctor-dashboard.html';
        roleLabel = 'Doctor';
      } else if (user.role === 'admin') {
        dashUrl = 'admin-dashboard.html';
        roleLabel = 'Admin';
      }

      authLinks = `
        <a href="${dashUrl}" class="user-menu-pill">
          <i class="fas fa-user-circle"></i>
          <span>${user.name.split(' ')[0]} (${roleLabel})</span>
        </a>
        <button onclick="HealthHub.logout()" class="btn btn-outline btn-sm" title="Log Out">
          <i class="fas fa-sign-out-alt"></i> Logout
        </button>
      `;
    } else {
      authLinks = `
        <a href="login.html" class="btn btn-outline btn-sm">Log In</a>
        <a href="register.html" class="btn btn-primary btn-sm">Sign Up</a>
      `;
    }

    navPlaceholder.innerHTML = `
      <nav class="navbar">
        <div class="container nav-container">
          <a href="index.html" class="brand-logo">
            <i class="fas fa-heartbeat"></i>
            <span>HealthHub</span>
            
          </a>

          <button class="nav-toggle-btn" id="nav-toggle-btn" aria-label="Toggle navigation">
            <i class="fas fa-bars"></i>
          </button>

          <ul class="nav-links" id="nav-links">
            <li><a href="index.html" class="nav-link ${activePage === 'home' ? 'active' : ''}">Home</a></li>
            <li><a href="doctors.html" class="nav-link ${activePage === 'doctors' ? 'active' : ''}">Find Doctors</a></li>
            <li><a href="appointments.html" class="nav-link ${activePage === 'appointments' ? 'active' : ''}">Appointments</a></li>
            <li><a href="symptoms.html" class="nav-link ${activePage === 'symptoms' ? 'active' : ''}">Symptoms</a></li>
            <li><a href="homeremedies.html" class="nav-link ${activePage === 'homeremedies' ? 'active' : ''}">Home Remedies</a></li>
            <li><a href="yoga.html" class="nav-link ${activePage === 'yoga' ? 'active' : ''}">Yoga</a></li>
            <li><a href="vitamins.html" class="nav-link ${activePage === 'vitamins' ? 'active' : ''}">Vitamins</a></li>
            <li><a href="articles.html" class="nav-link ${activePage === 'articles' ? 'active' : ''}">Articles</a></li>
          </ul>

          <div class="nav-actions">
            ${authLinks}
          </div>
        </div>
      </nav>
    `;

    const toggleBtn = document.getElementById('nav-toggle-btn');
    const navLinks = document.getElementById('nav-links');
    if (toggleBtn && navLinks) {
      toggleBtn.addEventListener('click', () => {
        navLinks.classList.toggle('show');
      });
    }
  },

  renderFooter(targetId = 'footer-placeholder') {
    const el = document.getElementById(targetId);
    if (!el) return;
    el.innerHTML = `
      <footer class="footer">
        <div class="container">
          <div class="footer-disclaimer-box">
            <i class="fas fa-shield-alt"></i>
            <strong>Important Medical Disclaimer:</strong> HealthHub provides general wellness information and appointment-management tools. It does not provide a diagnosis or replace professional medical advice, clinical assessment, or prescriptions. For emergencies, call 112 or contact your local emergency service.
          </div>

          <div class="footer-grid">
            <div class="footer-col">
              <div class="brand-logo" style="margin-bottom: 0.75rem;">
                <i class="fas fa-heartbeat"></i>
                <span>HealthHub</span>
              </div>
              <p style="color: var(--text-secondary); font-size: 0.9rem;">
                Bridging healthcare information, verified doctor availability, and holistic wellness guidance for modern life.
              </p>
            </div>

            <div class="footer-col">
              <h4>Quick Links</h4>
              <ul class="footer-links">
                <li><a href="index.html">Home</a></li>
                <li><a href="doctors.html">Find Doctors</a></li>
                <li><a href="appointments.html">Book Appointments</a></li>
                <li><a href="about.html">About the Project</a></li>
              </ul>
            </div>

            <div class="footer-col">
              <h4>Wellness Care</h4>
              <ul class="footer-links">
                <li><a href="symptoms.html">Symptom Guidance</a></li>
                <li><a href="homeremedies.html">Home Remedies</a></li>
                <li><a href="yoga.html">Yoga & Meditation</a></li>
                <li><a href="vitamins.html">Vitamins & Minerals</a></li>
              </ul>
            </div>

            <div class="footer-col">
              <h4>Support & Trust</h4>
              <ul class="footer-links">
                <li><a href="faq.html">Frequently Asked Questions</a></li>
                <li><a href="help.html">Help & Guidance</a></li>
                <li><a href="contact.html">Contact Us</a></li>
                <li><a href="feedback.html">Share Feedback</a></li>
              </ul>
            </div>
          </div>

          <div class="footer-bottom">
            <div>&copy; 2026 HealthHub. All Rights Reserved.</div>
            <div>Built with Flask, MySQL, HTML5, CSS3 & Vanilla JavaScript</div>
          </div>
        </div>
      </footer>
    `;
  },

  renderAlert(type, message, containerId = 'alert-container') {
    const el = document.getElementById(containerId);
    if (!el) return;
    const icons = {
      success: 'fa-check-circle',
      danger: 'fa-exclamation-circle',
      warning: 'fa-exclamation-triangle',
      info: 'fa-info-circle'
    };
    el.innerHTML = `
      <div class="alert alert-${type}">
        <i class="fas ${icons[type] || 'fa-info-circle'}"></i>
        <div>${message}</div>
      </div>
    `;
  },

  clearAlert(containerId = 'alert-container') {
    const el = document.getElementById(containerId);
    if (el) el.innerHTML = '';
  }
};
