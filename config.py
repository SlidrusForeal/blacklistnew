import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flask and Security Configuration
SECRET_KEY = os.getenv('SECRET_KEY')
WTF_CSRF_SECRET_KEY = os.getenv('WTF_CSRF_SECRET_KEY')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

# GitHub Webhook Configuration
GITHUB_SECRET = os.getenv('WEBHOOK_SECRET')

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')  # Public anon key
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')  # Private service key

# Validate required environment variables
required_vars = [
    'SECRET_KEY',
    'WTF_CSRF_SECRET_KEY',
    'JWT_SECRET_KEY',
    'WEBHOOK_SECRET',
    'SUPABASE_URL',
    'SUPABASE_KEY',
    'SUPABASE_SERVICE_KEY'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}") 