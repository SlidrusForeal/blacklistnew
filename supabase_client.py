from supabase import create_client, Client
from datetime import datetime, timedelta
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

    def get_all_blacklist_entries(self, page: int = 1, per_page: int = 20, search: str = None, 
                                  sort_by: str = 'created_at', sort_order: str = 'desc',
                                  date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        try:
            query = self.client.table('blacklist_entry').select('*', count='exact')
            
            if search:
                query = query.or_(f'nickname.ilike.%{search}%,reason.ilike.%{search}%')

            # Date range filtering
            if date_from:
                try:
                    # Ensure date_from is a valid ISO format string if not already
                    # For simplicity, assuming it comes in a compatible format or add parsing/validation
                    query = query.gte('created_at', date_from)
                except Exception as e:
                    logger.warning(f"Invalid date_from format: {date_from} - {e}")
            if date_to:
                try:
                    # Add time to date_to to include the whole day if it's just a date
                    # For example, if date_to is YYYY-MM-DD, make it YYYY-MM-DD 23:59:59.999
                    # Or expect full ISO timestamps. For now, using it as is.
                    query = query.lte('created_at', date_to)
                except Exception as e:
                    logger.warning(f"Invalid date_to format: {date_to} - {e}")
            
            # Pagination
            start_index = (page - 1) * per_page
            query = query.range(start_index, start_index + per_page - 1)

            # Sorting
            allowed_sort_columns = ['nickname', 'reason', 'created_at']
            if sort_by not in allowed_sort_columns:
                sort_by = 'created_at' # Default to a safe column
            
            is_descending = sort_order.lower() == 'desc'
            query = query.order(sort_by, desc=is_descending)
            
            result = query.execute()
            
            total_items = result.count if hasattr(result, 'count') and result.count is not None else 0
            
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

    def get_total_blacklist_entries_count(self) -> int:
        try:
            result = self.client.table('blacklist_entry').select('id', count='exact').execute()
            return result.count if hasattr(result, 'count') and result.count is not None else 0
        except Exception as e:
            logger.error(f"Error getting total blacklist entries count: {e}")
            return 0

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

    # Audit Log Operations
    def add_audit_log(self, admin_username: str, action_type: str, target_type: Optional[str] = None, target_identifier: Optional[str] = None, details: Optional[str] = None) -> bool:
        try:
            data = {
                'timestamp': datetime.utcnow().isoformat(),
                'admin_username': admin_username,
                'action_type': action_type,
                'target_type': target_type,
                'target_identifier': target_identifier,
                'details': details
            }
            # Use admin_client as audit logs are sensitive and should always be writable
            result = self.admin_client.table('audit_log').insert(data).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error adding audit log: {e}")
            return False

    def get_audit_logs(self, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        try:
            query = self.admin_client.table('audit_log').select('*', count='exact')
            
            start = (page - 1) * per_page
            query = query.range(start, start + per_page - 1).order('timestamp', desc=True)
            
            result = query.execute()
            
            total_items = result.count if hasattr(result, 'count') and result.count is not None else 0
            
            return {
                'items': result.data,
                'page': page,
                'per_page': per_page,
                'total_items': total_items,
                'has_more': (page * per_page) < total_items
            }
        except Exception as e:
            logger.error(f"Error getting audit logs: {e}")
            return {'items': [], 'page': page, 'per_page': per_page, 'total_items': 0, 'has_more': False}

    # Check Log Operations
    def add_check_log(self, check_source: str) -> bool:
        try:
            data = {
                'timestamp': datetime.utcnow().isoformat(),
                'check_source': check_source 
            }
            # Using admin_client as this is an internal logging mechanism
            # If RLS is set up on check_log to allow anon inserts, self.client could be used.
            # For now, admin_client is safer.
            result = self.admin_client.table('check_log').insert(data).execute()
            return bool(result.data) # Or check for errors in result.error
        except Exception as e:
            logger.error(f"Error adding check log: {e}")
            return False

    def count_total_checks(self) -> int:
        try:
            result = self.admin_client.table('check_log').select('id', count='exact').execute()
            return result.count if hasattr(result, 'count') and result.count is not None else 0
        except Exception as e:
            logger.error(f"Error counting total checks: {e}")
            return 0

    def count_checks_last_24_hours(self) -> int:
        try:
            time_24_hours_ago = (datetime.utcnow() - timedelta(days=1)).isoformat()
            result = self.admin_client.table('check_log') \
                         .select('id', count='exact') \
                         .gte('timestamp', time_24_hours_ago) \
                         .execute()
            return result.count if hasattr(result, 'count') and result.count is not None else 0
        except Exception as e:
            logger.error(f"Error counting checks in last 24 hours: {e}")
            return 0

# Create a global instance
db = SupabaseClient() 