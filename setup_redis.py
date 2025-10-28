from setuptools import setup

# Optionally read README if exists
long_description = "A lightweight, cross-platform desktop GUI for Redis"
try:
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()
except Exception:
    pass

setup(
    name="redis_viewer",
    version="0.1.1",
    author="乖猫记账",
    author_email="meizhitu@gmail.com",
    description="A lightweight, cross-platform desktop GUI for Redis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/isee15/redis_viewer",
    py_modules=["redis_gui"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Database :: Front-Ends",
        "Environment :: X11 Applications :: Qt",
    ],
    python_requires='>=3.8',
    install_requires=[
        "PyQt6",
        "redis>=4.5",
    ],
    entry_points={
        "gui_scripts": [
            "redis-viewer = redis_gui:main",
        ],
    },
)
