# Download a website from just an entry link!


## Supports

* multi-thread based
* downloaded files will not be downloaded again if re-run
* filters

## Filters

Filters is based on regex basically. 
There are two kind of filters. One is white filter, and the other is black.
White filter means if the filter match the url, the url will be downloaded. The black filter do the opposite.
Besides regex filter, a meta-filter({image}) is implemented right now. It presents image resource, including jpeg,
gif and png resource.


## Usage

change main() function to suite your own requirement, such as downloading Lua references from lua.org, 
using corret filter you can download the reference perfectly -- see example below :P

## Example

* download \<\<programming in Lua\>\> online document

add following lines to main()

```python
store.add_white_filter("www\.lua\.org\/pil\/", "{image}", "\.css")
store.put(Job("http://www.lua.org/pil/index.html"))
```
