class InfiniteScroll {
  constructor(container, options = {}) {
    this.container = container;
    this.options = {
      perPage: options.perPage || 20,
      threshold: options.threshold || 100,
      loadingTemplate: options.loadingTemplate || '<div class="loading">Загрузка...</div>',
      ...options
    };
    
    this.page = 1;
    this.loading = false;
    this.hasMore = true;
    
    this.init();
  }
  
  init() {
    // Create loading element
    this.loadingEl = document.createElement('div');
    this.loadingEl.innerHTML = this.options.loadingTemplate;
    this.loadingEl.style.display = 'none';
    this.container.appendChild(this.loadingEl);
    
    // Add scroll listener
    window.addEventListener('scroll', this.handleScroll.bind(this));
    
    // Initial load
    this.loadMore();
  }
  
  handleScroll() {
    if (this.loading || !this.hasMore) return;
    
    const scrollPos = window.innerHeight + window.scrollY;
    const threshold = document.documentElement.offsetHeight - this.options.threshold;
    
    if (scrollPos >= threshold) {
      this.loadMore();
    }
  }
  
  async loadMore() {
    try {
      this.loading = true;
      this.loadingEl.style.display = 'block';
      
      const response = await fetch(`/api/fullist?page=${this.page}&per_page=${this.options.perPage}`);
      const data = await response.json();
      
      if (data.items && data.items.length > 0) {
        await this.renderItems(data.items);
        this.page++;
        this.hasMore = data.has_more;
      } else {
        this.hasMore = false;
      }
    } catch (error) {
      console.error('Failed to load more items:', error);
      showToast('Ошибка загрузки данных', 'error');
    } finally {
      this.loading = false;
      this.loadingEl.style.display = 'none';
    }
  }
  
  async renderItems(items) {
    const fragment = document.createDocumentFragment();
    
    for (const item of items) {
      const element = document.createElement('div');
      element.className = 'blacklist-entry';
      
      let avatarSrc = '/static/icons/favicon.ico'; // Placeholder/fallback avatar
      try {
        const avatarResponse = await fetch(`/api/avatar/${item.uuid}`);
        if (avatarResponse.ok) {
          const avatarData = await avatarResponse.json();
          if (avatarData.avatar_base64) {
            avatarSrc = avatarData.avatar_base64;
          }
        }
      } catch (e) {
        console.error(`Failed to load avatar for ${item.nickname}:`, e);
      }
      
      element.innerHTML = `
        <div class="entry-header">
          <img src="${avatarSrc}" alt="${item.nickname}" class="avatar" loading="lazy">
          <h3>${item.nickname}</h3>
        </div>
        <div class="entry-details">
          <p class="reason">${item.reason}</p>
          <p class="date">${new Date(item.created_at).toLocaleDateString('ru-RU')}</p>
        </div>
      `;
      fragment.appendChild(element);
    }
    
    this.container.insertBefore(fragment, this.loadingEl);
  }
  
  reset() {
    this.page = 1;
    this.hasMore = true;
    this.container.innerHTML = '';
    this.init();
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