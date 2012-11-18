Download a website from just a simple link!
=============================================


supports
------------

* multi-thread based
* downloaded files will not be downloaded again if re-run
* filters, url filter and meta-filter({image})


usage
------------

change main() function to suite your own requirement

example
------------

* download programming lua document
add these lines to main()
```python
    store.add_white_filter("www\.lua\.org\/pil\/", "{image}", "\.css")
    store.put(Job("http://www.lua.org/pil/index.html"))
```
