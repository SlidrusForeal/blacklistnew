// static/js/filter-list.js

(() => {
  'use strict';

  // Constants
  const DEBOUNCE_DELAY = 150;
  const OBSERVER_OPTIONS = {
    root: null,
    rootMargin: '50px 0px',
    threshold: 0.1
  };

  // Utility functions
  const debounce = (fn, delay) => {
    let timeoutId;
    return (...args) => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fn.apply(this, args), delay);
    };
  };

  // Image loading with IntersectionObserver
  const setupImageLoading = () => {
    const images = document.querySelectorAll('img[data-src]');
    if (!images.length) return;

    const loadImage = (img) => {
      const src = img.dataset.src;
      if (!src) return;

      // Create a new image to preload
      const preloader = new Image();
      
      preloader.onload = () => {
        img.src = src;
        img.classList.remove('skeleton');
        img.classList.add('loaded');
        img.removeAttribute('data-src');
      };

      preloader.onerror = () => {
        img.classList.remove('skeleton');
        img.classList.add('error');
        console.error(`Failed to load image: ${src}`);
      };

      preloader.src = src;
    };

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          loadImage(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, OBSERVER_OPTIONS);

    images.forEach(img => {
      img.classList.add('skeleton');
      observer.observe(img);
    });
  };

  // Enhanced list filtering
  const setupListFiltering = () => {
    const searchInput = document.getElementById('search-input');
    if (!searchInput) return;

    const list = document.getElementById('blacklist');
    if (!list) return;

    const listItems = Array.from(list.getElementsByTagName('li'));
    if (!listItems.length) return;

    // Create index for faster searching
    const searchIndex = listItems.map(li => ({
      element: li,
      text: li.textContent.toLowerCase(),
      // Add more searchable fields if needed
      name: li.querySelector('.name')?.textContent.toLowerCase() || '',
      reason: li.querySelector('.reason')?.textContent.toLowerCase() || '',
      date: li.querySelector('.date')?.textContent.toLowerCase() || ''
    }));

    // Add status display
    const statusDiv = document.createElement('div');
    statusDiv.className = 'search-status';
    statusDiv.style.cssText = `
      margin: 10px 0;
      font-size: 0.9rem;
      color: var(--text-muted);
    `;
    searchInput.parentNode.insertBefore(statusDiv, list);

    // Setup highlight function
    const highlight = (text, term) => {
      if (!term) return text;
      const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
      return text.replace(regex, '<mark>$1</mark>');
    };

    // Filtering function
    const filterList = debounce((value) => {
      const term = value.toLowerCase().trim();
      let visibleCount = 0;

      // Clear highlights
      list.querySelectorAll('mark').forEach(mark => {
        const parent = mark.parentNode;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
      });

      if (!term) {
        // Show all items if no search term
        searchIndex.forEach(({ element }) => {
          element.style.display = '';
          element.classList.remove('filtered');
        });
        statusDiv.textContent = `Showing all ${listItems.length} items`;
        return;
      }

      // Filter and highlight
      searchIndex.forEach(({ element, text, name, reason, date }) => {
        const matches = 
          text.includes(term) || 
          name.includes(term) || 
          reason.includes(term) || 
          date.includes(term);

        if (matches) {
          element.style.display = '';
          element.classList.remove('filtered');
          visibleCount++;

          // Highlight matches
          element.querySelectorAll('.name, .reason, .date').forEach(el => {
            el.innerHTML = highlight(el.textContent, term);
          });
        } else {
          element.style.display = 'none';
          element.classList.add('filtered');
        }
      });

      // Update status
      statusDiv.textContent = visibleCount === 0 
        ? 'No matches found' 
        : `Showing ${visibleCount} of ${listItems.length} items`;
    }, DEBOUNCE_DELAY);

    // Setup event listeners
    searchInput.addEventListener('input', (e) => filterList(e.target.value));
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        searchInput.value = '';
        filterList('');
        searchInput.blur();
      }
    });

    // Add clear button
    const clearButton = document.createElement('button');
    clearButton.type = 'button';
    clearButton.className = 'search-clear';
    clearButton.setAttribute('aria-label', 'Clear search');
    clearButton.innerHTML = '×';
    clearButton.style.cssText = `
      position: absolute;
      right: 10px;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 1.2rem;
      cursor: pointer;
      padding: 0 5px;
      display: none;
    `;

    const searchWrapper = document.createElement('div');
    searchWrapper.style.position = 'relative';
    searchInput.parentNode.insertBefore(searchWrapper, searchInput);
    searchWrapper.appendChild(searchInput);
    searchWrapper.appendChild(clearButton);

    // Show/hide clear button
    searchInput.addEventListener('input', () => {
      clearButton.style.display = searchInput.value ? 'block' : 'none';
    });

    clearButton.addEventListener('click', () => {
      searchInput.value = '';
      filterList('');
      searchInput.focus();
      clearButton.style.display = 'none';
    });

    // Initial status
    statusDiv.textContent = `Showing all ${listItems.length} items`;
  };

  // Initialize when DOM is ready
  const init = () => {
    setupImageLoading();
    setupListFiltering();
  };

  // Run on initial load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-run on dynamic content changes
  if ('MutationObserver' in window) {
    new MutationObserver(debounce((mutations) => {
      for (const mutation of mutations) {
        if (mutation.addedNodes.length) {
          init();
          break;
        }
      }
    }, 100)).observe(document.body, { 
      childList: true, 
      subtree: true 
    });
  }
})();
