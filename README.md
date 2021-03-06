中文版 | [English][English]
## wukongqueue

一个纯Python3实现的轻量且易于使用的跨网络队列服务

---
[![Build Status](https://travis-ci.com/chaseSpace/wukongqueue.svg?branch=master)](https://travis-ci.com/chaseSpace/wukongqueue)
[![codecov](https://codecov.io/gh/chaseSpace/WukongQueue/branch/master/graph/badge.svg)](https://codecov.io/gh/chaseSpace/WukongQueue)
[![PyPI version](https://badge.fury.io/py/wukongqueue.svg)](https://badge.fury.io/py/wukongqueue)

> wukongqueue的本地队列服务的实现基于Python标准库[`queue`][1].


### 特点
* 快（基于tcp长连接通信）
* 支持多线程调用（连接池）
* 支持所有Python原生类型
* 支持断开自动重连
* 上手成本低，api使用和标准库[`queue`][1]保持一致
* 可设置认证秘钥


### 环境要求
* Python3.5+ (need [type hints](https://www.python.org/dev/peps/pep-0484/))

### 安装
`pip install wukongqueue`
 
### 例子
##### server.py
```python
from wukongqueue import WuKongQueue
import time
# start a queue server
svr = WuKongQueue(host='127.0.0.1', port=666, max_conns=10, max_size=0)
with svr:
    print("svr is started!")
    svr.put(b"1")
    svr.put(b"2")
    print("putted b'1' and b'2', wait for clients...")
    time.sleep(10)
print("svr closed!")
```

##### clientA.py
```python
from wukongqueue import WuKongQueueClient
client = WuKongQueueClient(host='127.0.0.1', port=666)
with client:
    print("got", client.get())  # b"1"
    client.task_done()
    import time
    wait = 5
    time.sleep(wait)
    print("after %s seconds, got" % wait,
          client.get(block=True))  # wait for a while, then print b"2"
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
按上面的顺序启动三个程序，可以看到如下打印:
```
# server.py 首先打印
svr is started! (马上)
putted b'1' and b'2', wait for clients... (马上)
svr closed! (10秒后)

# clientA print secondly
got b'1' (马上)
after 5 seconds, got b'2' (5秒后)
clientA: all task done! (马上)

# clientB print lastly
clientB all task done! (与clientA的all task done同步)
```

#### 连接池
```python
from wukongqueue import ConnectionPool,WuKongQueueClient
pool = ConnectionPool(host="localhost", port=2020, max_connections=3)
client = WuKongQueueClient(connection_pool=pool)
```

[更多例子](https://github.com/chaseSpace/wukongqueue/blob/master/_examples)

### TODO
- [ ] 持久化

### [版本发布日志](https://github.com/chaseSpace/wukongqueue/blob/master/RELEASELOG.md)

## License
[MIT](https://github.com/chaseSpace/WukongQueue/blob/master/LICENSE)

[1]: https://docs.python.org/3.6/library/queue.html
[Chinese]: https://github.com/chaseSpace/wukongqueue/blob/master/README.md
[English]: https://github.com/chaseSpace/wukongqueue/blob/master/README_ENG.md