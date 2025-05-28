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
      sortBy: options.sortBy || 'created_at', // Default sort
      sortOrder: options.sortOrder || 'desc', // Default order
      dateFrom: options.dateFrom || '',
      dateTo: options.dateTo || '',
      supabaseClient: options.supabaseClient || null // Added Supabase client
    };
    
    this.page = 1;
    this.loading = false;
    this.hasMore = true;
    this.realtimeChannel = null;
    this.itemsCache = new Map(); // Cache items by ID for quick updates/deletes
    
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

    if (this.options.supabaseClient) {
      this.subscribeToRealtimeUpdates();
    }
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
        await this.renderItems(data.items, false); // false for not prepending
        this.page++;
        this.hasMore = data.has_more;
        if (!this.hasMore && this.options.noMoreResultsIndicator) {
            this.options.noMoreResultsIndicator.style.display = 'block';
        }
      } else {
        this.hasMore = false;
        if (this.page === 1 && this.options.initialPageContentElement && this.container.children.length === (this.actualLoadingEl ? 1 : 0) ) { 
            this.options.initialPageContentElement.innerHTML = '<p class="text-center text-muted">Записи не найдены.</p>';
        }
        if (this.options.noMoreResultsIndicator) this.options.noMoreResultsIndicator.style.display = 'block';
      }
    } catch (error) {
      console.error('Failed to load more items:', error);
      if (this.options.initialPageContentElement && this.page === 1) { 
          this.options.initialPageContentElement.innerHTML = '<p class="text-center text-danger">Не удалось загрузить список. Попробуйте позже.</p>';
      }
      // Optionally, display a toast or specific error message to the user here
      // showToast('Ошибка загрузки данных', 'error'); // If you have a showToast function
    } finally {
      this.loading = false;
      if (this.actualLoadingEl) this.actualLoadingEl.style.display = 'none';
    }
  }
  
  async createItemElement(item) {
    const element = document.createElement('div');
    element.className = 'blacklist-entry';
    element.dataset.id = item.id; // Use database ID for tracking

    let avatarSrc = 'https://minotar.net/helm/MHF_Steve/50.png';
    try {
        // Use the new combined player details endpoint if available
        const detailsResponse = await fetch(`/api/player-details/${item.uuid}`);
        if (detailsResponse.ok) {
            const detailsData = await detailsResponse.json();
            if (detailsData.avatar_base64) avatarSrc = detailsData.avatar_base64;
            // item.nickname might be updated by this too, but the render logic below uses item.nickname from payload
        } else {
            console.warn(`Failed to fetch player details for ${item.uuid} (status: ${detailsResponse.status})`);
        }
    } catch (e) {
        console.warn(`Error fetching player details for ${item.uuid}:`, e);
    }

    element.innerHTML = `
      <div class="entry-header">
        <img src="${avatarSrc}" alt="${item.nickname}" class="avatar" loading="lazy" style="width:50px; height:50px; margin-right:10px; border-radius:5px;">
        <h3>${item.nickname || 'Неизвестный'}</h3>
      </div>
      <div class="entry-details">
        <p class="reason" style="margin: 5px 0;">Причина: ${item.reason || 'Не указана'}</p>
        <p class="uuid" style="font-size:0.8em; color: #ccc;">UUID: ${item.uuid}</p>
        <p class="date" style="font-size:0.8em; color: #ccc;">Добавлено: ${item.created_at ? new Date(item.created_at).toLocaleDateString('ru-RU') : 'N/A'}</p>
      </div>
    `;
    return element;
  }
  
  async renderItems(items, prepend = false) {
    if (!this.container) return;
    const fragment = document.createDocumentFragment();
    
    for (const item of items) {
      if (!item.id) {
          console.warn("Item without ID found, cannot cache or reliably update:", item);
          continue;
      }
      const element = await this.createItemElement(item);
      this.itemsCache.set(item.id.toString(), element); // Cache element by ID
      fragment.appendChild(element);
    }
    
    if (prepend) {
        this.container.insertBefore(fragment, this.container.firstChild);
    } else {
        if (this.actualLoadingEl && this.actualLoadingEl.parentNode === this.container) {
            this.container.insertBefore(fragment, this.actualLoadingEl);
        } else {
            this.container.appendChild(fragment);
        }
    }
  }
  
  reset() {
    this.page = 1;
    this.hasMore = true;
    this.loading = false;
    this.itemsCache.clear(); // Clear the cache
    if (this.container) this.container.innerHTML = '';
    if (this.actualLoadingEl && this.actualLoadingEl.parentNode !== this.container && this.container) {
        this.container.appendChild(this.actualLoadingEl);
    }
    if (this.options.noMoreResultsIndicator) this.options.noMoreResultsIndicator.style.display = 'none';
    this.loadMore();
  }

  subscribeToRealtimeUpdates() {
    if (!this.options.supabaseClient || this.realtimeChannel) return;

    this.realtimeChannel = this.options.supabaseClient
      .channel('public:blacklist_entry')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'blacklist_entry' }, 
        async (payload) => {
          console.log('Blacklist realtime update:', payload);
          // Basic check: If search query or filters are active, a full reload might be more accurate
          // For now, we'll attempt direct DOM manipulation and inform user about potential inconsistencies.
          if (this.options.searchQuery || this.options.dateFrom || this.options.dateTo) {
              console.warn("Realtime update received while filters/search active. List might become inconsistent until next manual search/filter.");
              // Optionally, display a small notification to the user.
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
            default:
              console.log("Unhandled realtime event type:", payload.eventType);
          }
        }
      )
      .subscribe((status, err) => {
        if (status === 'SUBSCRIBED') {
          console.log('Subscribed to blacklist_entry realtime updates!');
        } else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          console.error(`Realtime subscription failed: ${status}`, err);
          // Optionally, try to resubscribe or notify user
        } else {
          console.log('Realtime subscription status:', status);
        }
      });
  }

  async handleRealtimeInsert(newItem) {
    if (!newItem || !newItem.id || this.itemsCache.has(newItem.id.toString())) return; // Avoid duplicates
    
    // Consider sort order for prepending/appending - by default, prepend for 'desc' created_at
    const prepend = this.options.sortBy === 'created_at' && this.options.sortOrder === 'desc';
    await this.renderItems([newItem], prepend);
    if (this.options.initialPageContentElement && this.container.querySelector('.text-center.text-muted')){
        this.options.initialPageContentElement.innerHTML = ''; // Clear "No records found" if it was there
    }
    // Potentially show a toast notification for new entry
  }

  async handleRealtimeUpdate(updatedItem) {
    if (!updatedItem || !updatedItem.id) return;
    const itemKey = updatedItem.id.toString();
    const existingElement = this.itemsCache.get(itemKey);

    if (existingElement) {
      // Re-render the specific item with new data
      const newElement = await this.createItemElement(updatedItem);
      existingElement.replaceWith(newElement);
      this.itemsCache.set(itemKey, newElement); // Update cache
    } else {
      // Item not currently visible (e.g. on another page or filtered out)
      // We could choose to add it if it now matches filters, or ignore.
      // For simplicity, we'll ignore if not already visible from scroll loading.
      console.log("Realtime update for item not currently in view:", updatedItem.id);
    }
  }

  handleRealtimeDelete(deletedItem) {
    if (!deletedItem || !deletedItem.id) return;
    const itemKey = deletedItem.id.toString();
    const existingElement = this.itemsCache.get(itemKey);

    if (existingElement) {
      existingElement.remove();
      this.itemsCache.delete(itemKey);
    }
    if (this.container.children.length === (this.actualLoadingEl ? 1 : 0) && this.page ===1 && !this.hasMore && this.options.initialPageContentElement) {
        this.options.initialPageContentElement.innerHTML = '<p class="text-center text-muted">Записи не найдены.</p>';
    }
  }

  unsubscribeRealtime() {
    if (this.realtimeChannel) {
      this.options.supabaseClient.removeChannel(this.realtimeChannel);
      this.realtimeChannel = null;
      console.log("Unsubscribed from blacklist_entry realtime updates.");
    }
  }
  // Call unsubscribeRealtime() if the component/page is destroyed or re-initialized.
} 