import os
from dotenv import load_dotenv

load_dotenv()

# Supabase Configuration
SUPABASE_URL = "https://qknbojrrfhjqyiaupesx.supabase.co"
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFrbmJvanJyZmhqcXlpYXVwZXN4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgwMDM0NjUsImV4cCI6MjA2MzU3OTQ2NX0.WAE5nPoBk0J3FujE2WLy8ncRFW-bkwKJyO88MLKNwms')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFrbmJvanJyZmhqcXlpYXVwZXN4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0ODAwMzQ2NSwiZXhwIjoyMDYzNTc5NDY1fQ.HdM04qZCtQImIl1IXMCPdtAVW5gQFKPbxExj5AyV5rs')

# Flask Configuration
SECRET_KEY = os.getenv('SECRET_KEY')
WTF_CSRF_SECRET_KEY = os.getenv('WTF_CSRF_SECRET_KEY')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
GITHUB_SECRET = os.getenv('WEBHOOK_SECRET') 