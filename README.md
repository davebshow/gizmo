**gizmo** is a **Python 3** driver for the the TP3 Gremlin Server. This module is built on [asyncio](https://docs.python.org/3/library/asyncio.html) and [websockets](http://aaugustin.github.io/websockets/).

Minimal example:


Fire up the Gremlin-Server.
```bash
$ ./bin/gremlin-server.sh conf/gremlin-server-modern.yaml
```

Use websockets to submit Gremlin scripts to the server and receive the results.
```python
>>> from gizmo import GremlinClient
>>> gc = GremlinClient('ws://localhost:8182/')
>>> gc.execute("g.V(x).out()", bindings={"x":1}, consumer=lambda x: print(x))

# {'result': {'data': [{'label': 'software', 'id': 3, 'properties': {'name': [{'value': 'lop', 'id': 4, 'properties': {}}], 'lang': [{'value': 'java', 'id': 5, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 2, 'properties': {'name': [{'value': 'vadas', 'id': 2, 'properties': {}}], 'age': [{'value': 27, 'id': 3, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 4, 'properties': {'name': [{'value': 'josh', 'id': 6, 'properties': {}}], 'age': [{'value': 32, 'id': 7, 'properties': {}}]}, 'type': 'vertex'}], 'meta': {}}, 'requestId': '9c2d1263-eebf-47e9-a169-5b790eb49d6f', 'status': {'code': 200, 'message': '', 'attributes': {}}}

>>> for x in gc.execute("g.V(x).out()", bindings={"x":1}):
        if x:
            print(x)

# {'result': {'data': [{'label': 'software', 'id': 3, 'properties': {'name': [{'value': 'lop', 'id': 4, 'properties': {}}], 'lang': [{'value': 'java', 'id': 5, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 2, 'properties': {'name': [{'value': 'vadas', 'id': 2, 'properties': {}}], 'age': [{'value': 27, 'id': 3, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 4, 'properties': {'name': [{'value': 'josh', 'id': 6, 'properties': {}}], 'age': [{'value': 32, 'id': 7, 'properties': {}}]}, 'type': 'vertex'}], 'meta': {}}, 'requestId': 'ab51311f-d532-401a-9f4b-df6434765bd3', 'status': {'code': 200, 'message': '', 'attributes': {}}}

```
**AsyncGremlinClient** coming soon!!!
