from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in erpnext_eta/__init__.py
from erpnext_eta import __version__ as version

setup(
    name="erpnext_eta",
    version=version,
    description="Integration for Egyptian Tax Authority",
    author="Axentor, LLC",
    author_email="apps@axentor.co",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
