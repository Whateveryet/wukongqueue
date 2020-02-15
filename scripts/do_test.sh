#!/usr/bin/env bash

tests(){
    coverage run tests/server_tests.py -v
    coverage run tests/client_tests2.py -v
    coverage run tests/client_tests.py -v
}

if tests; then
    coverage report -m
    codecov -t a75972c8-bbc9-4332-aa8b-5e06c45b655e
fi