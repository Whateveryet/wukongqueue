# -*- coding: utf-8 -*-

from os import path

from setuptools import setup, find_packages

from wukongqueue import __version__

DIR = path.dirname(path.abspath(__file__))

with open(path.join(DIR, "README.md")) as f:
    README = f.read()

setup(
    name="wukongqueue",
    packages=find_packages(),
    version=__version__,
    author="chaseSpace",
    author_email="randomlilei@gmail.com",
    description="A lightweight and convenient cross process FIFO queue service based on TCP protocol.",
    keywords="cross process queue",
    url="https://github.com/chaseSpace/WukongQueue",
    long_description=README,
    long_description_content_type="text/markdown",
    # str or list of strings
    install_requires=[],
    tests_require=["unittest"],
    package_data={},
    include_package_data=True,
    python_requires=">=3.5",
)
