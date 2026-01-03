/* Main JavaScript */

const API_BASE_URL = '/api';
const TOKEN = localStorage.getItem('token');

// Fetch wrapper
async function fetchAPI(endpoint, options = {}) {
    // When sending FormData, do not set Content-Type header
    const isFormData = options.body instanceof FormData;
    const headers = {
        'X-CSRFToken': getCookie('csrftoken'),
        ...options.headers,
    };
    if (!isFormData) headers['Content-Type'] = 'application/json';

    if (TOKEN) {
        headers['Authorization'] = `Token ${TOKEN}`;
    }

    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers,
            credentials: 'same-origin',
        });

        if (!response.ok) {
            if (response.status === 401) {
                window.location.href = '/login/';
            }
            const errorText = await response.text();
            console.error('API Error Response:', errorText);
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        showAlert('An error occurred. Please try again.', 'danger');
        throw error;
    }
}

// Logout handler - update nav link if present
document.addEventListener('DOMContentLoaded', function(){
    const logoutLink = document.getElementById('logout-link');
    if (logoutLink) {
        logoutLink.addEventListener('click', function(e){
            e.preventDefault();
            // Clear any leftover token used by API clients
            try { localStorage.removeItem('token'); } catch (_) {}
            // Use server-side session logout to avoid session mix-ups
            window.location.href = '/logout/';
        });
    }
});

// CSRF Token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + '=') {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Show Alert
function showAlert(message, type = 'info') {
    const alertsContainer = document.querySelector('.alerts-container') || createAlertsContainer();
    const alertId = `alert-${Date.now()}`;
    
    const alertHTML = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert" id="${alertId}">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    alertsContainer.insertAdjacentHTML('beforeend', alertHTML);
    
    setTimeout(() => {
        const alert = document.getElementById(alertId);
        if (alert) {
            alert.remove();
        }
    }, 5000);
}

function createAlertsContainer() {
    const container = document.createElement('div');
    container.className = 'alerts-container container mt-3';
    document.querySelector('main').insertAdjacentElement('afterbegin', container);
    return container;
}

// Format currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
    }).format(amount);
}

// Format date
function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

// Format datetime
function formatDateTime(dateString) {
    return new Date(dateString).toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

// Get status badge
function getStatusBadge(status) {
    const badges = {
        pending: '<span class="badge badge-pending">Pending</span>',
        approved: '<span class="badge badge-approved">Approved</span>',
        rejected: '<span class="badge badge-rejected">Rejected</span>',
        active: '<span class="badge badge-active">Active</span>',
        completed: '<span class="badge badge-completed">Completed</span>',
        processing: '<span class="badge bg-info">Processing</span>',
        closed: '<span class="badge bg-secondary">Closed</span>',
        in_progress: '<span class="badge bg-warning">In Progress</span>',
    };
    return badges[status] || `<span class="badge bg-secondary">${status}</span>`;
}
// Alert Modal System
function showAlertModal(message, type = 'info') {
    // Color scheme based on alert type
    const colors = {
        success: { bg: '#f0fdf4', border: '#86efac', text: '#166534', btn: '#16a34a' },
        error: { bg: '#fef2f2', border: '#fca5a5', text: '#7f1d1d', btn: '#dc2626' },
        warning: { bg: '#fefce8', border: '#fde047', text: '#713f12', btn: '#ca8a04' },
        info: { bg: '#eff6ff', border: '#93c5fd', text: '#1e3a8a', btn: '#2563eb' }
    };
    
    const c = colors[type] || colors.info;
    
    // Create wrapper container
    const container = document.createElement('div');
    container.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:10000';
    
    // Create modal box
    const box = document.createElement('div');
    box.style.cssText = `background:${c.bg};border:2px solid ${c.border};border-radius:12px;padding:32px;max-width:500px;width:90%;text-align:center;box-shadow:0 20px 25px rgba(0,0,0,0.1)`;
    
    // Create content
    box.innerHTML = `
        <h2 style="color:${c.text};font-size:24px;font-weight:bold;margin:0 0 16px 0;">Alert</h2>
        <p style="color:#374151;font-size:16px;margin:0 0 24px 0;line-height:1.5">${message}</p>
        <button id="alert-ok" style="background:${c.btn};color:white;border:none;padding:12px 32px;border-radius:8px;font-weight:bold;cursor:pointer;font-size:16px;width:100%;transition:all 0.2s">OK</button>
    `;
    
    container.appendChild(box);
    document.body.appendChild(container);
    
    // Close functionality
    const closeModal = function() {
        container.remove();
    };
    
    document.getElementById('alert-ok').addEventListener('click', closeModal);
    container.addEventListener('click', function(e) {
        if (e.target === container) closeModal();
    });
}

// Check for server-side alerts and display them on page load
document.addEventListener('DOMContentLoaded', function() {
    const successAlert = document.querySelector('[data-alert-success]');
    const errorAlert = document.querySelector('[data-alert-error]');
    
    if (successAlert) {
        const message = successAlert.getAttribute('data-alert-success');
        if (message && message.trim() !== '') {
            showAlertModal(message, 'success');
        }
        successAlert.remove();
    }
    
    if (errorAlert) {
        const message = errorAlert.getAttribute('data-alert-error');
        if (message && message.trim() !== '') {
            showAlertModal(message, 'error');
        }
        errorAlert.remove();
    }
    
    // Test alert on deposits page
    if (window.location.pathname === '/deposits/') {
        // Uncomment below to test modal on page load
        // showAlertModal('This is a test alert!', 'success');
    }
});