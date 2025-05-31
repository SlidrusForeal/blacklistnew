// Supabase client initialization
function initSupabase(config) {
    if (!config || !config.url || !config.key) {
        console.error('Supabase configuration is missing');
        return null;
    }

    try {
        const supabase = window.supabase.createClient(config.url, config.key);
        console.log("Supabase client initialized successfully");
        return supabase;
    } catch (e) {
        console.error("Error initializing Supabase client:", e);
        return null;
    }
}

// Global Supabase instance
window.supabaseInstance = null; 