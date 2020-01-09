## wukongqueue
A lightweight and convenient cross process FIFO queue service based on TCP protocol.

---
[![Build Status](https://travis-ci.com/chaseSpace/wukongqueue.svg?branch=master)](https://travis-ci.com/chaseSpace/wukongqueue)
[![codecov](https://codecov.io/gh/chaseSpace/WukongQueue/branch/master/graph/badge.svg)](https://codecov.io/gh/chaseSpace/WukongQueue)
[![PyPI version](https://badge.fury.io/py/wukongqueue.svg)](https://badge.fury.io/py/wukongqueue)

> wukongqueue's local queue service is developed based on Python standard library [`queue`][1].


## Features
* Fast (directly based on tcp long-running connection)
* Multi-producer and Multi-consumer from different threads/processes
* Easy to use, APIs' usage like stdlib [`queue`][1]
* Allow to set authentication key for connection to server


## Requirements
* Python3.5+ (need [type hints](https://www.python.org/dev/peps/pep-0484/))

## Install
`pip install wukongqueue`
 
## Examples
##### server.py
```python
from wukongqueue import WuKongQueue
import time
# start a queue server
svr = WuKongQueue(host='127.0.0.1',port=666,max_conns=10,max_size=0)
with svr:
    print("svr is started!")
    svr.put(b"1")
    time.sleep(10)
    svr.put(b"2")
    print("wait for clients...")
    time.sleep(10)
print("putted b'1' and b'2', svr closed!")
```

##### clientA.py
```python
from wukongqueue import WuKongQueueClient
client = WuKongQueueClient(host='127.0.0.1', port=666)
with client:
    print("got",client.get()) # b"1"
    client.task_done()
    print("after 10 seconds, got",client.get(block=True)) # wait for 3 seconds, then print b"2"
    client.task_done()
    print("clientA: all task done!")
```

##### clientB.py
```python
from wukongqueue import WuKongQueueClient
client = WuKongQueueClient(host='127.0.0.1', port=666)
with client:
    client.join()
    print("clientB all task done!")
```
Then start these three program in order, you can see the following print:
```
# server.py print firstly
svr is started! (immediately)
wait for clients... (+3 seconds)
putted b'1' and b'2', svr closed! (+10s)

# clientA print secondly
got b'1' (immediately)
after 3 seconds, got b'2' (+3 seconds)
clientA: all task done!

# clientB print lastly
clientB all task done! (same as clientA last print)
```

Currently, the get and put methods on the server and client only support bytes
and strings, but in the end, they still communicate between processes in bytes.

**The server's usage of with is exactly the same.**

[more examples](https://github.com/chaseSpace/wukongqueue/blob/master/_examples)


## [Release log](https://github.com/chaseSpace/wukongqueue/blob/master/RELEASELOG.md)

## License
[MIT](https://github.com/chaseSpace/WukongQueue/blob/master/LICENSE)

[1]: https://docs.python.org/3.6/library/queue.html