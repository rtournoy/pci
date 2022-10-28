PCI Automated Tests
===================

Requirements
------------

Selenium tests:

	make test.install.selenium

Cypress tests:

	make test.install


Setup test environment
----------------------

	make test.setup
	make test.setup test.db.rr  # for RR


Run tests
---------

	make test.full

or live:

	npx cypress open

shorter scenario:

	make test.basic

	SHOW=y make test.basic  # live-show


Reset test environment
----------------------

	make test.reset
	make test.reset.rr  # for RR