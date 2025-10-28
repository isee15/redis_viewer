# PyQt Redis Viewer
Redis 可视化客户端工具

A simple, lightweight, cross-platform desktop GUI for browsing and managing Redis.

This app is built with Python and PyQt6. It provides a user-friendly UI for typical Redis operations: scanning keys, viewing/editing values, running commands, and inspecting server info. It is minimal and portable, with few dependencies.

---

## ✨ Features

- Flexible connectivity
  - Host/Port/DB selection
  - SSL/TLS, optional certificate verification
  - ACL authentication (username/password)
- Keys browser
  - Pattern scan with type filter and pagination
  - Keys list with context menu (open/copy/ttl/expire/delete)
- Key editor for common types
  - string, hash, list, set, zset
  - Get/Set/Delete/TTL/Expire
- Command console
  - Quick actions (INFO, DBSIZE, CLIENT LIST, etc.)
  - Execute custom Redis commands (Ctrl+Enter)
- Results display
  - Switch between JSON Text and Tree View, supports copy
- Session persistence
  - Saves connection profiles and last scan pattern to a config file

---

## 🛠️ Installation

Install from PyPI:

```bash
pip install redis-viewer
```

Run the application:

```bash
redis-viewer
```

### Run from source

```bash
pip install PyQt6 redis
python redis_gui.py
```

---

## 🚀 Usage

1) Connection panel
- Set Host, Port, DB
- Enable SSL/TLS (optional), and toggle certificate verification as needed
- Enable Authentication if required and fill in username/password
- Click “🔌 Test” to verify connectivity

2) Keys tab
- Enter a pattern (e.g., *) and optional type filter
- Click Scan; use Next ▶ to paginate results
- Double-click a key or use the context menu to open/copy/ttl/expire/delete

3) Key Editor tab
- Choose type: string/hash/list/set/zset
- Get/Set/Delete the key; check TTL or set Expire seconds
- “Format JSON” helps format JSON text for complex structures

4) Command Console tab
- Use quick actions or type a custom Redis command
- Press Execute or Ctrl+Enter to run

5) Results
- Switch display between JSON Text and Tree View; right-click or Ctrl+C to copy

---

## ⚙️ Configuration

- Config path: `~/.redis_viewer_config.json`
- Stores connection profiles and last scan pattern
- Note: password is saved in plain text; for dev/test use only

---

## 📜 License

MIT License. See `LICENSE`.
