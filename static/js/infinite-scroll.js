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
document.addEventListener('DOMContentLoaded', () => {
  const container = document.querySelector('.blacklist-entries');
  if (container) {
    new InfiniteScroll(container, {
      perPage: 20,
      threshold: 200,
      loadingTemplate: `
        <div class="loading-spinner">
          <div class="spinner"></div>
          <p>Загрузка записей...</p>
        </div>
      `
    });
  }
}); 