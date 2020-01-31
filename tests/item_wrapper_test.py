# -*- coding: utf-8 -*-
from wukongqueue._item_wrapper import *
from wukongqueue.utils import Unify_encoding

test_item = [
    b'',
    b'123',
    '123',
    123,
    123 - 1j,
    123.01,
    False,
    [True, False, 123],
    (True, False, 123),
    {"1": 123, "2": True, "3": [1, 2, 3]},
    {1, 2, 3},
    None
]

for item in test_item:
    x = item_wrapper(item)
    assert item_unwrap(x) == item, str(item)
