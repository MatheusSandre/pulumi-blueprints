from setuptools import setup
# List of requirements
requirements = []  # This could be retrieved from requirements.txt
# Package (minimal) configuration
setup(
    name="blueprints",
    version="0.0.1",
    description="component resources",
    py_modules=["s3_website_public"],
    # packages=find_packages(),  # __init__.py folders search
    install_requires=requirements
)
