from setuptools import setup


def readme():
    with open("README.md") as f:
        return f.read()


setup(
    name="aws-excom",
    version="0.0.2",
    description="Wrapper for AWS ECS Execute Command",
    long_description=readme(),
    author="Ben Vosper",
    author_email="ben-vosper@hotmail.com",
    license="MIT",
    packages=["aws_excom"],
    entry_points={
        "console_scripts": ["aws-excom=aws_excom.cli:main"],
    },
    install_requires=[
        "simple-term-menu",
        "termcolor",
        "boto3",
    ],
)
