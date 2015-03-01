# from distutils.core import setup
from setuptools import setup


setup(
    name="gizmo",
    version="0.1.6",
    url="",
    license="MIT",
    author="davebshow",
    author_email="davebshow@gmail.com",
    description="Async Python 3 driver for TP3 Gremlin Server",
    long_description=open("README.txt").read(),
    packages=["gizmo"],
    install_requires=[
        "websockets==2.4"
    ],
    test_suite="gizmo.tests"
)
