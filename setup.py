# orion/setup.py
"""
setup.py for orion cli tool
"""
from setuptools import setup, find_packages

setup(
    name='orion',
    use_scm_version={
        'version_scheme': 'no-guess-dev',
        'local_scheme': 'dirty-tag',
    },
    setup_requires=['setuptools_scm'],
    py_modules=['main', 'version'],
    install_requires=[
        'click',
        'setuptools_scm>=6.2',
    ],
    entry_points={
        'console_scripts': [
            'orion = main:main',
        ],
    },
    packages=find_packages(),
    license="MIT",
    classifiers=[
        'Programming Language :: Python :: 3.11',
        'Operating System :: OS Independent',
    ],
)
