from setuptools import setup, find_packages

setup(
    name="publish-conda-stack",
    version="0.3.0dev5",
    author="Stuart Berg, Carsten Haubold",
    author_email="team@ilastik.org",
    license="MIT",
    description="Short description",
    # long_description=description,
    # url='https://...',
    package_dir={"": "src"},
    packages=find_packages("./src"),
    include_package_data=True,
    install_requires=[
        "argcomplete",
        "anaconda-client",
        "conda-build>=3.18.10",
        "conda-verify",
        "ruamel.yaml",
    ],
    entry_points={
        "console_scripts": ["publish-conda-stack = publish_conda_stack.__main__:main"]
    },
)
