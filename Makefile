PHONY: test lint build check-dist

test:
	coverage run --source .\oauth2_client\ -m unittest -vv

lint:
	black --check oauth2_client
	pylint oauth2_client
	bandit -r oauth2_client

build:
	python setup.py sdist bdist_wheel

check-dist:
	pip install -U twine wheel --quiet
	python setup.py egg_info
	python setup.py sdist bdist_wheel
	twine check --strict dist/*

docs:
	sphinx-apidoc -o docs/ oauth2_client
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
