from setuptools import find_packages, setup

setup(
    name="publish-conda-stack",
    version="0.4.2",
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
        "anaconda-client",
        "argcomplete",
        "boa",
        "conda-build>=3.18.10",
        "conda-verify",
        "mamba",
        "ruamel.yaml>=0.15.2",
    ],
    entry_points={
        "console_scripts": ["publish-conda-stack = publish_conda_stack.__main__:main"]
    },
)
