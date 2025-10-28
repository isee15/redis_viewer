# PyQt Redis Viewer
Redis 可视化客户端工具（参考 ES Viewer 设计）

一个简单、轻量、跨平台的桌面 GUI，用于浏览与管理 Redis。

该应用使用 Python + PyQt6 构建，提供常用的 Redis 操作：扫描 Key、查看/编辑值、执行命令、查看服务信息。依赖少，便携易用。

---

## ✨ 功能

- 连接灵活
  - Host/Port/DB 选择
  - 支持 SSL/TLS，可选证书校验
  - 支持 ACL 认证（用户名/密码）
- Keys 浏览
  - 按模式扫描，支持类型过滤与分页（Next ▶）
  - Keys 列表右键菜单：打开/复制/TTL/Expire/删除
- Key 编辑器（常见类型）
  - string、hash、list、set、zset
  - Get/Set/Delete/TTL/Expire
- 命令控制台
  - 常用操作（INFO、DBSIZE、CLIENT LIST 等）
  - 执行自定义 Redis 命令（Ctrl+Enter）
- 结果展示
  - JSON 文本 与 树形视图 双模式，可复制
- 会话持久化
  - 保存连接配置与上次扫描模式到本地配置文件

---

## 🛠️ 安装

从 PyPI 安装：

```bash
pip install redis_viewer
```

运行应用：

```bash
redis-viewer
```

### 从源码运行

```bash
pip install PyQt6 redis
python redis_gui.py
```

---

## 🚀 使用说明

1) 连接面板
- 设置 Host、Port、DB
- 按需开启 SSL/TLS，并切换证书校验
- 若需认证，勾选启用后填写用户名/密码
- 点击“🔌 Test”测试连接

2) Keys 标签
- 输入扫描模式（如 *）和类型过滤
- 点击 Scan；使用 Next ▶ 翻页
- 双击 Key 或用右键菜单进行打开/复制/TTL/Expire/删除

3) Key Editor 标签
- 选择类型：string/hash/list/set/zset
- 进行 Get/Set/Delete；查看 TTL 或设置过期秒数
- “Format JSON” 可格式化复杂 JSON 文本

4) Command Console 标签
- 使用常用快捷操作或输入自定义命令
- 点击 Execute 或 Ctrl+Enter 执行

5) 结果视图
- 在 JSON 文本 与 树形视图 间切换；支持右键或 Ctrl+C 复制

---

## ⚙️ 配置

- 配置文件路径：`~/.redis_viewer_config.json`
- 保存连接配置与上次扫描模式
- 注意：密码以明文保存，仅建议在开发/测试环境使用

---

## 📜 许可证

MIT License，见 `LICENSE`。
