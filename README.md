## wukongqueue
A small and convenient cross process FIFO queue service based on TCP protocol.

---
[![codecov](https://codecov.io/gh/chaseSpace/WukongQueue/branch/master/graph/badge.svg)](https://codecov.io/gh/chaseSpace/WukongQueue)
## Features
* Fast (directly based on tcp)
* Multi Clients from different processes
* APIs' usage like stdlib [`queue`](https://docs.python.org/3.6/library/queue.html)

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
svr.put(b"1") # client is now started
time.sleep(3)
svr.put(b"2")
svr.close()
```

##### client.py
```python
from wukongqueue import WuKongQueueClient
client = WuKongQueueClient(host='127.0.0.1', port=666)
print(client.get()) # b"1"
print(client.get(block=True)) # wait for 3 seconds, then get b"2"
client.close()
```

Currently, the get and put methods on the server and client only support bytes
And strings, but in the end, they still communicate between processes in bytes.

#### Use `with` statement
```python
from wukongqueue import WuKongQueueClient

# assume server is started now
with WuKongQueueClient() as client:
    client.get()
# The client automatically close connection to server at the end of 
# the with statement.
```
Sometimes the creation and use of client are not in the same place. 
You can write with the following method:
```python
from wukongqueue import WuKongQueueClient

# create client (file_a.py)
client = WuKongQueueClient()

# use client (file_b.py)
# from file_a import client
with client.helper():
    client.get()
# The client still automatically close connection to server at the end of 
# the with statement.
```
**The server's usage of with is exactly the same.**

## TODO
support apis below:
* [`task_done()`](https://docs.python.org/3.6/library/queue.html#queue.Queue.task_done)
* [`join()`](https://docs.python.org/3.6/library/queue.html#queue.Queue.join)

## License
[MIT](https://github.com/chaseSpace/WukongQueue/blob/master/LICENSE)