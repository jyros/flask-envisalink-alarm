# author: oskar.blom@gmail.com
#
# Make sure your gevent version is >= 1.0
import gevent
from gevent.wsgi import WSGIServer
from gevent.queue import Queue
from flask import Flask, Response
import time
import Envisalink
from AlarmServerConfig import AlarmServerConfig
import argparse
import json
import logging
import time
import sys

logger = logging.getLogger('alarmserver')
logger.setLevel(logging.DEBUG)
# Console handler 
# Prints all messages (debug level)
ch = logging.StreamHandler();
ch.setLevel(logging.DEBUG)
# create formatter
formatter = logging.Formatter(
    fmt='%(asctime)s %(name)s %(levelname)s: %(message)s',
    datefmt='%b %d %H:%M:%S')
ch.setFormatter(formatter);
# add handlers to logger
logger.addHandler(ch)


# globals
ENVISALINKCLIENT = None
CONNECTEDCLIENTS={}

# SSE "protocol" is described here: http://mzl.la/UPFyxY
class ServerSentEvent(object):

    def __init__(self, data):
        self.data = data
        self.event = None
        self.id = None
        self.desc_map = {
            self.data : "data",
            self.event : "event",
            self.id : "id"
        }

    def encode(self):
        if not self.data:
            return ""
        lines = ["%s: %s" % (v, k) 
                 for k, v in self.desc_map.iteritems() if k]
        
        return "%s\n\n" % "\n".join(lines)

app = Flask(__name__)
subscriptions = []

# Client code consumes like this.
@app.route("/")
def index():
    debug_template = """
     <html>
       <head>
       </head>
       <body>
         <h1>Server sent events</h1>
         <div id="event"></div>
         <script type="text/javascript">

         var eventOutputContainer = document.getElementById("event");
         var evtSrc = new EventSource("/subscribe");

         evtSrc.onmessage = function(e) {
             console.log(e.data);
             eventOutputContainer.innerHTML = e.data;
         };

         </script>
       </body>
     </html>
    """
    return(debug_template)

@app.route("/debug")
def debug():
    return "Currently %d subscriptions" % len(subscriptions)

@app.route("/publish")
def publish():
    #Dummy data - pick up from request for real data
    def notify():
        msg = str(time.time())
        for sub in subscriptions[:]:
            sub.put(msg)
    
    gevent.spawn(notify)
    
    return "OK"

@app.route("/subscribe")
def subscribe():
    def gen():
        q = Queue()
        subscriptions.append(q)
        try:
            while True:
                result = q.get()
                ev = ServerSentEvent(str(result))
                yield ev.encode()
        except GeneratorExit: # Or maybe use flask signals
            subscriptions.remove(q)

    return Response(gen(), mimetype="text/event-stream")

@app.route("/api")
def api():
    return Response(json.dumps(ENVISALINKCLIENT._alarmstate))

@app.route("/api/refresh")
def refresh():
    ENVISALINKCLIENT.send_command('001', '')
    return Response(json.dumps({'response' : 'Request to refresh data received'}))

def main():
    global ENVISALINKCLIENT

    parser = argparse.ArgumentParser('Flask powered Alarm Server')
    parser.add_argument('config', help='Configurationf file', default='')
    args = parser.parse_args()

    logger.info('Using configuration file %s' % args.config)

    config = AlarmServerConfig(args.config)

    # Create Envisalink client object
    ENVISALINKCLIENT = Envisalink.Client(config, CONNECTEDCLIENTS)
    gevent.spawn(ENVISALINKCLIENT.connect)

    app.debug = True
    server = WSGIServer(("", 5000), app)
    server.start()
    # Then visit http://localhost:5000 to subscribe 
    # and send messages by visiting http://localhost:5000/publish
    try:
        while True:
            gevent.sleep(0.1)
            # insert scheduling code here.
    except KeyboardInterrupt:
        print "Crtl+C pressed. Shutting down."
        logger.info('Shutting down from Ctrl+C')

        server.stop()
        sys.exit()

if __name__ == "__main__":
    main()
