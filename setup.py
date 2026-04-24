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
    python_requires='>=3.11,<3.15',
    setup_requires=['setuptools_scm'],
    py_modules=['main', 'version'],
    install_requires=[
        'click==8.1.7',
        'setuptools_scm>=6.2',
        "apache-otava @ \
        git+https://github.com/vishnuchalla/otava.git@f1a2c67561fbc32f8fe11c2fd5e1de57b61e42de",
        'elastic-transport==8.11.0',
        'opensearch-dsl==2.1.0',
        'opensearch-py==3.0.0',
        'Jinja2==3.1.3',
        'PyYAML==6.0.1',
        'pyshorteners==1.0.1',
        "numpy==2.3.5; python_version=='3.14'",
        'scikit-learn==1.5.0',
        "pandas==2.3.3; python_version=='3.14'",
        'tabulate==0.9.0',
        'plotly>=5.18.0',
    ],
    entry_points={
        'console_scripts': [
            'orion = main:main',
        ],
    },
    packages=find_packages(),
    license="MIT",
    classifiers=[
        'Programming Language :: Python :: 3.14',
        'Operating System :: OS Independent',
    ],
)
