import os

from setuptools import find_packages, setup

base_dir = os.path.abspath(os.path.dirname(__file__))

about = {}

with open(os.path.join(base_dir, 'sockjs', '__version__.py'), 'r', encoding='utf-8') as f:
    exec(f.read(), about)

with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

with open('requirements.txt', 'r', encoding='utf-8') as f:
    requirements = [line.strip() for line in f.read().splitlines() if not line.startswith('#')]

setup(
    name=about['__title__'],
    version=about['__version__'],
    description=about['__description__'],
    author=about['__author__'],
    author_email=about['__author_email__'],
    url=about['__url__'],
    license=about['__license__'],
    long_description=readme,
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=["tests"]),
    include_package_data=True,
    requires=["channels", "django"],
    python_requires=">=3.6.0",
    install_requires=requirements,
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
