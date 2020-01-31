## Release log
#### v0.0.6a1
* Support all python basic type
* Optimize the part about communication Lock of the internal method 

#### v0.0.5
Same to v0.0.5rc1

#### v0.0.5rc1
*This is a big upgrades*
* Remove the call to [`queue`][1] and develop directly based on its source code
* add api [task_done()][task_done], [join()][join] 
* prefect docstring
* fix bugs and big optimized

#### v0.0.5a1
* optimize tcp-conn accept method
* add argument log_level to `WuKongQueue`

#### v0.0.4
* optimize reconnect logical
* optimize logging
* optimize server imports
* change instruction

#### v0.0.4a1
* allow to set log level  
* set host,port as required argments

[1]: https://docs.python.org/3.6/library/queue.html
[task_done]: https://docs.python.org/3.6/library/queue.html#queue.Queue.task_done
[join]: https://docs.python.org/3.6/library/queue.html#queue.Queue.join