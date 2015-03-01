class StatusException(IOError):

    def __init__(self, value, message):
        self.value = value
        self.response = {
            498: ("REQUEST_ERROR_MALFORMED_REQUEST",
                  """The request message was not properly formatted which means
                  it could not be parsed at all or the "op" code was not
                  recognized such that Gremlin Server could properly route it
                  for processing.  Check the message format and retry the
                  request"""),
            499: ("REQUEST_ERROR_INVALID_REQUEST_ARGUMENTS",
                  """The request message was parseable, but the arguments
                  supplied in the message were in conflict or incomplete. Check
                  the message format and retry the request."""),
            500: ("SERVER_ERROR",
                  """A general server error occurred that prevented the request
                  from being processed."""),
            596: ("SERVER_ERROR_TRAVERSAL_EVALUATION",
                  """The remote
                  {@link org.apache.tinkerpop.gremlin.process.Traversal}
                  submitted for processing evaluated in on the server with
                  errors and could not be processed"""),
            597: ("SERVER_ERROR_SCRIPT_EVALUATION",
                  ("The script submitted for processing evaluated in the " +
                   "{@code ScriptEngine} with errors and could not be  " +
                   "processed.Check the script submitted for syntax errors " +
                   "or other problems and then resubmit.")),
            598: ("SERVER_ERROR_TIMEOUT",
                  """The server exceeded one of the timeout settings for the
                  request and could therefore only partially respond or not
                  respond at all."""),
            599: ("SERVER_ERROR_SERIALIZATION",
                  """The server was not capable of serializing an object that
                  was returned from the script supplied on the request. Either
                  transform the object into something Gremlin Server can process
                  within the script or install mapper serialization classes to
                  Gremlin Server.""")
        }

        self.message = 'Code [{}]: {}. {}.\n\n{}'.format(self.value,
            self.response[self.value][0], self.response[self.value][1], message)

        def __str__(self):
            return self.message
