from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY
from typing import Optional, List, Dict, Any
from supabase_logger import SupabaseLogger

class SupabaseClient:
    def __init__(self):
        """Initialize Supabase client with both anonymous and service role clients"""
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self.logger = SupabaseLogger(self.admin_client)

    def _get_client(self, require_admin: bool = False) -> Client:
        """Get the appropriate client based on the operation type"""
        return self.admin_client if require_admin else self.client

    # Blacklist operations
    def get_blacklist_entry(self, nickname: str) -> Optional[Dict[str, Any]]:
        try:
            result = self._get_client().table('blacklist_entry').select('*').ilike('nickname', nickname).execute()
            entries = result.data
            if entries:
                self.logger.info(f"Found blacklist entry for nickname: {nickname}", 
                               extra={'nickname': nickname, 'entry_id': entries[0]['id']})
            else:
                self.logger.info(f"No blacklist entry found for nickname: {nickname}", 
                               extra={'nickname': nickname})
            return entries[0] if entries else None
        except Exception as e:
            self.logger.exception(f"Error getting blacklist entry for {nickname}", e, 
                                extra={'nickname': nickname})
            return None

    def get_blacklist_entry_by_id(self, entry_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = self._get_client().table('blacklist_entry').select('*').eq('id', entry_id).execute()
            entries = result.data
            if entries:
                self.logger.info(f"Found blacklist entry by ID: {entry_id}", 
                               extra={'entry_id': entry_id})
            else:
                self.logger.info(f"No blacklist entry found for ID: {entry_id}", 
                               extra={'entry_id': entry_id})
            return entries[0] if entries else None
        except Exception as e:
            self.logger.exception(f"Error getting blacklist entry by ID {entry_id}", e, 
                                extra={'entry_id': entry_id})
            return None

    def add_blacklist_entry(self, nickname: str, uuid: str, reason: str) -> bool:
        try:
            data = {
                'nickname': nickname,
                'uuid': uuid,
                'reason': reason,
                'created_at': datetime.utcnow().isoformat()
            }
            result = self._get_client(True).table('blacklist_entry').insert(data).execute()
            success = bool(result.data)
            if success:
                self.logger.info(f"Added blacklist entry for {nickname}", 
                               extra={'nickname': nickname, 'uuid': uuid, 'reason': reason})
            else:
                self.logger.warning(f"Failed to add blacklist entry for {nickname}", 
                                  extra={'nickname': nickname, 'uuid': uuid})
            return success
        except Exception as e:
            self.logger.exception(f"Error adding blacklist entry for {nickname}", e, 
                                extra={'nickname': nickname, 'uuid': uuid})
            return False

    def update_blacklist_entry(self, entry_id: int, data: Dict[str, Any]) -> bool:
        try:
            result = self._get_client(True).table('blacklist_entry').update(data).eq('id', entry_id).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception(f"Error updating blacklist entry for ID {entry_id}", e, 
                                extra={'entry_id': entry_id})
            return False

    def update_blacklist_entry_nickname(self, entry_id: int, new_nickname: str) -> bool:
        try:
            result = self._get_client(True).table('blacklist_entry').update({'nickname': new_nickname}).eq('id', entry_id).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception(f"Error updating blacklist entry nickname for ID {entry_id}", e, 
                                extra={'entry_id': entry_id, 'new_nickname': new_nickname})
            return False

    def delete_blacklist_entry(self, entry_id: int) -> bool:
        try:
            result = self._get_client(True).table('blacklist_entry').delete().eq('id', entry_id).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception(f"Error deleting blacklist entry for ID {entry_id}", e, 
                                extra={'entry_id': entry_id})
            return False

    def get_all_blacklist_entries(self, page: int = 1, per_page: int = 20, search: str = None, sort_by: str = 'created_at', sort_order: str = 'desc', date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        try:
            query = self._get_client().table('blacklist_entry').select('*', count='exact')
            
            if search:
                query = query.or_(f'nickname.ilike.%{search}%,reason.ilike.%{search}%')
            
            # Date filtering
            if date_from:
                query = query.gte('created_at', date_from)
            if date_to:
                # Add 1 day to date_to to make the range inclusive of the end date
                try:
                    end_date = datetime.fromisoformat(date_to.replace('Z', '+00:00')) + timedelta(days=1)
                    query = query.lte('created_at', end_date.isoformat())
                except ValueError:
                    self.logger.warning(f"Invalid date_to format: {date_to}. Skipping date_to filter.")

            # Sorting
            if sort_by and sort_order:
                is_desc = sort_order.lower() == 'desc'
                query = query.order(sort_by, desc=is_desc)
            else: # Default sort if not specified
                query = query.order('created_at', desc=True)

            # Pagination
            start_index = (page - 1) * per_page
            query = query.range(start_index, start_index + per_page - 1)
            
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
            self.logger.exception("Error getting blacklist entries", e)
            return {'items': [], 'page': page, 'per_page': per_page, 'total_items': 0, 'has_more': False}

    def get_total_blacklist_entries_count(self) -> int:
        try:
            # Use admin_client for potentially sensitive counts or if RLS restricts full count for anon
            result = self._get_client(True).table('blacklist_entry').select('id', count='exact').execute()
            return result.count if hasattr(result, 'count') and result.count is not None else 0
        except Exception as e:
            self.logger.exception("Error getting total blacklist entries count", e)
            return 0

    # Admin user operations
    def get_admin_user(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            result = self._get_client(True).table('admin_user').select('*').eq('username', username).execute()
            users = result.data
            return users[0] if users else None
        except Exception as e:
            self.logger.exception(f"Error getting admin user for username {username}", e, 
                                extra={'username': username})
            return None

    def get_admin_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = self._get_client(True).table('admin_user').select('*').eq('id', user_id).execute()
            users = result.data
            return users[0] if users else None
        except Exception as e:
            self.logger.exception(f"Error getting admin user by ID {user_id}", e, 
                                extra={'user_id': user_id})
            return None

    def create_admin_user(self, username: str, password_hash: str, role: str) -> bool:
        try:
            data = {
                'username': username,
                'password_hash': password_hash,
                'role': role
            }
            result = self._get_client(True).table('admin_user').insert(data).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception(f"Error creating admin user for username {username}", e, 
                                extra={'username': username})
            return False

    def get_all_admin_users(self) -> List[Dict[str, Any]]:
        try:
            result = self._get_client(True).table('admin_user').select('*').order('username').execute()
            return result.data
        except Exception as e:
            self.logger.exception("Error getting all admin users", e)
            return []

    def delete_admin_user(self, user_id: int) -> bool:
        try:
            result = self._get_client(True).table('admin_user').delete().eq('id', user_id).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception(f"Error deleting admin user for ID {user_id}", e, 
                                extra={'user_id': user_id})
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
            result = self._get_client(True).table('audit_log').insert(data).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception("Error adding audit log", e)
            return False

    def get_audit_logs(self, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        try:
            query = self._get_client(True).table('audit_log').select('*', count='exact')
            
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
            self.logger.exception("Error getting audit logs", e)
            return {'items': [], 'page': page, 'per_page': per_page, 'total_items': 0, 'has_more': False}

    # Check Log Operations
    def add_check_log(self, check_source: str) -> bool:
        try:
            data = {
                'timestamp': datetime.utcnow().isoformat(),
                'check_source': check_source 
            }
            result = self._get_client(True).table('check_log').insert(data).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception("Error adding check log", e)
            return False

    def count_total_checks(self) -> int:
        try:
            result = self._get_client(True).table('check_log').select('id', count='exact').execute()
            return result.count if hasattr(result, 'count') and result.count is not None else 0
        except Exception as e:
            self.logger.exception("Error counting total checks", e)
            return 0

    def count_checks_last_24_hours(self) -> int:
        try:
            # Ensure created_at column is timestamptz for proper timezone handling with now()
            time_24_hours_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            result = self._get_client(True).table('check_log') \
                         .select('id', count='exact') \
                         .gte('timestamp', time_24_hours_ago) \
                         .execute()
            return result.count if hasattr(result, 'count') and result.count is not None else 0
        except Exception as e:
            self.logger.exception("Error counting checks in last 24 hours", e)
            return 0

    # NEW STATISTICS FUNCTIONS
    def get_blacklist_entries_by_month(self, num_months: int = 12) -> List[Dict[str, Any]]:
        try:
            result = self._get_client(True).rpc('get_monthly_blacklist_counts', {'last_n_months': num_months}).execute()
            if result.data:
                # Ensure data is sorted by month ascending for charting
                return sorted(result.data, key=lambda x: x['month'])
            return []
        except Exception as e:
            self.logger.exception("Error getting blacklist entries by month", e)
            return []

    def get_top_n_reasons(self, n: int = 5) -> List[Dict[str, Any]]:
        try:
            result = self._get_client(True).rpc('get_top_reasons', {'limit_count': n}).execute()
            return result.data if result.data else []
        except Exception as e:
            self.logger.exception("Error getting top N reasons", e)
            return []

    def get_unique_player_count_in_blacklist(self) -> int:
        try:
            result = self._get_client(True).rpc('count_unique_blacklist_uuids', {}).execute()
            return result.data if result.data is not None else 0
        except Exception as e:
            self.logger.exception("Error getting unique player count in blacklist", e)
            return 0
            
    def get_latest_n_blacklist_entries(self, n: int = 5) -> List[Dict[str, Any]]:
        try:
            result = self._get_client().table('blacklist_entry') \
                .select('*') \
                .order('created_at', desc=True) \
                .limit(n) \
                .execute()
            return result.data if result.data else []
        except Exception as e:
            self.logger.exception("Error getting latest N blacklist entries", e)
            return []

    # Whitelist Operations
    def get_all_whitelist_entries(self) -> List[Dict[str, Any]]:
        try:
            result = self._get_client().table('whitelist_players').select('id, uuid, added_by, created_at').order('created_at', desc=True).execute()
            return result.data if result.data else []
        except Exception as e:
            self.logger.exception("Error getting all whitelist entries", e)
            return []

    def get_all_whitelisted_uuids(self) -> List[str]:
        try:
            # Optimized to fetch only UUIDs if that's all that's needed by the mod
            result = self._get_client().table('whitelist_players').select('uuid').execute()
            return [item['uuid'] for item in result.data] if result.data else []
        except Exception as e:
            self.logger.exception("Error getting all whitelisted UUIDs", e)
            return []

    def is_whitelisted(self, uuid_to_check: str) -> bool:
        try:
            result = self._get_client().table('whitelist_players').select('uuid').eq('uuid', uuid_to_check).limit(1).execute()
            return bool(result.data)
        except Exception as e:
            self.logger.exception(f"Error checking if UUID is whitelisted for {uuid_to_check}", e)
            return False

    def add_to_whitelist(self, uuid_to_add: str, added_by: Optional[str] = None) -> bool:
        try:
            data = {'uuid': uuid_to_add, 'added_by': added_by}
            # Use admin_client for whitelist modifications
            result = self._get_client(True).table('whitelist_players').insert(data).execute()
            return bool(result.data)
        except Exception as e:
            # Could be a duplicate UUID violation (UNIQUE constraint on uuid column)
            if 'duplicate key value violates unique constraint' in str(e).lower():
                self.logger.warning(f"Attempted to add duplicate UUID to whitelist: {uuid_to_add}")
            else:
                self.logger.error(f"Error adding UUID to whitelist: {e}")
            return False

    def remove_from_whitelist(self, uuid_to_remove: str) -> bool:
        try:
            result = self._get_client(True).table('whitelist_players').delete().eq('uuid', uuid_to_remove).execute()
            return bool(result.data) 
        except Exception as e:
            self.logger.error(f"Error removing UUID from whitelist: {e}")
            return False

# Create a global instance
db = SupabaseClient() 