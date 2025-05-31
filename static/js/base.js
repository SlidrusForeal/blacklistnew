// Base functionality for the site
(() => {
  'use strict';

  // Constants
  const TOAST_DURATION = 5000;
  const TOAST_TYPES = {
    info: 'var(--primary-color)',
    success: '#4caf50',
    warning: '#ff9800',
    error: '#f44336'
  };

  // Utility functions
  const debounce = (fn, delay) => {
    let timeoutId;
    return (...args) => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fn.apply(this, args), delay);
    };
  };

  // Lazy loading for images with IntersectionObserver
  const setupLazyLoading = () => {
    if ('IntersectionObserver' in window) {
      const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            if (img.dataset.src) {
              img.src = img.dataset.src;
              img.removeAttribute('data-src');
            }
            img.classList.add('loaded');
            observer.unobserve(img);
          }
        });
      }, {
        rootMargin: '50px 0px',
        threshold: 0.01
      });

      document.querySelectorAll('img[loading="lazy"]').forEach(img => {
        img.classList.add('lazy-image');
        if (img.complete) {
          img.classList.add('loaded');
        } else {
          imageObserver.observe(img);
        }
      });
    }
  };

  // Enhanced toast notification system
  const createToastContainer = () => {
    const container = document.getElementById('toastContainer') || document.createElement('div');
    if (!container.id) {
      container.id = 'toastContainer';
      container.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000;
        display: flex;
        flex-direction: column;
        gap: 10px;
      `;
      document.body.appendChild(container);
    }
    return container;
  };

  window.showToast = (message, type = 'info', duration = TOAST_DURATION) => {
    const container = createToastContainer();
    const toast = document.createElement('div');
    
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
      padding: 12px 24px;
      background: ${TOAST_TYPES[type]};
      color: white;
      border-radius: 4px;
      box-shadow: 0 2px 5px rgba(0,0,0,0.2);
      margin: 0;
      opacity: 0;
      transform: translateX(100%);
      transition: all 0.3s ease;
      cursor: pointer;
    `;
    
    toast.innerHTML = `
      <div style="display: flex; align-items: center; gap: 8px;">
        <span>${message}</span>
        <button aria-label="Close" style="background: none; border: none; color: white; cursor: pointer; padding: 0 4px;">×</button>
      </div>
    `;

    container.appendChild(toast);
    
    // Force reflow
    toast.offsetHeight;
    
    // Animate in
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(0)';

    // Setup close handlers
    const close = () => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      setTimeout(() => toast.remove(), 300);
    };

    toast.querySelector('button').addEventListener('click', close);
    toast.addEventListener('click', close);

    if (duration > 0) {
      setTimeout(close, duration);
    }
  };

  // Enhanced form validation
  const setupFormValidation = () => {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
      // Remove existing validation to prevent duplicates
      form.noValidate = true;
      
      // Setup validation styles
      const style = document.createElement('style');
      style.textContent = `
        .error-message {
          color: #f44336;
          font-size: 0.875rem;
          margin-top: 4px;
          display: none;
        }
        .form-field.error input,
        .form-field.error select,
        .form-field.error textarea {
          border-color: #f44336;
        }
        .form-field.error .error-message {
          display: block;
        }
      `;
      document.head.appendChild(style);

      // Handle form submission
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Clear previous errors
        form.querySelectorAll('.error-message').forEach(msg => msg.remove());
        form.querySelectorAll('.form-field').forEach(field => field.classList.remove('error'));

        // Validate all fields
        let isValid = true;
        const formData = new FormData(form);
        const errors = new Map();

        for (const [name, value] of formData.entries()) {
          const field = form.querySelector(`[name="${name}"]`);
          const fieldContainer = field.closest('.form-field') || field.parentNode;
          
          if (!field.checkValidity()) {
            isValid = false;
            errors.set(name, field.validationMessage);
            fieldContainer.classList.add('error');
          }
          
          // Custom validation
          if (field.dataset.validate) {
            try {
              const validateFn = new Function('value', field.dataset.validate);
              const customValid = validateFn(value);
              if (customValid !== true) {
                isValid = false;
                errors.set(name, customValid || 'Invalid value');
                fieldContainer.classList.add('error');
              }
            } catch (err) {
              console.error('Custom validation error:', err);
            }
          }
        }

        // Show errors if any
        if (!isValid) {
          errors.forEach((message, name) => {
            const field = form.querySelector(`[name="${name}"]`);
            const fieldContainer = field.closest('.form-field') || field.parentNode;
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = message;
            fieldContainer.appendChild(errorDiv);
          });
          
          // Scroll to first error
          const firstError = form.querySelector('.error-message');
          if (firstError) {
            firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
          
          return;
        }

        // If valid, proceed with form submission
        try {
          const submitButton = form.querySelector('[type="submit"]');
          if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner"></span> Sending...';
          }

          // Get CSRF token from meta tag
          const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

          // Add CSRF token to form data if not present
          if (!formData.has('csrf_token')) {
            formData.append('csrf_token', csrfToken);
          }

          const response = await fetch(form.action, {
            method: form.method || 'POST',
            body: formData,
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              'X-CSRF-Token': csrfToken
            },
            credentials: 'same-origin'
          });

          if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

          const data = await response.json();
          
          if (data.redirect) {
            window.location.href = data.redirect;
          } else if (data.message) {
            // Show success message
            const messageContainer = document.querySelector('.message-container') || createMessageContainer();
            const messageDiv = document.createElement('div');
            messageDiv.className = 'success-message';
            messageDiv.textContent = data.message;
            messageContainer.appendChild(messageDiv);
            
            // Clear form if it's not a search form
            if (!form.classList.contains('search-form')) {
              form.reset();
            }
          }
        } catch (error) {
          console.error('Form submission error:', error);
          const messageContainer = document.querySelector('.message-container') || createMessageContainer();
          const messageDiv = document.createElement('div');
          messageDiv.className = 'error-message';
          messageDiv.textContent = 'Произошла ошибка. Пожалуйста, попробуйте снова.';
          messageContainer.appendChild(messageDiv);
        } finally {
          const submitButton = form.querySelector('[type="submit"]');
          if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = submitButton.dataset.originalText || 'Submit';
          }
        }
      });

      // Real-time validation
      form.querySelectorAll('input, select, textarea').forEach(field => {
        const validate = debounce(() => {
          const fieldContainer = field.closest('.form-field') || field.parentNode;
          const errorDiv = fieldContainer.querySelector('.error-message');
          
          if (errorDiv) errorDiv.remove();
          fieldContainer.classList.remove('error');

          if (!field.checkValidity()) {
            fieldContainer.classList.add('error');
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = field.validationMessage;
            fieldContainer.appendChild(errorDiv);
          }
        }, 300);

        field.addEventListener('input', validate);
        field.addEventListener('blur', validate);
      });
    });
  };

  // Initialize when DOM is ready
  document.addEventListener('DOMContentLoaded', () => {
    setupLazyLoading();
    setupFormValidation();
  });

  // Re-run setup on dynamic content changes
  if ('MutationObserver' in window) {
    new MutationObserver(debounce((mutations) => {
      for (const mutation of mutations) {
        if (mutation.addedNodes.length) {
          setupLazyLoading();
          setupFormValidation();
          break;
        }
      }
    }, 100)).observe(document.body, { 
      childList: true, 
      subtree: true 
    });
  }

  // Helper function to create message container
  function createMessageContainer() {
    const container = document.createElement('div');
    container.className = 'message-container';
    const mainContent = document.querySelector('.main-content');
    mainContent.insertBefore(container, mainContent.firstChild);
    return container;
  }

  // Handle search input
  const searchInput = document.querySelector('.search-input');
  if (searchInput) {
    let searchTimeout;
    searchInput.addEventListener('input', function() {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        const searchForm = this.closest('form');
        if (searchForm) {
          searchForm.dispatchEvent(new Event('submit'));
        }
      }, 300);
    });
  }
})(); 