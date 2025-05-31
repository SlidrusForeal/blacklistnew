// Lazy loading for images
document.addEventListener('DOMContentLoaded', function() {
  const lazyImages = document.querySelectorAll('img[loading="lazy"]');
  lazyImages.forEach(img => {
    img.classList.add('lazy-image');
    img.addEventListener('load', () => img.classList.add('loaded'));
  });
});

// Toast notification function
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.getElementById('toastContainer').appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

// Form validation
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', function(e) {
    if (!this.checkValidity()) {
      e.preventDefault();
      Array.from(this.elements).forEach(input => {
        if (!input.validity.valid) {
          const errorDiv = document.createElement('div');
          errorDiv.className = 'error-message';
          errorDiv.textContent = input.validationMessage;
          input.parentNode.appendChild(errorDiv);
        }
      });
    }
  });
}); 