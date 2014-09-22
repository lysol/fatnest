try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

setup(name='fatnest',
  version='0.1',
  description='FatNest',
  author='Derek Arnold',
  author_email='derek@fatnest.com',
  url='http://fatnest.com',
  packages=['fatnest'],
  zip_safe=False,
  install_requires=[
      'Flask',
      'Flask-Uploads',
      'PIL',
      'psycopg2'
      ],
  include_package_data=True
)
