// Fetch API configuration
async function fetchApiConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const config = await response.json();
        if (!config.supabaseUrl || !config.supabaseKey) {
            throw new Error('Invalid configuration received');
        }
        return config;
    } catch (error) {
        console.error('Error fetching API configuration:', error);
        return null;
    }
}

// Initialize Supabase with fetched configuration
async function initializeSupabaseFromApi() {
    const config = await fetchApiConfig();
    if (!config) {
        console.error('Failed to fetch API configuration');
        return null;
    }

    try {
        window.supabaseInstance = initSupabase({
            url: config.supabaseUrl,
            key: config.supabaseKey
        });

        if (!window.supabaseInstance) {
            throw new Error('Failed to initialize Supabase client');
        }

        return window.supabaseInstance;
    } catch (error) {
        console.error('Error initializing Supabase:', error);
        return null;
    }
} 