from setuptools import setup, find_packages
from oauth2_client import __version__
package_directory = 'oauth2_client'
package_name = 'oauth2-client'


setup(name=package_name,
      version=__version__,
      zip_safe=False,
      packages=find_packages(where=package_directory),
      author='Benjamin Einaudi',
      author_email='antechrestos@gmail.com',
      description='A client library for OAuth2',
      long_description=open('README.rst').read(),
      long_description_content_type="text/x-rst",
      url='https://github.com/antechrestos/OAuth2Client',
      classifiers=[
          "Programming Language :: Python",
          "Natural Language :: English",
          "Operating System :: OS Independent",
          "Programming Language :: Python :: 3",
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: 3.7",
          "Programming Language :: Python :: 3.8",
          "Programming Language :: Python :: 3.9",
          "Topic :: Communications",
      ],
      package_dir={package_directory: package_directory},
      install_requires=[requirement.rstrip(' \r\n') for requirement in open('requirements.txt').readlines()],
      )
