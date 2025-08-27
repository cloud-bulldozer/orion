# orion/setup.py
"""
setup.py for orion cli tool
"""
from setuptools import setup, find_packages

setup(
    name='orion',
    version='1.0',
    py_modules=['main'],
    install_requires=[
        'click',
    ],
    entry_points={
        'console_scripts': [
            'orion = main:main',
        ],
    },
    packages=find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
