class InfiniteScroll {
  constructor(container, options = {}) {
    this.container = container;
    this.options = {
      perPage: options.perPage || 20,
      threshold: options.threshold || 100, // Pixels from bottom to trigger load
      loadingTemplate: options.loadingTemplate || '<div class="loading">Загрузка...</div>',
      searchQuery: options.searchQuery || '',
      noMoreResultsIndicator: options.noMoreResultsIndicator, // Element for "no more results"
      loadingIndicator: options.loadingIndicator, // Element for loading spinner
      initialPageContentElement: options.initialPageContentElement // Element to show "no results" on initial load
    };
    
    this.page = 1;
    this.loading = false;
    this.hasMore = true;
    
    this.init();
  }
  
  init() {
    // Use provided loading indicator or create one
    this.actualLoadingEl = this.options.loadingIndicator;
    if (!this.actualLoadingEl && this.container) { // Ensure container exists for appending
        const loadingElDiv = document.createElement('div');
        loadingElDiv.innerHTML = this.options.loadingTemplate;
        this.actualLoadingEl = loadingElDiv.firstChild;
        if (this.actualLoadingEl) this.container.appendChild(this.actualLoadingEl);
    }
    if (this.actualLoadingEl) this.actualLoadingEl.style.display = 'none';
    if (this.options.noMoreResultsIndicator) this.options.noMoreResultsIndicator.style.display = 'none';
    
    window.addEventListener('scroll', this.handleScroll.bind(this));
    this.loadMore(); // Initial load
  }
  
  handleScroll() {
    if (this.loading || !this.hasMore || !this.container) return;
    
    const scrollPos = window.innerHeight + window.scrollY;
    // Check if container is tall enough to scroll, or if body scroll is sufficient
    const containerBottom = this.container.offsetTop + this.container.offsetHeight;
    const triggerPoint = Math.max(document.documentElement.offsetHeight - this.options.threshold, containerBottom - this.options.threshold);

    if (scrollPos >= triggerPoint) {
      this.loadMore();
    }
  }
  
  async loadMore() {
    if (this.loading || !this.hasMore) return;

    this.loading = true;
    if (this.actualLoadingEl) this.actualLoadingEl.style.display = 'block';
    if (this.options.noMoreResultsIndicator) this.options.noMoreResultsIndicator.style.display = 'none';
    
    try {
      let apiUrl = `/api/fullist?page=${this.page}&per_page=${this.options.perPage}`;
      if (this.options.searchQuery) {
        apiUrl += `&q=${encodeURIComponent(this.options.searchQuery)}`;
      }
      
      const response = await fetch(apiUrl);
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      const data = await response.json();
      
      if (data.items && data.items.length > 0) {
        await this.renderItems(data.items);
        this.page++;
        this.hasMore = data.has_more;
        if (!this.hasMore && this.options.noMoreResultsIndicator) {
            this.options.noMoreResultsIndicator.style.display = 'block';
        }
      } else {
        this.hasMore = false;
        if (this.page === 1 && this.options.initialPageContentElement) { 
            this.options.initialPageContentElement.innerHTML = '<p class="text-center text-muted">Записи не найдены.</p>';
        }
        if (this.options.noMoreResultsIndicator) this.options.noMoreResultsIndicator.style.display = 'block';
      }
    } catch (error) {
      console.error('Failed to load more items:', error);
      if (this.options.initialPageContentElement) { 
          this.options.initialPageContentElement.innerHTML = '<p class="text-center text-danger">Не удалось загрузить список. Попробуйте позже.</p>';
      }
      // Optionally, display a toast or specific error message to the user here
      // showToast('Ошибка загрузки данных', 'error'); // If you have a showToast function
    } finally {
      this.loading = false;
      if (this.actualLoadingEl) this.actualLoadingEl.style.display = 'none';
    }
  }
  
  async renderItems(items) {
    if (!this.container) return;
    const fragment = document.createDocumentFragment();
    
    for (const item of items) {
      const element = document.createElement('div');
      element.className = 'blacklist-entry'; // This class should exist in your CSS
      
      let avatarSrc = 'https://minotar.net/helm/MHF_Steve/50.png'; // Default fallback avatar
      try {
        const avatarResponse = await fetch(`/api/avatar/${item.uuid}`);
        if (avatarResponse.ok) {
          const avatarData = await avatarResponse.json();
          if (avatarData.avatar_base64) {
            avatarSrc = avatarData.avatar_base64;
          }
        }
      } catch (e) {
        console.warn(`Failed to load avatar for ${item.nickname}:`, e);
      }
      
      // Structure based on the original, simple blacklist entry style
      element.innerHTML = `
        <div class="entry-header">
          <img src="${avatarSrc}" alt="${item.nickname}" class="avatar" loading="lazy" style="width:50px; height:50px; margin-right:10px; border-radius:5px;">
          <h3>${item.nickname}</h3>
        </div>
        <div class="entry-details">
          <p class="reason" style="margin: 5px 0;">Причина: ${item.reason || 'Не указана'}</p>
          <p class="uuid" style="font-size:0.8em; color: #ccc;">UUID: ${item.uuid}</p>
          <p class="date" style="font-size:0.8em; color: #ccc;">Добавлено: ${item.created_at ? new Date(item.created_at).toLocaleDateString('ru-RU') : 'N/A'}</p>
        </div>
      `;
      fragment.appendChild(element);
    }
    
    // Append before the loading element if it's a child of the container
    if (this.actualLoadingEl && this.actualLoadingEl.parentNode === this.container) {
        this.container.insertBefore(fragment, this.actualLoadingEl);
    } else {
        this.container.appendChild(fragment);
    }
  }
  
  reset() {
    this.page = 1;
    this.hasMore = true;
    this.loading = false; // Reset loading state
    if (this.container) this.container.innerHTML = ''; // Clear previous items
    // Re-add loading indicator if it was cleared
    if (this.actualLoadingEl && this.actualLoadingEl.parentNode !== this.container && this.container) {
        this.container.appendChild(this.actualLoadingEl);
    }
    if (this.options.noMoreResultsIndicator) this.options.noMoreResultsIndicator.style.display = 'none';

    this.loadMore(); // Fetch the first page with new (or reset) query
  }
}

// Initialize infinite scroll when the page loads
document.addEventListener('DOMContentLoaded', function () {
    const blacklistContainer = document.getElementById('blacklistContainer');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const noMoreResultsIndicator = document.getElementById('noMoreResultsIndicator');
    const searchInput = document.getElementById('searchInput');
    
    // New filter/sort controls
    const sortBySelect = document.getElementById('sortBy');
    const sortOrderSelect = document.getElementById('sortOrder');
    const dateFromInput = document.getElementById('dateFrom');
    const dateToInput = document.getElementById('dateTo');
    const applyFiltersBtn = document.getElementById('applyFiltersBtn');

    let currentPage = 1;
    const perPage = 20;
    let isLoading = false;
    let hasMore = true;
    let currentSearchQuery = '';
    
    // Store current filter values
    let currentSortBy = 'created_at';
    let currentSortOrder = 'desc';
    let currentDateFrom = '';
    let currentDateTo = '';

    async function fetchBlacklist(page, query = '', sortBy = 'created_at', sortOrder = 'desc', dateFrom = '', dateTo = '') {
        if (isLoading || !hasMore) return;
        isLoading = true;
        loadingIndicator.style.display = 'block';
        noMoreResultsIndicator.style.display = 'none';

        try {
            let apiUrl = `/api/fullist?page=${page}&per_page=${perPage}`;
            if (query) {
                apiUrl += `&q=${encodeURIComponent(query)}`;
            }
            if (sortBy) {
                apiUrl += `&sort_by=${encodeURIComponent(sortBy)}`;
            }
            if (sortOrder) {
                apiUrl += `&sort_order=${encodeURIComponent(sortOrder)}`;
            }
            if (dateFrom) {
                apiUrl += `&date_from=${encodeURIComponent(dateFrom)}`;
            }
            if (dateTo) {
                apiUrl += `&date_to=${encodeURIComponent(dateTo)}`;
            }

            const response = await fetch(apiUrl);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            if (data.items && data.items.length > 0) {
                data.items.forEach(item => {
                    const entryDiv = document.createElement('div');
                    entryDiv.className = 'list-group-item list-group-item-action flex-column align-items-start';
                    
                    const headerDiv = document.createElement('div');
                    headerDiv.className = 'd-flex w-100 justify-content-between';
                    
                    const nicknameH5 = document.createElement('h5');
                    nicknameH5.className = 'mb-1';
                    nicknameH5.textContent = item.nickname;
                    
                    const createdAtSmall = document.createElement('small');
                    createdAtSmall.textContent = item.created_at ? new Date(item.created_at).toLocaleDateString() : 'N/A';
                    
                    headerDiv.appendChild(nicknameH5);
                    headerDiv.appendChild(createdAtSmall);
                    
                    const reasonP = document.createElement('p');
                    reasonP.className = 'mb-1';
                    reasonP.textContent = `Причина: ${item.reason || 'Не указана'}`;
                    
                    const uuidSmall = document.createElement('small');
                    uuidSmall.textContent = `UUID: ${item.uuid}`;
                    uuidSmall.className = 'text-muted';

                    // Avatar
                    const avatarImg = document.createElement('img');
                    avatarImg.alt = item.nickname + " avatar";
                    avatarImg.style.width = '50px';
                    avatarImg.style.height = '50px';
                    avatarImg.style.marginRight = '15px';
                    avatarImg.loading = 'lazy';
                    
                    // Fetch avatar data
                    fetch(`/api/avatar/${item.uuid}`)
                        .then(res => res.json())
                        .then(avatarData => {
                            if (avatarData && avatarData.avatar_base64) {
                                avatarImg.src = avatarData.avatar_base64;
                            } else {
                                avatarImg.src = 'https://minotar.net/helm/MHF_Steve/50.png'; // Fallback
                            }
                        })
                        .catch(() => {
                            avatarImg.src = 'https://minotar.net/helm/MHF_Steve/50.png'; // Fallback on error
                        });

                    const contentDiv = document.createElement('div');
                    contentDiv.className = 'd-flex align-items-center';
                    contentDiv.appendChild(avatarImg);
                    
                    const textDiv = document.createElement('div');
                    textDiv.appendChild(headerDiv);
                    textDiv.appendChild(reasonP);
                    textDiv.appendChild(uuidSmall);
                    contentDiv.appendChild(textDiv);

                    entryDiv.appendChild(contentDiv);
                    blacklistContainer.appendChild(entryDiv);
                });
                currentPage++;
                hasMore = data.has_more;
                if (!hasMore) {
                    noMoreResultsIndicator.style.display = 'block';
                }
            } else {
                hasMore = false;
                if (page === 1) { // Only show if it's the first page and no results
                    blacklistContainer.innerHTML = '<p class="text-center text-muted">Записи не найдены.</p>';
                }
                noMoreResultsIndicator.style.display = 'block';
            }
        } catch (error) {
            console.error('Failed to fetch blacklist:', error);
            blacklistContainer.innerHTML = '<p class="text-center text-danger">Не удалось загрузить список. Попробуйте позже.</p>';
        }
        isLoading = false;
        loadingIndicator.style.display = 'none';
    }

    function resetAndLoad() {
        currentPage = 1;
        hasMore = true;
        blacklistContainer.innerHTML = ''; 
        noMoreResultsIndicator.style.display = 'none';
        // Get current values from controls
        currentSearchQuery = searchInput.value.trim();
        currentSortBy = sortBySelect.value;
        currentSortOrder = sortOrderSelect.value;
        currentDateFrom = dateFromInput.value;
        currentDateTo = dateToInput.value;
        fetchBlacklist(currentPage, currentSearchQuery, currentSortBy, currentSortOrder, currentDateFrom, currentDateTo);
    }

    // Initial load
    fetchBlacklist(currentPage, currentSearchQuery, currentSortBy, currentSortOrder, currentDateFrom, currentDateTo);

    // Scroll event for infinite loading
    window.addEventListener('scroll', () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200 && !isLoading && hasMore) {
            fetchBlacklist(currentPage, currentSearchQuery, currentSortBy, currentSortOrder, currentDateFrom, currentDateTo);
        }
    });

    // Search input event
    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            resetAndLoad();
        }, 500); // Debounce search
    });

    // Apply filters button event
    if (applyFiltersBtn) { // Ensure button exists
        applyFiltersBtn.addEventListener('click', () => {
            resetAndLoad();
        });
    }
    
    // Also trigger resetAndLoad if any of the select/date inputs change directly (optional)
    [sortBySelect, sortOrderSelect, dateFromInput, dateToInput].forEach(element => {
        if (element) { // Check if element exists before adding listener
            element.addEventListener('change', () => {
                // If you want immediate reload on change, call resetAndLoad().
                // Otherwise, user relies on the "Apply" button.
                // For this setup, we rely on the Apply button, so this can be empty or a visual cue.
            });
        }
    });
}); 