document.addEventListener('DOMContentLoaded', () => {
  const searchInput = document.getElementById('searchInput');
  const blacklistContainer = document.getElementById('blacklistContainer');
  const loadingIndicator = document.getElementById('loadingIndicator');
  const noMoreResultsIndicator = document.getElementById('noMoreResultsIndicator');

  // Filter and Sort controls (get them if they exist)
  const sortBySelect = document.getElementById('sortBy');
  const sortOrderSelect = document.getElementById('sortOrder');
  const dateFromInput = document.getElementById('dateFrom');
  const dateToInput = document.getElementById('dateTo');
  const applyFiltersBtn = document.getElementById('applyFiltersBtn');

  if (!blacklistContainer) {
    console.error('Blacklist container not found. Infinite scroll cannot be initialized.');
    return;
  }

  if (!window.supabaseInstance) {
    console.error('Supabase client not initialized. Some features may not work.');
  }

  const initialOptions = {
    perPage: 20,
    threshold: 200, // Adjusted threshold for potentially taller items
    searchQuery: searchInput ? searchInput.value.trim() : '',
    loadingTemplate: '<div class="loading-spinner"><div class="spinner"></div><p>Загрузка записей...</p></div>',
    noMoreResultsIndicator: noMoreResultsIndicator,
    loadingIndicator: loadingIndicator,
    initialPageContentElement: blacklistContainer,
    // Set initial sort/filter values if controls exist, otherwise defaults in class will be used
    sortBy: sortBySelect ? sortBySelect.value : 'created_at',
    sortOrder: sortOrderSelect ? sortOrderSelect.value : 'desc',
    dateFrom: dateFromInput ? dateFromInput.value : '',
    dateTo: dateToInput ? dateToInput.value : '',
    supabaseClient: window.supabaseInstance // Use the global Supabase instance
  };

  const globalInfiniteScrollInstance = new InfiniteScroll(blacklistContainer, initialOptions);

  let searchTimeout;
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        globalInfiniteScrollInstance.options.searchQuery = e.target.value.trim();
        // If filter/sort controls are present, their current values should also be applied
        if (sortBySelect) globalInfiniteScrollInstance.options.sortBy = sortBySelect.value;
        if (sortOrderSelect) globalInfiniteScrollInstance.options.sortOrder = sortOrderSelect.value;
        if (dateFromInput) globalInfiniteScrollInstance.options.dateFrom = dateFromInput.value;
        if (dateToInput) globalInfiniteScrollInstance.options.dateTo = dateToInput.value;
        globalInfiniteScrollInstance.reset();
      }, 300); // Debounce search
    });
  }

  if (applyFiltersBtn) {
    applyFiltersBtn.addEventListener('click', () => {
      globalInfiniteScrollInstance.options.searchQuery = searchInput ? searchInput.value.trim() : '';
      globalInfiniteScrollInstance.options.sortBy = sortBySelect ? sortBySelect.value : 'created_at';
      globalInfiniteScrollInstance.options.sortOrder = sortOrderSelect ? sortOrderSelect.value : 'desc';
      globalInfiniteScrollInstance.options.dateFrom = dateFromInput ? dateFromInput.value : '';
      globalInfiniteScrollInstance.options.dateTo = dateToInput ? dateToInput.value : '';
      globalInfiniteScrollInstance.reset();
    });
  }
}); 