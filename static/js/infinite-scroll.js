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
      initialPageContentElement: options.initialPageContentElement, // Element to show "no results" on initial load
      sortBy: options.sortBy || '',
      sortOrder: options.sortOrder || '',
      dateFrom: options.dateFrom || '',
      dateTo: options.dateTo || ''
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
      if (this.options.sortBy) {
        apiUrl += `&sort_by=${encodeURIComponent(this.options.sortBy)}`;
      }
      if (this.options.sortOrder) {
        apiUrl += `&sort_order=${encodeURIComponent(this.options.sortOrder)}`;
      }
      if (this.options.dateFrom) {
        apiUrl += `&date_from=${encodeURIComponent(this.options.dateFrom)}`;
      }
      if (this.options.dateTo) {
        apiUrl += `&date_to=${encodeURIComponent(this.options.dateTo)}`;
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