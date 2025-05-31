// Enhanced infinite scroll with virtual DOM and performance optimizations
class InfiniteScroll {
  constructor(container, options = {}) {
    // Core properties
    this.container = container;
    this.virtualContainer = document.createElement('div');
    this.virtualContainer.className = 'virtual-scroll-container';
    this.container.appendChild(this.virtualContainer);
    
    // Configuration
    this.options = {
      perPage: options.perPage || 20,
      threshold: options.threshold || 200,
      loadingTemplate: options.loadingTemplate || '<div class="loading">Loading...</div>',
      searchQuery: options.searchQuery || '',
      noMoreResultsIndicator: options.noMoreResultsIndicator,
      loadingIndicator: options.loadingIndicator,
      initialPageContentElement: options.initialPageContentElement,
      sortBy: options.sortBy || 'created_at',
      sortOrder: options.sortOrder || 'desc',
      dateFrom: options.dateFrom || '',
      dateTo: options.dateTo || '',
      supabaseClient: options.supabaseClient || null,
      itemHeight: options.itemHeight || 180, // Estimated item height for virtual scrolling
      bufferSize: options.bufferSize || 5, // Number of items to render above/below viewport
      debounceDelay: options.debounceDelay || 150 // Debounce delay for scroll events
    };
    
    // State
    this.state = {
      page: 1,
      loading: false,
      hasMore: true,
      items: [], // All loaded items
      visibleItems: new Set(), // Currently rendered items
      lastScrollPosition: 0,
      scrollDirection: 'down',
      virtualScrollHeight: 0
    };
    
    // Cache
    this.cache = {
      elements: new Map(), // Cache DOM elements by ID
      avatars: new Map(), // Cache avatar URLs
      intersectionObserver: null,
      scrollTimeout: null,
      resizeObserver: null,
      mutationObserver: null
    };
    
    // Initialize
    this.init();
  }
  
  init() {
    // Setup loading indicator
    this.setupLoadingIndicator();
    
    // Setup virtual scrolling
    this.setupVirtualScroll();
    
    // Setup observers
    this.setupObservers();
    
    // Initial load
    this.loadMore();
    
    // Setup realtime updates if available
    if (this.options.supabaseClient) {
      this.subscribeToRealtimeUpdates();
    }
  }
  
  setupLoadingIndicator() {
    this.actualLoadingEl = this.options.loadingIndicator;
    if (!this.actualLoadingEl && this.container) {
      const loadingElDiv = document.createElement('div');
      loadingElDiv.innerHTML = this.options.loadingTemplate;
      this.actualLoadingEl = loadingElDiv.firstChild;
      if (this.actualLoadingEl) {
        this.actualLoadingEl.style.cssText = `
          position: fixed;
          bottom: 20px;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(0, 0, 0, 0.8);
          color: white;
          padding: 10px 20px;
          border-radius: 20px;
          z-index: 1000;
          display: none;
        `;
        document.body.appendChild(this.actualLoadingEl);
      }
    }
    
    if (this.options.noMoreResultsIndicator) {
      this.options.noMoreResultsIndicator.style.display = 'none';
    }
  }
  
  setupVirtualScroll() {
    // Setup virtual scroll container styles
    this.virtualContainer.style.cssText = `
      position: relative;
      width: 100%;
      min-height: 100px;
    `;
    
    // Debounced scroll handler
    const handleScroll = () => {
      if (this.cache.scrollTimeout) {
        window.cancelAnimationFrame(this.cache.scrollTimeout);
      }
      
      this.cache.scrollTimeout = window.requestAnimationFrame(() => {
        const scrollPos = window.scrollY;
        this.state.scrollDirection = scrollPos > this.state.lastScrollPosition ? 'down' : 'up';
        this.state.lastScrollPosition = scrollPos;
        
        this.updateVisibleItems();
        this.checkLoadMore();
      });
    };
    
    // Throttled resize handler
    const handleResize = () => {
      if (this.cache.resizeTimeout) {
        clearTimeout(this.cache.resizeTimeout);
      }
      
      this.cache.resizeTimeout = setTimeout(() => {
        this.updateVisibleItems();
      }, 150);
    };
    
    // Event listeners
    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', handleResize, { passive: true });
  }
  
  setupObservers() {
    // Intersection Observer for lazy loading images
    this.cache.intersectionObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            if (img.dataset.src) {
              img.src = img.dataset.src;
              img.removeAttribute('data-src');
              this.cache.intersectionObserver.unobserve(img);
            }
          }
        });
      },
      {
        rootMargin: '50px 0px',
        threshold: 0.1
      }
    );
    
    // Resize Observer for dynamic height adjustments
    if ('ResizeObserver' in window) {
      this.cache.resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
          const itemId = entry.target.dataset.id;
          if (itemId) {
            this.updateItemHeight(itemId, entry.contentRect.height);
          }
        }
      });
    }
    
    // Mutation Observer for dynamic content changes
    this.cache.mutationObserver = new MutationObserver(mutations => {
      let needsUpdate = false;
      for (const mutation of mutations) {
        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
          needsUpdate = true;
          break;
        }
      }
      if (needsUpdate) {
        this.updateVisibleItems();
      }
    });
    
    this.cache.mutationObserver.observe(this.virtualContainer, {
      childList: true,
      subtree: true
    });
  }
  
  updateVisibleItems() {
    const viewportTop = window.scrollY;
    const viewportBottom = viewportTop + window.innerHeight;
    const buffer = this.options.bufferSize * this.options.itemHeight;
    
    const startIndex = Math.max(0, Math.floor((viewportTop - buffer) / this.options.itemHeight));
    const endIndex = Math.min(
      this.state.items.length,
      Math.ceil((viewportBottom + buffer) / this.options.itemHeight)
    );
    
    // Calculate which items should be visible
    const newVisibleItems = new Set();
    for (let i = startIndex; i < endIndex; i++) {
      const item = this.state.items[i];
      if (item) {
        newVisibleItems.add(item.id.toString());
      }
    }
    
    // Remove items that shouldn't be visible
    for (const itemId of this.state.visibleItems) {
      if (!newVisibleItems.has(itemId)) {
        const element = this.cache.elements.get(itemId);
        if (element && element.parentNode === this.virtualContainer) {
          this.virtualContainer.removeChild(element);
        }
      }
    }
    
    // Add items that should be visible
    for (const itemId of newVisibleItems) {
      if (!this.state.visibleItems.has(itemId)) {
        const item = this.state.items.find(i => i.id.toString() === itemId);
        if (item) {
          this.renderItem(item);
        }
      }
    }
    
    this.state.visibleItems = newVisibleItems;
  }
  
  updateItemHeight(itemId, height) {
    const index = this.state.items.findIndex(item => item.id.toString() === itemId);
    if (index !== -1) {
      const element = this.cache.elements.get(itemId);
      if (element) {
        element.style.top = `${index * this.options.itemHeight}px`;
      }
    }
  }
  
  checkLoadMore() {
    if (this.state.loading || !this.state.hasMore) return;
    
    const scrollPos = window.innerHeight + window.scrollY;
    const triggerPoint = document.documentElement.offsetHeight - this.options.threshold;
    
    if (scrollPos >= triggerPoint) {
      this.loadMore();
    }
  }
  
  async loadMore() {
    if (this.state.loading || !this.state.hasMore) return;
    
    this.state.loading = true;
    if (this.actualLoadingEl) this.actualLoadingEl.style.display = 'block';
    
    try {
      const queryParams = new URLSearchParams({
        page: this.state.page.toString(),
        per_page: this.options.perPage.toString(),
        sort_by: this.options.sortBy,
        sort_order: this.options.sortOrder
      });
      
      if (this.options.searchQuery) queryParams.set('q', this.options.searchQuery);
      if (this.options.dateFrom) queryParams.set('date_from', this.options.dateFrom);
      if (this.options.dateTo) queryParams.set('date_to', this.options.dateTo);
      
      const response = await fetch(`/api/fullist?${queryParams}`);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      
      const data = await response.json();
      
      if (data.items?.length > 0) {
        // Update state
        this.state.items.push(...data.items);
        this.state.page++;
        this.state.hasMore = data.has_more;
        
        // Update virtual scroll height
        this.state.virtualScrollHeight = this.state.items.length * this.options.itemHeight;
        this.virtualContainer.style.height = `${this.state.virtualScrollHeight}px`;
        
        // Update visible items
        this.updateVisibleItems();
        
        // Show "no more results" if needed
        if (!this.state.hasMore && this.options.noMoreResultsIndicator) {
          this.options.noMoreResultsIndicator.style.display = 'block';
        }
      } else {
        this.state.hasMore = false;
        if (this.state.page === 1) {
          this.showNoResults();
        }
      }
    } catch (error) {
      console.error('Failed to load more items:', error);
      this.handleError(error);
    } finally {
      this.state.loading = false;
      if (this.actualLoadingEl) this.actualLoadingEl.style.display = 'none';
    }
  }
  
  async renderItem(item) {
    const itemId = item.id.toString();
    let element = this.cache.elements.get(itemId);
    
    if (!element) {
      element = document.createElement('div');
      element.className = 'blacklist-entry';
      element.dataset.id = itemId;
      element.style.cssText = `
        position: absolute;
        left: 0;
        right: 0;
        height: ${this.options.itemHeight}px;
        transition: transform 0.3s ease;
      `;
      
      // Get cached avatar or fetch new one
      let avatarSrc = this.cache.avatars.get(item.uuid) || 'https://minotar.net/helm/MHF_Steve/50.png';
      
      if (!this.cache.avatars.has(item.uuid)) {
        try {
          const detailsResponse = await fetch(`/api/player-details/${item.uuid}`);
          if (detailsResponse.ok) {
            const detailsData = await detailsResponse.json();
            if (detailsData.avatar_base64) {
              avatarSrc = detailsData.avatar_base64;
              this.cache.avatars.set(item.uuid, avatarSrc);
            }
          }
        } catch (error) {
          console.warn(`Error fetching player details for ${item.uuid}:`, error);
        }
      }
      
      element.innerHTML = `
        <div class="entry-header">
          <img 
            src="${avatarSrc}" 
            alt="${item.nickname || 'Unknown'}" 
            class="avatar" 
            loading="lazy" 
            style="width:50px; height:50px; margin-right:10px; border-radius:5px;"
          >
          <h3>${item.nickname || 'Unknown'}</h3>
        </div>
        <div class="entry-details">
          <p class="reason" style="margin: 5px 0;">Reason: ${item.reason || 'Not specified'}</p>
          <p class="uuid" style="font-size:0.8em; color: #ccc;">UUID: ${item.uuid}</p>
          <p class="date" style="font-size:0.8em; color: #ccc;">Added: ${
            item.created_at ? 
            new Intl.DateTimeFormat('ru-RU', {
              year: 'numeric',
              month: 'long',
              day: 'numeric'
            }).format(new Date(item.created_at)) : 
            'N/A'
          }</p>
        </div>
      `;
      
      // Cache the element
      this.cache.elements.set(itemId, element);
      
      // Observe images for lazy loading
      element.querySelectorAll('img[loading="lazy"]').forEach(img => {
        this.cache.intersectionObserver.observe(img);
      });
      
      // Observe element size if ResizeObserver is available
      if (this.cache.resizeObserver) {
        this.cache.resizeObserver.observe(element);
      }
    }
    
    // Position the element
    const index = this.state.items.findIndex(i => i.id.toString() === itemId);
    element.style.transform = `translateY(${index * this.options.itemHeight}px)`;
    
    // Add to DOM if not already there
    if (!element.parentNode) {
      this.virtualContainer.appendChild(element);
    }
  }
  
  showNoResults() {
    if (this.options.initialPageContentElement) {
      this.options.initialPageContentElement.innerHTML = `
        <div class="no-results" style="text-align: center; padding: 40px;">
          <p style="color: var(--text-muted); font-size: 1.1em;">No records found.</p>
          ${this.options.searchQuery ? `
            <p style="color: var(--text-muted); font-size: 0.9em;">
              Try adjusting your search criteria.
            </p>
          ` : ''}
        </div>
      `;
    }
  }
  
  handleError(error) {
    if (this.options.initialPageContentElement && this.state.page === 1) {
      this.options.initialPageContentElement.innerHTML = `
        <div class="error-message" style="text-align: center; padding: 40px;">
          <p style="color: var(--error-color); font-size: 1.1em;">
            Failed to load the list. Please try again later.
          </p>
          <button onclick="location.reload()" style="
            margin-top: 20px;
            padding: 10px 20px;
            background: var(--primary-color);
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
          ">
            Retry
          </button>
        </div>
      `;
    }
    
    // Show toast notification if available
    if (window.showToast) {
      window.showToast('Error loading data. Please try again later.', 'error');
    }
  }
  
  reset() {
    // Reset state
    this.state = {
      ...this.state,
      page: 1,
      hasMore: true,
      loading: false,
      items: [],
      visibleItems: new Set(),
      virtualScrollHeight: 0
    };
    
    // Clear cache
    this.cache.elements.clear();
    this.cache.avatars.clear();
    
    // Reset DOM
    this.virtualContainer.innerHTML = '';
    this.virtualContainer.style.height = '100px';
    
    if (this.options.noMoreResultsIndicator) {
      this.options.noMoreResultsIndicator.style.display = 'none';
    }
    
    // Reload
    this.loadMore();
  }
  
  destroy() {
    // Remove event listeners
    window.removeEventListener('scroll', this.handleScroll);
    window.removeEventListener('resize', this.handleResize);
    
    // Disconnect observers
    this.cache.intersectionObserver?.disconnect();
    this.cache.resizeObserver?.disconnect();
    this.cache.mutationObserver?.disconnect();
    
    // Unsubscribe from realtime updates
    this.unsubscribeRealtime();
    
    // Clear timeouts
    if (this.cache.scrollTimeout) {
      window.cancelAnimationFrame(this.cache.scrollTimeout);
    }
    if (this.cache.resizeTimeout) {
      clearTimeout(this.cache.resizeTimeout);
    }
    
    // Remove loading indicator
    if (this.actualLoadingEl && this.actualLoadingEl.parentNode) {
      this.actualLoadingEl.parentNode.removeChild(this.actualLoadingEl);
    }
    
    // Clear cache and state
    this.cache.elements.clear();
    this.cache.avatars.clear();
    this.state.items = [];
    this.state.visibleItems.clear();
    
    // Remove virtual container
    if (this.virtualContainer.parentNode) {
      this.virtualContainer.parentNode.removeChild(this.virtualContainer);
    }
  }
  
  // Realtime update handlers
  subscribeToRealtimeUpdates() {
    if (!this.options.supabaseClient || this.realtimeChannel) return;
    
    this.realtimeChannel = this.options.supabaseClient
      .channel('public:blacklist_entry')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'blacklist_entry' },
        this.handleRealtimeEvent.bind(this)
      )
      .subscribe();
  }
  
  async handleRealtimeEvent(payload) {
    // Skip updates if filters are active
    if (this.options.searchQuery || this.options.dateFrom || this.options.dateTo) {
      console.warn('Realtime update skipped due to active filters');
      return;
    }
    
    switch (payload.eventType) {
      case 'INSERT':
        await this.handleRealtimeInsert(payload.new);
        break;
      case 'UPDATE':
        await this.handleRealtimeUpdate(payload.new);
        break;
      case 'DELETE':
        this.handleRealtimeDelete(payload.old);
        break;
    }
  }
  
  async handleRealtimeInsert(newItem) {
    if (!newItem?.id || this.cache.elements.has(newItem.id.toString())) return;
    
    // Add to items array based on sort order
    if (this.options.sortBy === 'created_at' && this.options.sortOrder === 'desc') {
      this.state.items.unshift(newItem);
    } else {
      this.state.items.push(newItem);
    }
    
    // Update virtual scroll height
    this.state.virtualScrollHeight = this.state.items.length * this.options.itemHeight;
    this.virtualContainer.style.height = `${this.state.virtualScrollHeight}px`;
    
    // Update visible items
    this.updateVisibleItems();
    
    // Show notification
    if (window.showToast) {
      window.showToast('New entry added', 'info');
    }
  }
  
  async handleRealtimeUpdate(updatedItem) {
    if (!updatedItem?.id) return;
    
    const itemId = updatedItem.id.toString();
    const index = this.state.items.findIndex(item => item.id.toString() === itemId);
    
    if (index !== -1) {
      // Update item in state
      this.state.items[index] = updatedItem;
      
      // Update DOM if visible
      if (this.state.visibleItems.has(itemId)) {
        const element = this.cache.elements.get(itemId);
        if (element) {
          // Remove from cache to force re-render
          this.cache.elements.delete(itemId);
          if (element.parentNode) {
            element.parentNode.removeChild(element);
          }
          // Re-render item
          this.renderItem(updatedItem);
        }
      }
    }
  }
  
  handleRealtimeDelete(deletedItem) {
    if (!deletedItem?.id) return;
    
    const itemId = deletedItem.id.toString();
    const index = this.state.items.findIndex(item => item.id.toString() === itemId);
    
    if (index !== -1) {
      // Remove from state
      this.state.items.splice(index, 1);
      
      // Remove from DOM if visible
      if (this.state.visibleItems.has(itemId)) {
        const element = this.cache.elements.get(itemId);
        if (element && element.parentNode) {
          element.parentNode.removeChild(element);
        }
      }
      
      // Remove from cache
      this.cache.elements.delete(itemId);
      this.state.visibleItems.delete(itemId);
      
      // Update virtual scroll height
      this.state.virtualScrollHeight = this.state.items.length * this.options.itemHeight;
      this.virtualContainer.style.height = `${this.state.virtualScrollHeight}px`;
      
      // Update visible items
      this.updateVisibleItems();
    }
  }
  
  unsubscribeRealtime() {
    if (this.realtimeChannel) {
      this.realtimeChannel.unsubscribe();
      this.realtimeChannel = null;
    }
  }
} 