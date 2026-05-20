from setuptools import setup, find_packages

setup(
    name="omen-rgb-linux",
    version="1.0.0",
    description="HP Omen Max Per-key RGB Controller for Linux",
    author="arfelious",
    packages=find_packages(),
    install_requires=[
        "hidapi",
    ],
    entry_points={
        "console_scripts": [
            "omen-cli=src.cli:main",
        ],
    },
)
