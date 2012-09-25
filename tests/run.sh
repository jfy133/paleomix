#!/bin/bash

# Ensure that timestamps are as expected
touch --date "2001-9-11 8:46" tests/data/timestamp_older
touch --date "2005-7-7 8:50"  tests/data/timestamp_younger

MODULES=$(find tests/ pypeline/ -name '*.py' | grep -v "__init__" | sed -e 's#\.py##g' -e's#/#.#g')

nosetests -d tests/ --with-coverage \
    --cover-tests \
    $(for module in $MODULES;do echo --cover-package=$module;done)