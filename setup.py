# from distutils.core import setup
from setuptools import setup


setup(
    name="gizmo",
    version="0.1.12",
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
    test_suite="gizmo.tests",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3 :: Only'
    ]
)
