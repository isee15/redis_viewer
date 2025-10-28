# Redis-Viewer 打包、上传与使用说明

本文档描述如何将 `redis_viewer` 包打包并上传到 PyPI，以及用户如何通过 `pip` 安装和使用 `redis-viewer` 桌面应用。

---

## 1. 环境准备

确保已安装 Python，并准备好 PyPI 账户。

### 安装打包工具

```bash
pip install setuptools wheel twine
```

---

## 2. 打包项目

本项目使用 `setup_redis.py` 进行打包。

在项目根目录执行：

```bash
python setup_redis.py sdist bdist_wheel
```

执行完成后，生成的文件位于 `dist/` 目录，例如：
- `redis_viewer-0.1.0.tar.gz`
- `redis_viewer-0.1.0-py3-none-any.whl`

---

## 3. 上传到 PyPI

```bash
twine upload dist/*
```

> 建议先上传到 TestPyPI 进行验证：
>
> ```bash
> twine upload --repository testpypi dist/*
> pip install --index-url https://test.pypi.org/simple/ redis_viewer
> ```

---

## 4. 用户安装与使用

通过 pip 安装：

```bash
pip install redis_viewer
```

安装后可直接运行桌面应用：

```bash
redis-viewer
```

等效于在源码中运行：

```bash
python redis_gui.py
```

---

## 5. 可执行文件打包（本地）

Windows（需已安装 PyInstaller）：

```bash
pyinstaller --name RedisViewer --onefile --windowed --icon=favicon.ico --add-data "favicon.ico;." redis_gui.py
```

macOS 参考 .github/workflows/build-dmg-release.yml 中的流程生成 .app 与 .dmg。
