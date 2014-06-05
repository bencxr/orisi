import json

class OPERATION:
  PING = 'PingRequest'
  TRANSACTION = 'TransactionRequest'


VALID_OPERATIONS = {
    'ping': OPERATION.PING,
    'transaction': OPERATION.TRANSACTION
}

OPERATION_REQUIRED_FIELDS = {
    OPERATION.PING: [],
    OPERATION.TRANSACTION: ['raw_transaction', 'check_time', 'condition'],
}


PROTOCOL_VERSION = '0.1'
PROTOCOL_FOOTER = \
"""
--
Distributed Oracle
Version {0}
""".format(PROTOCOL_VERSION)

PING_SUBJECT = 'PingResponse'
PING_MESSAGE_RAW = {
  "response": "active",
  "version": PROTOCOL_VERSION,
}
PING_MESSAGE = json.dumps(PING_MESSAGE_RAW)


IDENTITY_SUBJECT = 'IdentityBroadcast'
IDENTITY_MESSAGE_RAW = {
  "response": "active",
  "version": PROTOCOL_VERSION 
}
IDENTITY_MESSAGE = json.dumps(IDENTITY_MESSAGE_RAW)