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
    python_requires='==3.11',
    setup_requires=['setuptools_scm'],
    py_modules=['main', 'version'],
    install_requires=[
        'click==8.1.7',    
        'setuptools_scm>=6.2',
        'hunter @ git+https://github.com/apache/otava.git@v0.5.0',
        'elastic-transport==8.11.0',
        'opensearch-dsl==2.1.0',
        'opensearch-py==3.0.0',
        'Jinja2==3.1.3',
        'PyYAML==6.0.1',
        'pyshorteners==1.0.1',
        "numpy==1.24.0; python_version=='3.11'",
        'scikit-learn==1.5.0',
        'scipy==1.12.0',
        "pandas==2.3.1; python_version=='3.11'",
        'tabulate==0.8.10',
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
