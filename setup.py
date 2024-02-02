# orion/setup.py
"""
setup.py for orion cli tool
"""
from setuptools import setup, find_packages


setup(
    name='orion',
    version='1.0',
    py_modules=['orion'],
    install_requires=[
        'click',
        'fmatch'
    ],
    entry_points={
        'console_scripts': [
            'orion = orion:orion',
        ],
    },
    packages=find_packages(),
    package_data={'utils': ['utils.py'],'hunter': ['*.py']},
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
