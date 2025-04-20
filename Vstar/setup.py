from setuptools import setup

def readme():
    with open('README.rst') as f:
        return f.read()

setup(
    name='vstars',
    version='4.9.8.53',
    description='VStars Python API',
    author='Geodetic Systems Inc.',
    author_email='support@geodetic.com',
    url='https://www.geodetic.com/',
    packages=['vstars'],
    install_requires=[
        "numpy >= 1.19.1"
    ]
    )
