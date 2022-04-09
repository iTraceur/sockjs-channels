import re
from pathlib import Path

from setuptools import find_packages, setup


def read(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_version():
    init_py = Path("sockjs/__init__.py").read_text()
    return re.search(r"__version__\W*=\W*['\"]([[\d.]+)['\"]", init_py).group(1)


def get_requirements():
    return [line.strip() for line in read("requirements.txt").splitlines() if not line.startswith("#")]


def get_long_description():
    readme = read('README.md')
    try:
        return "\n\n".join((read("README.md"), read("CHANGELOG.md")))
    except IOError:
        return readme


setup(
    name="sockjs-channels",
    version=get_version(),
    url="https://github.com/iTraceur/sockjs-channels",
    author="iTraceur",
    author_email="iTraceur.cn@gmail.com",
    description="WebSocket emulation - SockJS server implementation for Django Channels.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    license="MIT License",
    packages=find_packages(exclude=["tests"]),
    include_package_data=True,
    requires=["channels", "django"],
    python_requires=">=3.6.0",
    install_requires=get_requirements(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Framework :: Django",
        "Topic :: Internet :: WWW/HTTP",
    ]
)
