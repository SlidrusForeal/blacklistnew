from supabase import create_client, Client
from datetime import datetime
from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.admin_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # Blacklist operations
    def get_blacklist_entry(self, nickname: str) -> Optional[Dict[str, Any]]:
        try:
            result = self.client.table('blacklist_entry').select('*').ilike('nickname', nickname).execute()
            entries = result.data
            return entries[0] if entries else None
        except Exception as e:
            logger.error(f"Error getting blacklist entry: {e}")
            return None

    def get_blacklist_entry_by_id(self, entry_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = self.client.table('blacklist_entry').select('*').eq('id', entry_id).execute()
            entries = result.data
            return entries[0] if entries else None
        except Exception as e:
            logger.error(f"Error getting blacklist entry by ID: {e}")
            return None

    def add_blacklist_entry(self, nickname: str, uuid: str, reason: str) -> bool:
        try:
            data = {
                'nickname': nickname,
                'uuid': uuid,
                'reason': reason,
                'created_at': datetime.utcnow().isoformat()
            }
            result = self.admin_client.table('blacklist_entry').insert(data).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error adding blacklist entry: {e}")
            return False

    def update_blacklist_entry(self, entry_id: int, data: Dict[str, Any]) -> bool:
        try:
            result = self.admin_client.table('blacklist_entry').update(data).eq('id', entry_id).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error updating blacklist entry: {e}")
            return False

    def delete_blacklist_entry(self, entry_id: int) -> bool:
        try:
            result = self.admin_client.table('blacklist_entry').delete().eq('id', entry_id).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error deleting blacklist entry: {e}")
            return False

    def get_all_blacklist_entries(self, page: int = 1, per_page: int = 20, search: str = None) -> Dict[str, Any]:
        try:
            query = self.client.table('blacklist_entry').select('*')
            
            if search:
                query = query.or_(f'nickname.ilike.%{search}%,reason.ilike.%{search}%')
            
            # Get total count
            count_result = query.execute()
            total_items = len(count_result.data)
            
            # Get paginated results
            start = (page - 1) * per_page
            query = query.range(start, start + per_page - 1).order('created_at', desc=True)
            result = query.execute()
            
            return {
                'items': result.data,
                'page': page,
                'per_page': per_page,
                'total_items': total_items,
                'has_more': (page * per_page) < total_items
            }
        except Exception as e:
            logger.error(f"Error getting blacklist entries: {e}")
            return {'items': [], 'page': page, 'per_page': per_page, 'total_items': 0, 'has_more': False}

    # Admin user operations
    def get_admin_user(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            result = self.admin_client.table('admin_user').select('*').eq('username', username).execute()
            users = result.data
            return users[0] if users else None
        except Exception as e:
            logger.error(f"Error getting admin user: {e}")
            return None

    def get_admin_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = self.admin_client.table('admin_user').select('*').eq('id', user_id).execute()
            users = result.data
            return users[0] if users else None
        except Exception as e:
            logger.error(f"Error getting admin user by ID: {e}")
            return None

    def create_admin_user(self, username: str, password_hash: str, role: str) -> bool:
        try:
            data = {
                'username': username,
                'password_hash': password_hash,
                'role': role
            }
            result = self.admin_client.table('admin_user').insert(data).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error creating admin user: {e}")
            return False

    def get_all_admin_users(self) -> List[Dict[str, Any]]:
        try:
            result = self.admin_client.table('admin_user').select('*').order('username').execute()
            return result.data
        except Exception as e:
            logger.error(f"Error getting admin users: {e}")
            return []

    def delete_admin_user(self, user_id: int) -> bool:
        try:
            result = self.admin_client.table('admin_user').delete().eq('id', user_id).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error deleting admin user: {e}")
            return False

# Create a global instance
db = SupabaseClient() 