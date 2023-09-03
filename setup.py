from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in erpnext_egypt_compliance/__init__.py
from erpnext_egypt_compliance import __version__ as version

setup(
    name="erpnext_egypt_compliance",
    version=version,
    description="Integration for Egyptian Tax Authority",
    author="Axentor, LLC",
    author_email="apps@axentor.co",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
