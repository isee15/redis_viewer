# coding: utf-8
"""
A PyQt application to view and manage Redis with common operations,
SSL/auth support, key browsing, and corrected copy functionality.
Author: isee15
Date: 2025-10-28
"""
import sys
import json
import os
import ssl
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QTreeView, QSplitter,
    QStatusBar, QMessageBox, QCheckBox, QFormLayout, QTabWidget, QMenu, QComboBox, QSizePolicy, QListWidget, QGroupBox, QStyle, QHeaderView
)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont, QKeySequence, QAction, QShortcut, QIcon, QPalette, QColor
from PyQt6.QtCore import Qt

# Third-party
try:
    import redis
except ImportError as e:
    redis = None  # Will surface a clear error in UI when used

# --- Config File Path ---
CONFIG_FILE = Path.home() / ".redis_viewer_config.json"


def resource_path(filename: str) -> str:
    """兼容打包后的资源路径"""
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)


# ==============================================================================
#  Business Logic Layer: Simple Redis Client
# ==============================================================================

class SimpleRedisClientError(Exception):
    pass


def _b2s(val: Any) -> Any:
    """Convert Redis bytes to str recursively."""
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return val.decode("utf-8", errors="replace")
    if isinstance(val, list):
        return [_b2s(v) for v in val]
    if isinstance(val, tuple):
        return tuple(_b2s(v) for v in val)
    if isinstance(val, dict):
        return { _b2s(k): _b2s(v) for k, v in val.items() }
    return val


class SimpleRedisClient:
    def __init__(self, host: str, port: int, db: int = 0,
                 username: Optional[str] = None, password: Optional[str] = None,
                 use_ssl: bool = False, verify_ssl: bool = True, timeout: float = 5.0):
        if redis is None:
            raise SimpleRedisClientError("The 'redis' package is not installed. Please install redis>=4.5.")
        ssl_ctx = None
        if use_ssl:
            ssl_ctx = ssl.create_default_context()
            if not verify_ssl:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
        cert_reqs = ssl.CERT_REQUIRED if verify_ssl else ssl.CERT_NONE

        def _try_pool(kwargs, use_ssl_conn: bool = False):
            # Attempt to create a ConnectionPool with provided kwargs, removing unsupported args if necessary
            last_err = None
            # order of attempts: raw kwargs -> drop username -> drop ssl_context -> drop ssl_cert_reqs
            attempts = []
            if use_ssl_conn:
                # Use legacy SSLConnection class if available
                SSLConnection = getattr(getattr(redis, 'connection', redis), 'SSLConnection', None)
                if SSLConnection is None:
                    raise SimpleRedisClientError("This redis-py version does not support SSLConnection. Please upgrade 'redis' package.")
                kwargs_conn = dict(kwargs)
                kwargs_conn['connection_class'] = SSLConnection
                attempts.append(kwargs_conn)
                # progressively remove possibly unsupported kwargs
                for drop in [('username',), ('ssl_context',), ('ssl_cert_reqs',)]:
                    k = dict(kwargs_conn)
                    for d in drop:
                        k.pop(d, None)
                    attempts.append(k)
            else:
                attempts.append(dict(kwargs))
                # progressively remove
                for drop in [('username',), ('ssl_context',), ('ssl_cert_reqs',), ('ssl',)]:
                    k = dict(kwargs)
                    for d in drop:
                        k.pop(d, None)
                    attempts.append(k)
            for a in attempts:
                try:
                    return redis.ConnectionPool(**a)
                except TypeError as te:
                    last_err = te
                    continue
            raise last_err  # type: ignore[misc]

        try:
            base_kwargs = dict(
                host=host,
                port=port,
                db=db,
                socket_timeout=timeout,
                decode_responses=False,
            )
            if password:
                base_kwargs['password'] = password
            if username:
                base_kwargs['username'] = username
            if use_ssl:
                base_kwargs['ssl'] = True
                base_kwargs['ssl_cert_reqs'] = cert_reqs
                if ssl_ctx is not None:
                    base_kwargs['ssl_context'] = ssl_ctx

            try:
                # Try modern API first
                self.pool = _try_pool(base_kwargs, use_ssl_conn=False)
            except TypeError as te:
                # Fallback to SSLConnection path if SSL kw not supported
                if use_ssl and ('ssl' in str(te) or 'ssl_context' in str(te)):
                    self.pool = _try_pool(base_kwargs, use_ssl_conn=True)
                else:
                    raise
            self.client = redis.Redis(connection_pool=self.pool)
        except Exception as e:
            raise SimpleRedisClientError(f"Failed to initialize Redis client: {e}")

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def info(self) -> Dict[str, Any]:
        try:
            return _b2s(self.client.info())
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def dbsize(self) -> int:
        try:
            return int(self.client.dbsize())
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def ttl(self, key: str) -> int:
        try:
            return int(self.client.ttl(key))
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def expire(self, key: str, seconds: int) -> bool:
        try:
            return bool(self.client.expire(key, seconds))
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def delete(self, key: str) -> int:
        try:
            return int(self.client.delete(key))
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def type(self, key: str) -> str:
        try:
            return _b2s(self.client.type(key))  # returns bytes or str depending on version
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def get_value(self, key: str, max_items: int = 200):
        try:
            t = self.type(key)
            t = t.decode("utf-8") if isinstance(t, bytes) else t
            if t == "string":
                val = self.client.get(key)
                sval = _b2s(val)
                # try parse json
                try:
                    return {"type": t, "key": key, "value": json.loads(sval)} if isinstance(sval, str) else {"type": t, "key": key, "value": sval}
                except Exception:
                    return {"type": t, "key": key, "value": sval}
            elif t == "hash":
                return {"type": t, "key": key, "value": _b2s(self.client.hgetall(key))}
            elif t == "list":
                return {"type": t, "key": key, "value": _b2s(self.client.lrange(key, 0, max_items - 1))}
            elif t == "set":
                return {"type": t, "key": key, "value": sorted(_b2s(list(self.client.smembers(key))))}
            elif t == "zset":
                data = self.client.zrange(key, 0, max_items - 1, withscores=True)
                return {"type": t, "key": key, "value": [[_b2s(k), float(s)] for k, s in data]}
            elif t == "stream":
                # Show a small range
                return {"type": t, "key": key, "value": _b2s(self.client.xrange(key, count=max_items))}
            elif t == "none":
                return {"type": t, "key": key, "value": None}
            else:
                # Fallback generic
                val = self.client.get(key)
                return {"type": t, "key": key, "value": _b2s(val)}
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def set_value(self, key: str, value_text: str, value_type: str = "string") -> Dict[str, Any]:
        try:
            vt = value_type.lower()
            if vt == "string":
                # allow plain text or JSON
                # if JSON, we store original string text
                self.client.set(key, value_text.encode("utf-8"))
                return {"acknowledged": True, "operation": "SET", "key": key}
            elif vt == "hash":
                data = json.loads(value_text)
                if not isinstance(data, dict):
                    raise ValueError("Hash value must be a JSON object")
                # HMSET is deprecated; use HSET with mapping
                self.client.hset(key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()})
                return {"acknowledged": True, "operation": "HSET", "key": key, "fields": len(data)}
            elif vt == "list":
                data = json.loads(value_text)
                if not isinstance(data, list):
                    raise ValueError("List value must be a JSON array")
                if data:
                    # replace existing
                    self.client.delete(key)
                    self.client.rpush(key, *[json.dumps(v) if isinstance(v, (dict, list)) else str(v) for v in data])
                return {"acknowledged": True, "operation": "RPUSH", "key": key, "length": len(data)}
            elif vt == "set":
                data = json.loads(value_text)
                if not isinstance(data, list):
                    raise ValueError("Set value must be a JSON array")
                if data:
                    self.client.delete(key)
                    self.client.sadd(key, *[json.dumps(v) if isinstance(v, (dict, list)) else str(v) for v in data])
                return {"acknowledged": True, "operation": "SADD", "key": key, "length": len(data)}
            elif vt == "zset":
                data = json.loads(value_text)
                # Accept array of {"member":..., "score":...} or [[member, score], ...]
                pairs: List[Tuple[str, float]] = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            pairs.append((json.dumps(item.get("member")) if isinstance(item.get("member"), (dict, list)) else str(item.get("member")), float(item.get("score", 0))))
                        else:
                            member, score = item
                            pairs.append((json.dumps(member) if isinstance(member, (dict, list)) else str(member), float(score)))
                else:
                    raise ValueError("ZSet value must be an array of pairs or objects")
                if pairs:
                    self.client.delete(key)
                    self.client.zadd(key, {m: s for m, s in pairs})
                return {"acknowledged": True, "operation": "ZADD", "key": key, "length": len(pairs)}
            else:
                raise ValueError(f"Unsupported type: {value_type}")
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def scan(self, pattern: str = "*", type_filter: Optional[str] = None, count: int = 100) -> List[str]:
        try:
            cursor = 0
            keys: List[str] = []
            # Use low-level scan to support type filter where available
            while True:
                if type_filter and type_filter.lower() != "all":
                    cursor, batch = self.client.scan(cursor=cursor, match=pattern, count=count, _type=type_filter)
                else:
                    cursor, batch = self.client.scan(cursor=cursor, match=pattern, count=count)
                keys.extend([_b2s(k) for k in batch])
                if cursor == 0 or len(keys) >= count:
                    break
            return keys[:count]
        except TypeError:
            # Older redis servers don't support TYPE in SCAN
            try:
                cursor = 0
                keys: List[str] = []
                while True:
                    cursor, batch = self.client.scan(cursor=cursor, match=pattern, count=count)
                    keys.extend([_b2s(k) for k in batch])
                    if cursor == 0 or len(keys) >= count:
                        break
                if type_filter and type_filter.lower() != "all":
                    # post-filter by TYPE
                    filtered = []
                    for k in keys:
                        try:
                            if self.type(k) == type_filter:
                                filtered.append(k)
                        except Exception:
                            pass
                    return filtered[:count]
                return keys[:count]
            except Exception as e:
                raise SimpleRedisClientError(str(e))
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def scan_with_cursor(self, pattern: str = "*", type_filter: Optional[str] = None, count: int = 100, cursor: int = 0) -> Tuple[List[str], int]:
        try:
            keys: List[str] = []
            next_cursor = cursor
            while len(keys) < count:
                if type_filter and type_filter.lower() != "all":
                    next_cursor, batch = self.client.scan(cursor=next_cursor, match=pattern, count=count, _type=type_filter)
                else:
                    next_cursor, batch = self.client.scan(cursor=next_cursor, match=pattern, count=count)
                keys.extend([_b2s(k) for k in batch])
                if next_cursor == 0:
                    break
            return keys[:count], int(next_cursor)
        except TypeError:
            # Fallback for servers without TYPE support in SCAN
            try:
                keys: List[str] = []
                next_cursor = cursor
                while len(keys) < count:
                    next_cursor, batch = self.client.scan(cursor=next_cursor, match=pattern, count=count)
                    batch_keys = [_b2s(k) for k in batch]
                    if type_filter and type_filter.lower() != "all":
                        for k in batch_keys:
                            try:
                                if self.type(k) == type_filter:
                                    keys.append(k)
                            except Exception:
                                pass
                    else:
                        keys.extend(batch_keys)
                    if next_cursor == 0:
                        break
                return keys[:count], int(next_cursor)
            except Exception as e:
                raise SimpleRedisClientError(str(e))
        except Exception as e:
            raise SimpleRedisClientError(str(e))

    def custom(self, parts: List[str]):
        try:
            # Execute arbitrary command
            cmd = parts[0]
            args = parts[1:]
            res = self.client.execute_command(cmd, *args)
            return _b2s(res)
        except Exception as e:
            raise SimpleRedisClientError(str(e))


# ==============================================================================
#  UI Presentation Layer: PyQt Application
# ==============================================================================

class RedisViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.redis_client: Optional[SimpleRedisClient] = None
        self.connections: List[Dict[str, Any]] = []
        # pagination state
        self._scan_cursor: int = 0
        self._last_scan_params: Dict[str, Any] = {"pattern": "*", "type": "All", "count": 100}
        self._keys_all: List[str] = []
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle('Redis Viewer v0.1.0 (by 乖猫记账)')
        self.setGeometry(100, 100, 1280, 720)
        self.setMinimumSize(1024, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Connection group (as group box for better visual separation)
        connection_group = QGroupBox("Connection")
        connection_layout = QFormLayout(connection_group)
        connection_layout.setContentsMargins(10, 8, 10, 8)
        connection_layout.setSpacing(6)

        connection_management_layout = QHBoxLayout()
        self.connection_combo = QComboBox()
        self.connection_combo.setEditable(True)
        self.connection_combo.setPlaceholderText("Enter new connection name or select existing")
        self.save_connection_button = QPushButton("Save")
        self.delete_connection_button = QPushButton("Delete")
        self.test_connection_button = QPushButton("Test")
        # Standard icons (consistent with OS theme)
        self.save_connection_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.delete_connection_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.test_connection_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        connection_management_layout.addWidget(QLabel("Connection:"))
        connection_management_layout.addWidget(self.connection_combo, 1)
        connection_management_layout.addWidget(self.save_connection_button)
        connection_management_layout.addWidget(self.delete_connection_button)
        connection_management_layout.addWidget(self.test_connection_button)
        # Theme chooser on the far right
        connection_management_layout.addStretch(1)
        theme_label = QLabel("Theme:")
        self.theme_combo = QComboBox(); self.theme_combo.addItems(["System", "Light", "Dark"])
        connection_management_layout.addWidget(theme_label)
        connection_management_layout.addWidget(self.theme_combo)
        connection_layout.addRow(connection_management_layout)

        self.host_input = QLineEdit()
        self.port_input = QLineEdit()
        self.db_input = QLineEdit()
        self.db_input.setPlaceholderText("0")
        self.host_input.setPlaceholderText("localhost")
        self.port_input.setPlaceholderText("6379")
        connection_layout.addRow('Host:', self.host_input)
        connection_layout.addRow('Port:', self.port_input)
        connection_layout.addRow('DB:', self.db_input)

        https_layout = QHBoxLayout()
        self.https_checkbox = QCheckBox('Use SSL/TLS')
        self.verify_ssl_checkbox = QCheckBox('Verify SSL Certificate')
        https_layout.addWidget(self.https_checkbox)
        https_layout.addWidget(self.verify_ssl_checkbox)
        https_layout.addStretch(1)
        connection_layout.addRow(https_layout)

        self.auth_checkbox = QCheckBox('Enable Authentication (ACL)')
        connection_layout.addRow(self.auth_checkbox)
        self.user_label = QLabel('Username:')
        self.user_input = QLineEdit()
        self.pass_label = QLabel('Password:')
        self.pass_input = QLineEdit(); self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        connection_layout.addRow(self.user_label, self.user_input)
        connection_layout.addRow(self.pass_label, self.pass_input)
        self.user_label.hide(); self.user_input.hide(); self.pass_label.hide(); self.pass_input.hide()

        self.auth_checkbox.toggled.connect(self.toggle_auth_fields)
        self.https_checkbox.toggled.connect(self.toggle_ssl_verify_option)
        self.connection_combo.activated.connect(self.load_selected_connection)
        self.save_connection_button.clicked.connect(self.save_connection)
        self.delete_connection_button.clicked.connect(self.delete_connection)
        self.test_connection_button.clicked.connect(self.test_connection)

        main_layout.addWidget(connection_group)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left tabs
        self.tabs = QTabWidget()
        self.tab_keys = QWidget()
        self.tab_editor = QWidget()
        self.tab_console = QWidget()
        self.tab_server = QWidget()

        self.tabs.addTab(self.tab_keys, "🔍 Keys")
        self.tabs.addTab(self.tab_editor, "📝 Key Editor")
        self.tabs.addTab(self.tab_console, "🚀 Command Console")
        self.tabs.addTab(self.tab_server, "📊 Server")
        # Set consistent tab icons
        try:
            self.tabs.setTabIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            self.tabs.setTabIcon(1, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
            self.tabs.setTabIcon(2, self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.tabs.setTabIcon(3, self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        except Exception:
            pass

        # --- Keys Tab ---
        keys_layout = QVBoxLayout(self.tab_keys)
        keys_layout.setContentsMargins(10, 10, 10, 10)
        keys_layout.setSpacing(8)
        pattern_layout = QHBoxLayout()
        self.pattern_input = QLineEdit("*")
        self.count_input = QLineEdit("100")
        self.type_combo = QComboBox(); self.type_combo.addItems(["All", "string", "hash", "list", "set", "zset", "stream"])
        self.scan_button = QPushButton('Scan')
        self.scan_next_button = QPushButton('Next ▶')
        self.scan_next_button.setEnabled(False)
        self.scan_status_label = QLabel('Cursor: 0')
        for w in [QLabel("Pattern:"), self.pattern_input, QLabel("Type:"), self.type_combo, QLabel("Count:"), self.count_input, self.scan_button, self.scan_next_button, self.scan_status_label]:
            pattern_layout.addWidget(w)
        pattern_layout.addStretch()
        # Group box for keys area
        keys_box = QGroupBox("Keys")
        keys_box_layout = QVBoxLayout(keys_box)
        keys_box_layout.setContentsMargins(10, 8, 10, 8)
        keys_box_layout.addLayout(pattern_layout)
        # Inline filter for keys list
        filter_layout = QHBoxLayout()
        self.keys_filter_input = QLineEdit(); self.keys_filter_input.setPlaceholderText("Filter keys (supports substring)")
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.keys_filter_input)
        keys_box_layout.addLayout(filter_layout)
        self.keys_list = QListWidget()
        self.keys_list.setAlternatingRowColors(True)
        keys_box_layout.addWidget(self.keys_list)
        keys_layout.addWidget(keys_box)
        self.scan_button.clicked.connect(self.execute_scan)
        self.scan_next_button.clicked.connect(self.execute_scan_next)
        self.keys_list.itemDoubleClicked.connect(self.open_key_from_list)
        self.keys_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.keys_list.customContextMenuRequested.connect(self.open_keys_list_menu)
        self.keys_filter_input.textChanged.connect(self.filter_keys_list)

        # --- Key Editor Tab ---
        editor_layout = QVBoxLayout(self.tab_editor)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.setSpacing(8)
        editor_form = QFormLayout()
        self.key_input = QLineEdit(); self.key_input.setPlaceholderText("Enter key")
        self.value_type_combo = QComboBox(); self.value_type_combo.addItems(["string", "hash", "list", "set", "zset"])
        editor_form.addRow("Key:", self.key_input)
        editor_form.addRow("Type:", self.value_type_combo)
        editor_layout.addLayout(editor_form)
        editor_layout.addWidget(QLabel("Value"))
        self.value_text = QTextEdit(); self.value_text.setFont(QFont("Consolas", 10)); self.value_text.setMinimumHeight(120)
        self.value_text.setPlaceholderText("String: plain text or JSON\nHash/List/Set/ZSet: JSON")
        editor_layout.addWidget(self.value_text)
        editor_buttons = QHBoxLayout()
        self.btn_get = QPushButton("Get")
        self.btn_set = QPushButton("Set/Update")
        self.btn_delete = QPushButton("Delete")
        self.btn_ttl = QPushButton("TTL")
        self.expire_seconds = QLineEdit(); self.expire_seconds.setPlaceholderText("Expire seconds")
        self.btn_expire = QPushButton("Expire")
        self.btn_format = QPushButton("Format JSON")
        for b in [self.btn_get, self.btn_set, self.btn_delete, self.btn_ttl, self.expire_seconds, self.btn_expire, self.btn_format]:
            editor_buttons.addWidget(b)
        editor_buttons.addStretch()
        editor_layout.addLayout(editor_buttons)
        for b in [self.btn_get, self.btn_set, self.btn_delete, self.btn_ttl, self.btn_expire, self.btn_format]:
            b.setSizePolicy(b.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Fixed)
        self.btn_get.clicked.connect(self.execute_get_value)
        self.btn_set.clicked.connect(self.execute_set_value)
        self.btn_delete.clicked.connect(self.execute_delete_key)
        self.btn_ttl.clicked.connect(self.execute_ttl)
        self.btn_expire.clicked.connect(self.execute_expire)
        self.btn_format.clicked.connect(self.format_json_value)

        # --- Command Console Tab ---
        console_layout = QVBoxLayout(self.tab_console)
        console_layout.setContentsMargins(10, 10, 10, 10)
        console_layout.setSpacing(8)
        console_form = QFormLayout()
        self.command_input = QLineEdit(); self.command_input.setPlaceholderText("e.g., GET mykey  or  ZRANGE myzset 0 -1 WITHSCORES")
        console_form.addRow("Command:", self.command_input)
        console_layout.addLayout(console_form)
        self.execute_command_button = QPushButton('Execute')
        self.execute_command_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.execute_command_button.setSizePolicy(self.execute_command_button.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Fixed)
        self.execute_command_button.clicked.connect(self.execute_custom_command)
        console_layout.addWidget(self.execute_command_button, 0, Qt.AlignmentFlag.AlignRight)
        self.command_input.returnPressed.connect(self.execute_custom_command)
        QShortcut(QKeySequence("Ctrl+Return"), self.tab_console, activated=self.execute_custom_command)
        QShortcut(QKeySequence("Ctrl+Enter"), self.tab_console, activated=self.execute_custom_command)

        # --- Server Tab ---
        server_layout = QVBoxLayout(self.tab_server)
        server_layout.setContentsMargins(10, 10, 10, 10)
        server_layout.setSpacing(8)
        server_layout.addWidget(QLabel("<b>Common Operations</b> (Double-click to run)"))
        self.quick_query_tree = QTreeView()
        self.quick_query_tree.setHeaderHidden(True)
        quick_query_model = QStandardItemModel(); self.quick_query_tree.setModel(quick_query_model)
        self.populate_quick_query_tree(quick_query_model)
        self.quick_query_tree.expandAll()
        self.quick_query_tree.doubleClicked.connect(self.execute_quick_query)
        server_layout.addWidget(self.quick_query_tree)

        # Results panel (as group box)
        results_box = QGroupBox("Results")
        results_layout = QVBoxLayout(results_box)
        results_layout.setContentsMargins(10, 8, 10, 8)

        display_toggle_layout = QHBoxLayout()
        display_toggle_layout.addWidget(QLabel("Results:")); display_toggle_layout.addStretch()
        self.view_mode_combo = QComboBox(); self.view_mode_combo.addItems(["JSON Text", "Tree View"])  
        self.view_mode_combo.currentTextChanged.connect(self.toggle_display_mode)
        display_toggle_layout.addWidget(QLabel("Display Mode:")); display_toggle_layout.addWidget(self.view_mode_combo)
        # Add copy actions
        self.copy_json_btn = QPushButton("Copy JSON")
        self.copy_value_btn = QPushButton("Copy Value")
        self.copy_json_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.copy_value_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogToParent))
        self.copy_json_btn.setToolTip("Copy full JSON (Ctrl+Shift+C)")
        self.copy_value_btn.setToolTip("Copy only value (Ctrl+Alt+C)")
        display_toggle_layout.addWidget(self.copy_json_btn)
        display_toggle_layout.addWidget(self.copy_value_btn)
        self.copy_json_btn.clicked.connect(self.copy_full_json)
        self.copy_value_btn.clicked.connect(self.copy_value_only)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.copy_full_json)
        QShortcut(QKeySequence("Ctrl+Alt+C"), self, activated=self.copy_value_only)
        results_layout.addLayout(display_toggle_layout)

        self.results_text = QTextEdit(); self.results_text.setFont(QFont("Consolas", 10)); self.results_text.setReadOnly(True)
        results_layout.addWidget(self.results_text)
        self.results_tree = QTreeView(); self.results_tree.hide(); results_layout.addWidget(self.results_tree)
        self.results_tree.setAlternatingRowColors(True)
        self.results_tree.setUniformRowHeights(True)
        try:
            header = self.results_tree.header()
            header.setStretchLastSection(True)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        except Exception:
            pass

        main_splitter.addWidget(self.tabs)
        main_splitter.addWidget(results_box)
        main_splitter.setSizes([560, 720])
        main_layout.addWidget(main_splitter)

        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.setup_copy_functionality()
        # Theme apply
        self.theme_combo.currentTextChanged.connect(self.apply_theme)

        # Add shortcut hints/tooltips
        self.scan_button.setToolTip("Scan (F5)")
        self.scan_next_button.setToolTip("Next page (F6)")
        self.btn_get.setToolTip("Get (F9)")
        self.btn_set.setToolTip("Set/Update (Ctrl+S)")
        self.btn_delete.setToolTip("Delete (Del)")
        self.btn_ttl.setToolTip("TTL (Ctrl+T)")
        self.btn_expire.setToolTip("Expire (Ctrl+E)")
        self.btn_format.setToolTip("Format JSON (Ctrl+Shift+F)")
        self.execute_command_button.setToolTip("Execute (Ctrl+Enter)")
        # Keyboard shortcuts
        QShortcut(QKeySequence("F5"), self, activated=self.execute_scan)
        QShortcut(QKeySequence("F6"), self, activated=self.execute_scan_next)
        QShortcut(QKeySequence("F9"), self, activated=self.execute_get_value)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.execute_set_value)
        QShortcut(QKeySequence("Del"), self, activated=self.execute_delete_key)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.execute_ttl)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.execute_expire)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, activated=self.format_json_value)

    # --- Copy functionality ---
    def setup_copy_functionality(self):
        self.results_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_tree.customContextMenuRequested.connect(self.open_tree_context_menu)
        copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.results_tree)
        copy_shortcut.activated.connect(self.copy_selection_to_clipboard)

    def open_tree_context_menu(self, position):
        index = self.results_tree.indexAt(position)
        if index.isValid():
            menu = QMenu(); copy_action = QAction("Copy", self)
            copy_action.triggered.connect(self.copy_selection_to_clipboard); menu.addAction(copy_action)
            menu.exec(self.results_tree.viewport().mapToGlobal(position))

    def copy_selection_to_clipboard(self):
        selected_indexes = self.results_tree.selectionModel().selectedIndexes()
        if not selected_indexes:
            return
        selected_index = selected_indexes[0]
        model = self.results_tree.model()
        key_index = model.index(selected_index.row(), 0, selected_index.parent())
        key_text = model.data(key_index, Qt.ItemDataRole.DisplayRole)
        value_index = model.index(selected_index.row(), 1, selected_index.parent())
        value_text = model.data(value_index, Qt.ItemDataRole.DisplayRole)
        text_to_copy = f"{key_text}: {value_text}" if value_text else key_text
        if text_to_copy:
            QApplication.clipboard().setText(text_to_copy)
            self.status_bar.showMessage(f"Copied: '{text_to_copy}'", 3000)

    # --- Connection methods ---
    def load_selected_connection(self, index):
        if index < 0 or index >= len(self.connections):
            return
        connection_data = self.connections[index]
        self.populate_connection_fields(connection_data)
        self.setWindowTitle(f"Redis Viewer v0.1.0 (by 乖猫记账) - {connection_data['name']}")
        self.status_bar.showMessage(f"Loaded connection '{connection_data['name']}'", 3000)

    def populate_connection_fields(self, data):
        self.host_input.setText(data.get("host", "localhost"))
        self.port_input.setText(data.get("port", "6379"))
        self.db_input.setText(str(data.get("db", "0")))
        self.https_checkbox.setChecked(data.get("ssl_enabled", False))
        self.verify_ssl_checkbox.setChecked(data.get("verify_ssl", True))
        self.toggle_ssl_verify_option(self.https_checkbox.isChecked())
        self.auth_checkbox.setChecked(data.get("auth_enabled", False))
        self.user_input.setText(data.get("username", ""))
        self.pass_input.setText(data.get("password", ""))
        self.toggle_auth_fields(self.auth_checkbox.isChecked())

    def save_connection(self):
        conn_name = self.connection_combo.currentText().strip()
        if not conn_name:
            QMessageBox.warning(self, "Save Error", "Connection name cannot be empty.")
            return
        new_connection = {
            "name": conn_name,
            "host": self.host_input.text(),
            "port": self.port_input.text(),
            "db": self.db_input.text() or "0",
            "ssl_enabled": self.https_checkbox.isChecked(),
            "verify_ssl": self.verify_ssl_checkbox.isChecked(),
            "auth_enabled": self.auth_checkbox.isChecked(),
            "username": self.user_input.text(),
            "password": self.pass_input.text(),
        }
        existing_indices = [i for i, conn in enumerate(self.connections) if conn['name'] == conn_name]
        if existing_indices:
            self.connections[existing_indices[0]] = new_connection
            self.status_bar.showMessage(f"Connection '{conn_name}' updated.", 3000)
        else:
            self.connections.append(new_connection)
            self.connection_combo.addItem(conn_name)
            self.connection_combo.setCurrentText(conn_name)
            self.status_bar.showMessage(f"Connection '{conn_name}' saved.", 3000)
        self.save_settings()

    def delete_connection(self):
        conn_name = self.connection_combo.currentText()
        if not conn_name:
            QMessageBox.warning(self, "Delete Error", "No connection selected to delete.")
            return
        confirm = QMessageBox.question(self, "Confirm Delete",
                                       f"Are you sure you want to delete the connection profile '{conn_name}'?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No:
            return
        self.connections = [conn for conn in self.connections if conn['name'] != conn_name]
        self.connection_combo.clear(); self.connection_combo.addItems([conn['name'] for conn in self.connections])
        if self.connections:
            self.connection_combo.setCurrentIndex(0); self.load_selected_connection(0)
        else:
            self.clear_connection_fields()
        self.status_bar.showMessage(f"Connection '{conn_name}' deleted.", 3000)
        self.save_settings()

    def clear_connection_fields(self):
        self.host_input.clear(); self.port_input.clear(); self.db_input.clear()
        self.https_checkbox.setChecked(False); self.auth_checkbox.setChecked(False)
        self.user_input.clear(); self.pass_input.clear(); self.connection_combo.setCurrentText("")

    def _get_client(self) -> Optional[SimpleRedisClient]:
        host = self.host_input.text().strip(); port = self.port_input.text().strip(); db_txt = self.db_input.text().strip() or "0"
        if not host or not port:
            QMessageBox.warning(self, 'Input Error', 'Host and Port cannot be empty.')
            return None
        try:
            db = int(db_txt)
        except ValueError:
            QMessageBox.warning(self, 'Input Error', 'DB must be an integer.')
            return None
        use_ssl = self.https_checkbox.isChecked(); verify_ssl = self.verify_ssl_checkbox.isChecked()
        username = self.user_input.text().strip() if self.auth_checkbox.isChecked() else None
        password = self.pass_input.text() if self.auth_checkbox.isChecked() else None
        try:
            client = SimpleRedisClient(host=host, port=int(port), db=db,
                                       username=username, password=password,
                                       use_ssl=use_ssl, verify_ssl=verify_ssl)
            # test connection
            if not client.ping():
                QMessageBox.critical(self, 'Connection Error', 'Unable to ping Redis server.')
                return None
            return client
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Connection Error', str(e))
            return None

    def save_settings(self):
        current_conn_name = self.connection_combo.currentText()
        settings = {
            "connections": self.connections,
            "current_connection_name": current_conn_name,
            "pattern": self.pattern_input.text(),
            "theme": self.theme_combo.currentText() if hasattr(self, 'theme_combo') else "System",
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self.status_bar.showMessage(f"Error saving settings: {e}", 5000)

    def load_settings(self):
        if not os.path.exists(CONFIG_FILE):
            default_conn = {
                "name": "default", "host": "localhost", "port": "6379", "db": "0",
                "ssl_enabled": False, "verify_ssl": True, "auth_enabled": False,
                "username": "", "password": ""
            }
            self.connections = [default_conn]
            self.connection_combo.addItems([c['name'] for c in self.connections])
            self.populate_connection_fields(default_conn)
            self.pattern_input.setText("*")
            self.save_settings(); return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            self.connections = settings.get("connections", [])
            current_conn_name = settings.get("current_connection_name")
            self.connection_combo.clear(); self.connection_combo.addItems([c['name'] for c in self.connections])
            if current_conn_name and any(c['name'] == current_conn_name for c in self.connections):
                self.connection_combo.setCurrentText(current_conn_name)
                self.load_selected_connection(self.connection_combo.currentIndex())
            elif self.connections:
                self.connection_combo.setCurrentIndex(0); self.load_selected_connection(0)
            else:
                self.clear_connection_fields()
            self.pattern_input.setText(settings.get("pattern", "*"))
            # restore theme
            theme = settings.get("theme", "System")
            if theme in ["System", "Light", "Dark"]:
                self.theme_combo.setCurrentText(theme)
                self.apply_theme(theme)
        except (IOError, json.JSONDecodeError, KeyError) as e:
            QMessageBox.critical(self, "Load Settings Error", f"Could not load or parse config file: {e}")
            self.clear_connection_fields()

    # --- Actions ---
    def execute_scan(self):
        client = self._get_client()
        if not client:
            return
        pattern = self.pattern_input.text().strip() or "*"
        type_filter = self.type_combo.currentText()
        try:
            count = int(self.count_input.text())
        except ValueError:
            QMessageBox.warning(self, 'Input Error', 'Count must be an integer.')
            return
        try:
            self.status_bar.showMessage(f'Scanning keys pattern "{pattern}"...')
            QApplication.processEvents()
            # reset cursor
            self._scan_cursor = 0
            keys, next_cursor = client.scan_with_cursor(pattern=pattern, type_filter=type_filter if type_filter.lower() != 'all' else None, count=count, cursor=self._scan_cursor)
            self._scan_cursor = next_cursor
            self._last_scan_params = {"pattern": pattern, "type": type_filter, "count": count}
            data = {"pattern": pattern, "type": type_filter, "count": len(keys), "keys": keys, "next_cursor": next_cursor}
            self.populate_tree(data)
            # populate list widget
            self._keys_all = list(keys)
            self.keys_list.clear()
            self.keys_list.addItems(keys)
            # update pagination controls
            self.scan_next_button.setEnabled(next_cursor != 0)
            self.scan_status_label.setText(f'Cursor: {next_cursor}')
            self.status_bar.showMessage('Scan successful. Settings saved.', 5000)
            self.save_settings()
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def execute_scan_next(self):
        client = self._get_client()
        if not client:
            return
        if self._scan_cursor == 0:
            self.status_bar.showMessage('No more results.', 3000)
            self.scan_next_button.setEnabled(False)
            return
        pattern = self._last_scan_params.get("pattern", "*")
        type_filter = self._last_scan_params.get("type", "All")
        count = int(self._last_scan_params.get("count", 100))
        try:
            self.status_bar.showMessage(f'Fetching next keys page...')
            QApplication.processEvents()
            keys, next_cursor = client.scan_with_cursor(pattern=pattern, type_filter=type_filter if str(type_filter).lower() != 'all' else None, count=count, cursor=self._scan_cursor)
            self._scan_cursor = next_cursor
            # append to list widget and cache
            self._keys_all.extend(keys)
            self.keys_list.addItems(keys)
            # show in results pane as page
            data = {"pattern": pattern, "type": type_filter, "page_size": len(keys), "next_cursor": next_cursor, "keys_page": keys}
            self.populate_tree(data)
            self.scan_next_button.setEnabled(next_cursor != 0)
            self.scan_status_label.setText(f'Cursor: {next_cursor}')
            if next_cursor == 0:
                self.status_bar.showMessage('Reached end of scan.', 4000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def execute_get_value(self):
        client = self._get_client()
        if not client:
            return
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, 'Input Error', 'Key is required.')
            return
        try:
            self.status_bar.showMessage(f"Getting key '{key}'...")
            data = client.get_value(key)
            self.populate_tree(data)
            # Update type combo based on actual type
            if isinstance(data, dict) and data.get("type"):
                idx = self.value_type_combo.findText(data["type"]) 
                if idx >= 0:
                    self.value_type_combo.setCurrentIndex(idx)
            # Put pretty value for string/hash/etc.
            val = data.get("value") if isinstance(data, dict) else None
            if isinstance(val, (dict, list)):
                self.value_text.setPlainText(json.dumps(val, indent=2, ensure_ascii=False))
            elif val is None:
                self.value_text.clear()
            else:
                self.value_text.setPlainText(str(val))
            self.status_bar.showMessage('Get successful.', 5000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def execute_set_value(self):
        client = self._get_client()
        if not client:
            return
        key = self.key_input.text().strip(); vtype = self.value_type_combo.currentText()
        if not key:
            QMessageBox.warning(self, 'Input Error', 'Key is required.')
            return
        value_text = self.value_text.toPlainText()
        try:
            self.status_bar.showMessage(f"Setting key '{key}'...")
            res = client.set_value(key, value_text, vtype)
            self.populate_tree(res)
            self.status_bar.showMessage('Set successful.', 5000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def execute_delete_key(self):
        client = self._get_client()
        if not client:
            return
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, 'Input Error', 'Key is required.')
            return
        confirm = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to delete key '{key}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No:
            return
        try:
            self.status_bar.showMessage(f"Deleting key '{key}'...")
            deleted = client.delete(key)
            self.populate_tree({"deleted": deleted, "key": key})
            if deleted:
                self.value_text.clear()
            self.status_bar.showMessage('Delete operation completed.', 5000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def execute_ttl(self):
        client = self._get_client()
        if not client:
            return
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, 'Input Error', 'Key is required.')
            return
        try:
            t = client.ttl(key)
            self.populate_tree({"key": key, "ttl": t})
            self.status_bar.showMessage('TTL fetched.', 5000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def execute_expire(self):
        client = self._get_client()
        if not client:
            return
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, 'Input Error', 'Key is required.')
            return
        try:
            seconds = int(self.expire_seconds.text())
        except ValueError:
            QMessageBox.warning(self, 'Input Error', 'Expire seconds must be an integer.')
            return
        try:
            ok = client.expire(key, seconds)
            self.populate_tree({"key": key, "expire": seconds, "acknowledged": ok})
            self.status_bar.showMessage('Expire set.', 5000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def execute_custom_command(self):
        client = self._get_client()
        if not client:
            return
        cmdline = self.command_input.text().strip()
        if not cmdline:
            QMessageBox.warning(self, 'Input Error', 'Command cannot be empty.')
            return
        import shlex
        try:
            parts = shlex.split(cmdline)
            self.status_bar.showMessage(f"Executing: {' '.join(parts)}")
            res = client.custom(parts)
            # Normalize to displayable structure
            data = {"command": parts[0], "args": parts[1:], "result": res}
            self.populate_tree(data)
            self.status_bar.showMessage('Command executed.', 5000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))
        except ValueError as e:
            QMessageBox.critical(self, 'Parse Error', str(e))

    def populate_quick_query_tree(self, model: QStandardItemModel):
        root_item = model.invisibleRootItem()
        server_cat = QStandardItem("🌐 Server")
        server_cat.setEditable(False); server_cat.setSelectable(False)
        root_item.appendRow(server_cat)
        for name, op in {
            "INFO": {"op": "info"},
            "DBSIZE": {"op": "dbsize"},
        }.items():
            it = QStandardItem(name); it.setEditable(False); it.setData(op, Qt.ItemDataRole.UserRole)
            server_cat.appendRow(it)

        client_cat = QStandardItem("👥 Client")
        client_cat.setEditable(False); client_cat.setSelectable(False)
        root_item.appendRow(client_cat)
        # We'll implement some via custom commands for simplicity
        for name, cmd in {
            "CLIENT LIST": "CLIENT LIST",
            "SLOWLOG GET 10": "SLOWLOG GET 10",
            "CONFIG GET *": "CONFIG GET *",
        }.items():
            it = QStandardItem(name); it.setEditable(False); it.setData({"cmd": cmd}, Qt.ItemDataRole.UserRole)
            client_cat.appendRow(it)

    def execute_quick_query(self, index):
        item = self.quick_query_tree.model().itemFromIndex(index)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        if "op" in data:
            # direct method
            client = self._get_client()
            if not client:
                return
            try:
                if data["op"] == "info":
                    res = client.info()
                elif data["op"] == "dbsize":
                    res = {"dbsize": client.dbsize()}
                else:
                    res = {"message": "Unknown op"}
                self.populate_tree(res)
                self.status_bar.showMessage('Operation executed.', 5000)
            except SimpleRedisClientError as e:
                QMessageBox.critical(self, 'Client Error', str(e))
        elif "cmd" in data:
            self.command_input.setText(data["cmd"])  # preload to console
            self.tabs.setCurrentWidget(self.tab_console)

    # --- Result display helpers ---
    def populate_tree(self, data: Any):
        model = QStandardItemModel(); model.setHorizontalHeaderLabels(['Key', 'Value'])
        self.results_tree.setModel(model); root_item = model.invisibleRootItem()
        self._populate_tree_model(data, root_item)
        self.results_text.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        # Enable default sorting by key
        try:
            self.results_tree.setSortingEnabled(True)
            self.results_tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        except Exception:
            pass
        self.results_tree.expandToDepth(2)

    def _populate_tree_model(self, data: Any, parent_item: QStandardItem):
        if isinstance(data, dict):
            for key, value in data.items():
                key_item = QStandardItem(str(key)); key_item.setEditable(False)
                value_item = QStandardItem(); value_item.setEditable(False)
                parent_item.appendRow([key_item, value_item])
                if isinstance(value, (dict, list)):
                    self._populate_tree_model(value, key_item)
                else:
                    value_item.setText(str(value))
        elif isinstance(data, list):
            for index, value in enumerate(data):
                index_item = QStandardItem(f"[{index}]"); index_item.setEditable(False)
                value_item = QStandardItem(); value_item.setEditable(False)
                parent_item.appendRow([index_item, value_item])
                if isinstance(value, (dict, list)):
                    self._populate_tree_model(value, index_item)
                else:
                    value_item.setText(str(value))
        else:
            key_item = QStandardItem("value"); key_item.setEditable(False)
            value_item = QStandardItem(str(data)); value_item.setEditable(False)
            parent_item.appendRow([key_item, value_item])

    def toggle_display_mode(self, mode):
        if mode == "JSON Text":
            self.results_tree.hide(); self.results_text.show()
        else:
            self.results_text.hide(); self.results_tree.show()

    def filter_keys_list(self, text: str):
        q = text.strip().lower()
        for i in range(self.keys_list.count()):
            item = self.keys_list.item(i)
            item.setHidden(q not in item.text().lower())

    def copy_full_json(self):
        text = self.results_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status_bar.showMessage('JSON copied.', 2000)

    def copy_value_only(self):
        # Try to extract only the value portion from the last data
        try:
            obj = json.loads(self.results_text.toPlainText() or '{}')
        except Exception:
            obj = {}
        value = None
        # Prefer common keys
        for k in ["value", "result", "keys", "data"]:
            if isinstance(obj, dict) and k in obj:
                value = obj[k]
                break
        if value is None:
            # fallback to current selection's value column
            sel = self.results_tree.selectionModel().selectedIndexes() if self.results_tree.model() else []
            if sel:
                model = self.results_tree.model()
                idx = sel[0]
                value_index = model.index(idx.row(), 1, idx.parent())
                value = model.data(value_index, Qt.ItemDataRole.DisplayRole)
            else:
                value = obj
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            text = str(value)
        if text:
            QApplication.clipboard().setText(text)
            self.status_bar.showMessage('Value copied.', 2000)

    # Theming helpers
    def apply_theme(self, theme: str):
        # Use Fusion for consistent theming
        QApplication.instance().setStyle("Fusion")
        app = QApplication.instance()
        if theme == "Dark":
            palette = QPalette()
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
            palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
            app.setPalette(palette)
            app.setStyleSheet("""
                QGroupBox { font-weight: 600; border: 1px solid #3c3c3c; border-radius: 6px; margin-top: 6px; }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
                QLineEdit, QComboBox, QTextEdit { border: 1px solid #3c3c3c; border-radius: 4px; padding: 4px; }
                QPushButton { padding: 4px 10px; border: 1px solid #3c3c3c; border-radius: 4px; }
                QPushButton:hover { border-color: #2a82da; }
            """)
        elif theme == "Light":
            app.setPalette(QApplication.style().standardPalette())
            app.setStyleSheet("""
                QGroupBox { font-weight: 600; border: 1px solid #e0e0e0; border-radius: 6px; margin-top: 6px; }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
                QLineEdit, QComboBox, QTextEdit { border: 1px solid #d0d0d0; border-radius: 4px; padding: 4px; }
                QPushButton { padding: 4px 10px; border: 1px solid #d0d0d0; border-radius: 4px; }
                QPushButton:hover { border-color: #2a82da; }
            """)
        else:
            # System
            app.setPalette(QApplication.style().standardPalette())
            app.setStyleSheet("")

    # --- Toggles ---
    def toggle_ssl_verify_option(self, checked):
        self.verify_ssl_checkbox.setVisible(checked)

    def toggle_auth_fields(self, checked):
        self.user_label.setVisible(checked); self.user_input.setVisible(checked)
        self.pass_label.setVisible(checked); self.pass_input.setVisible(checked)

    def open_key_from_list(self, item):
        key = item.text()
        self.key_input.setText(key)
        self.tabs.setCurrentWidget(self.tab_editor)
        self.execute_get_value()

    def open_keys_list_menu(self, pos):
        item = self.keys_list.itemAt(pos)
        if not item:
            return
        key = item.text()
        menu = QMenu(self)
        act_open = QAction("Open", self)
        act_copy = QAction("Copy Key", self)
        act_delete = QAction("Delete", self)
        act_ttl = QAction("TTL", self)
        act_expire = QAction("Expire 3600s", self)
        menu.addAction(act_open)
        menu.addAction(act_copy)
        menu.addSeparator()
        menu.addAction(act_ttl)
        menu.addAction(act_expire)
        menu.addSeparator()
        menu.addAction(act_delete)

        def _open():
            self.key_input.setText(key)
            self.tabs.setCurrentWidget(self.tab_editor)
            self.execute_get_value()
        def _copy():
            QApplication.clipboard().setText(key)
            self.status_bar.showMessage("Key copied.", 2000)
        def _delete():
            self.key_input.setText(key)
            self.execute_delete_key()
            # remove item from list if deleted
        def _ttl():
            self.key_input.setText(key)
            self.execute_ttl()
        def _expire():
            self.key_input.setText(key)
            self.expire_seconds.setText("3600")
            self.execute_expire()

        act_open.triggered.connect(_open)
        act_copy.triggered.connect(_copy)
        act_delete.triggered.connect(_delete)
        act_ttl.triggered.connect(_ttl)
        act_expire.triggered.connect(_expire)
        menu.exec(self.keys_list.mapToGlobal(pos))

    def test_connection(self):
        client = self._get_client()
        if not client:
            return
        try:
            info = client.info()
            self.populate_tree({"ping": True, "server": {"redis_version": info.get("redis_version"), "mode": info.get("redis_mode"), "os": info.get("os")}})
            self.status_bar.showMessage('Connection OK.', 4000)
        except SimpleRedisClientError as e:
            QMessageBox.critical(self, 'Client Error', str(e))

    def format_json_value(self):
        text = self.value_text.toPlainText().strip()
        if not text:
            return
        try:
            obj = json.loads(text)
            self.value_text.setPlainText(json.dumps(obj, indent=2, ensure_ascii=False))
            self.status_bar.showMessage('JSON formatted.', 3000)
        except Exception:
            # Not JSON; ignore
            self.status_bar.showMessage('Not valid JSON.', 2000)


def main():
    # Enable HiDPI before creating QApplication
    try:
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    app = QApplication(sys.argv)
    # Set a clean default font
    app.setFont(QFont("Segoe UI", 10))
    viewer = RedisViewer()
    viewer.setWindowIcon(QIcon(resource_path("favicon.ico")))
    # Apply default theme
    viewer.apply_theme("System")
    viewer.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()