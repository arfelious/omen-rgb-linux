from setuptools import setup, find_packages

setup(
    name="omen-rgb",
    version="1.0.0",
    description="RGB keyboard and lightbar controller for HP OMEN laptops on Linux",
    author="arfelious",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={
        "omen_rgb": ["data/*.json", "assets/*.png"],
    },
    include_package_data=True,
    install_requires=[
        "hidapi>=0.14.0",
    ],
    entry_points={
        "console_scripts": [
            "omen-rgb=omen_rgb.cli:main",
            "omen-rgb-gui=omen_rgb.gui:main",
        ],
    },
)
