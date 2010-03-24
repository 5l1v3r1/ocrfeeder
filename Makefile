PYTHON=`which python`
DESTDIR=/
BUILDIR=$(CURDIR)/debian/ocrfeeder
PROJECT=ocrfeeder
PO_DIR=po
LINGUAS=$(shell cat $(PO_DIR)/LINGUAS)
RESOURCES_DIR=resources
VERSION=0.6.5

all:
	@echo "make source   - Create source package"
	@echo "make install  - Install on local system"
	@echo "make buildrpm - Generate a rpm package"
	@echo "make builddeb - Generate a deb package"
	@echo "make clean    - Get rid of scratch and byte files"

po/$(PROJECT).pot:
	cd $(PO_DIR); intltool-update -p -g $(PROJECT)

update-po: $(PO_DIR)/$(PROJECT).pot
	cd $(PO_DIR); intltool-update -r -g $(PROJECT)

%.mo : %.po
	@langname=`basename $(<) .po`; \
	dirname=locale/$$langname/LC_MESSAGES/; \
	echo Generating $$dirname/$(PROJECT).mo; \
	mkdir -p $$dirname; \
	msgfmt $< -o $$dirname/$(PROJECT).mo; \

generate-mo: $(patsubst %,$(PO_DIR)/%.mo,$(LINGUAS))

$(RESOURCES_DIR)/$(PROJECT).desktop: $(RESOURCES_DIR)/$(PROJECT).desktop.in $(PO_DIR)/*.po
	@intltool-merge -d $(PO_DIR) $(RESOURCES_DIR)/$(PROJECT).desktop.in $(RESOURCES_DIR)/$(PROJECT).desktop

i18n: po/$(PROJECT).pot update-po generate-mo $(RESOURCES_DIR)/$(PROJECT).desktop

source: i18n
	$(PYTHON) setup.py sdist $(COMPILE)

install: i18n
	$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

buildrpm: i18n
	$(PYTHON) setup.py bdist_rpm --post-install=rpm/postinstall --pre-uninstall=rpm/preuninstall

builddeb: i18n
	dpkg-buildpackage -rfakeroot -b

clean:
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean
	rm -rf build/ MANIFEST
	rm -rf locale po/$(PROJECT).pot $(RESOURCES_DIR)/$(PROJECT).desktop
	find . -name '*.pyc' -delete

generatepot:
	@# After this, use the following command to initiate an empty po: msginit --input=po/ocrfeeder.pot --locale=en_US
	@# To update an existing po, do this: msgmerge -U po/en_US.po new_en_US.po        the po/en_US.po will be updated.
	xgettext --language=Python --keyword=_ --output=$(PO_DIR)/$(PROJECT).pot studio/*.py feeder/*.py util/*.py ocrfeeder ocrfeeder-cli

