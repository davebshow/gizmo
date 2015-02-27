class GremlinResponse(list):
    """
    Parse and flatten the Gremlin Server's response a bit. Make standard use
    case easier for end user to process.
    """
    def __init__(self, message):
        super().__init__()
        data = message["result"].get("data", "")
        if data:
            for datum in data:
                if isinstance(datum, dict):
                    try:
                        datum = parse_struct(datum)
                    except (KeyError, IndexError):
                        pass
                self.append(datum)
        self.meta = message["result"]["meta"]
        self.request_id = message["requestId"]
        self.status_code = message["status"]["code"]
        self.message = message["status"]["message"]
        self.attrs = message["status"]["attributes"]


def parse_struct(struct):
    output = {}
    for k, v in struct.items():
        if k != "properties":
            output[k] = v
    # This looses part of the response. I'm not familiar yet with
    # how property ids and property properties work yet. May change.
    properties = {k: [val["value"] for val in v] for (k, v) in
        struct["properties"].items()}
    output.update(properties)
    return output
