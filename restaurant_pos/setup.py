from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="restaurant_pos",
    version="1.0.0",
    description="Restaurant-grade POS system for ERPNext",
    author="ILI Digital",
    author_email="dev@ili.digital",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
