import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional
from supabase import Client

class SupabaseHandler(logging.Handler):
    def __init__(self, supabase_client: Client):
        super().__init__()
        self.supabase = supabase_client
        self.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Prepare the log entry
            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'logger_name': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line_number': record.lineno,
            }

            # Add exception info if present
            if record.exc_info:
                log_entry['exception'] = self.formatter.formatException(record.exc_info)

            # Add extra fields if present
            if hasattr(record, 'extra_data'):
                log_entry['extra_data'] = json.dumps(record.extra_data)

            # Insert into Supabase
            self.supabase.table('system_logs').insert(log_entry).execute()

        except Exception as e:
            # Fallback to stderr in case of failure
            import sys
            print(f"Failed to log to Supabase: {e}", file=sys.stderr)

class SupabaseLogger:
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.handler = SupabaseHandler(supabase_client)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(self.handler)
        
        # Create our own logger
        self.logger = logging.getLogger('supabase_logger')
        self.logger.setLevel(logging.INFO)
        
    def _log(self, level: int, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Internal method to handle logging with extra data"""
        if extra:
            # Create a new record with extra data
            record = logging.LogRecord(
                name=self.logger.name,
                level=level,
                pathname=__file__,
                lineno=0,
                msg=message,
                args=(),
                exc_info=None
            )
            record.extra_data = extra
            self.handler.emit(record)
        else:
            # Use standard logging
            self.logger.log(level, message)

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.INFO, message, extra)

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.WARNING, message, extra)

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.ERROR, message, extra)

    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.CRITICAL, message, extra)

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._log(logging.DEBUG, message, extra)

    def exception(self, message: str, exc_info: Optional[Exception] = None, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log an exception with traceback"""
        if extra is None:
            extra = {}
        if exc_info:
            extra['exception'] = str(exc_info)
            extra['traceback'] = logging.Formatter().formatException(
                (type(exc_info), exc_info, exc_info.__traceback__)
            )
        self._log(logging.ERROR, message, extra) 