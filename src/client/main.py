#!/usr/bin/env python2.7

import pprint

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import json
import datetime
import time

from random import randrange

from shared import liburl_wrapper
from shared.liburl_wrapper import safe_pushtx
from shared.bitcoind_client.bitcoinclient import BitcoinClient
from shared.fastproto import (
    generateKey,
    sendMessage,
    constructMessage)

from math import ceil
from decimal import Decimal


START_COMMAND = "./runclient.sh"

# Charter url should be url to json with oracles described. Check out http://oracles.li/timelock-charter.json for example
CHARTER_URL = 'http://localhost:8000/test.json'
# Eligius requires 4096 satoshi fee per 512 bytes of transaction ( http://eligius.st/~gateway/faq-page )
# With three oracles, the tx fee is around 512 bytes.
MINERS_FEE = 4*4096 # = fee enough to pay for a tx of 4*512 bytes. a bit higher than required, but we want to support Eligius

def fetch_charter(charter_url):
  while True:
    try:
      charter_json = liburl_wrapper.safe_read(charter_url, timeout_time=10)
      return json.loads(charter_json)
    except:
      print "retrying..."

def main(args):
  btc = BitcoinClient()
  tmp_address = btc.validate_address(btc.get_new_address())

  print "fetching charter: %s" % CHARTER_URL
  charter = fetch_charter(CHARTER_URL)

  client_pubkey = tmp_address['pubkey']
  oracle_pubkeys = []
  for o in charter['nodes']:
#    print json.dumps(o)
    oracle_pubkeys.append(o['pubkey'])

  min_sigs = int(ceil(float(len(oracle_pubkeys))/2))

  print "number of nodes: %i" % len(charter['nodes'])
  print "required signatures: %i" % min_sigs
  sum_fees_satoshi = 0
  for o in charter['nodes']:
    sum_fees_satoshi += Decimal(o['fee'])*100000000
  sum_fees_satoshi += Decimal(charter['org_fee'])*100000000


  key_list = [client_pubkey] + oracle_pubkeys

  response = btc.create_multisig_address(min_sigs, key_list)

  print ""
  print "1. wire the funds to %s" % response['address']
  print "   oracle & org fees: %i satoshi (as detailed in %s)" % (sum_fees_satoshi , CHARTER_URL)
  print "   miners fee: %i satoshi (see MINERS_FEE in src/client/main.py if you want to lower it)" % MINERS_FEE
  print "2. wait for transaction to get any confirmations"
  print "3. run:"
  print "%s main2 %s <locktime_minutes> <return_address>" % ( START_COMMAND, client_pubkey )

def timelock(args):
  if len(args) < 2:
    print "USAGE: `%s timelock <locktime_minutes> <return_address>`" % START_COMMAND
    return

  return_address = args[1]

  print "fetching charter: %s" % CHARTER_URL
  charter = fetch_charter(CHARTER_URL)

  oracle_pubkeys = []
  oracle_fees = {}
  oracle_bms = []
  for o in charter['nodes']:
    oracle_pubkeys.append(o['pubkey'])
    oracle_fees[o['address']] = o['fee']
    oracle_bms.append(o['bm'])

  min_sigs = int(ceil(float(len(oracle_pubkeys))/2))

  print "number of nodes: %i" % len(charter['nodes'])
  print "required signatures: %i" % min_sigs

  oracle_fees[charter['org_address']] = charter['org_fee']

  key_list = oracle_pubkeys

  request = {}
  msig_addr = return_address

  request['message_id'] = "%s-%s" % (msig_addr, str(randrange(1000000000,9000000000)))
  request['pubkey_list'] = key_list

  request['miners_fee_satoshi'] = MINERS_FEE
  request['locktime'] = time.time() + int(args[0])*60
  request['return_address'] = return_address
  request['oracle_fees'] = oracle_fees
  request['req_sigs'] = min_sigs
  request['operation'] = 'safe_timelock_create'

  pub, priv = generateKey()

  meta_request = {}
  meta_request['source'] = pub
  meta_request['channel'] = 0
  meta_request['epoch'] = time.mktime(datetime.datetime.utcnow().timetuple())
  meta_request['body'] = json.dumps(request)

  print sendMessage(constructMessage(priv, **meta_request))

def main2(args):
  if len(args)<3:
    print "USAGE: `%s main2 <pubkey_once> <locktime_minutes> <return_address>`" % START_COMMAND
    print "- run `%s main` to obtain pubkey_once" % START_COMMAND
    print "- keep in mind that this is alpha, don't expect oracles to run properly for any extended periods of time"
    return

  btc = BitcoinClient()

  request = {}
  client_pubkey = args[0]
  request['locktime'] = time.time() + int(args[1])*60
  request['return_address'] = args[2]

  print "fetching charter url" # hopefully it didn't check between running main1 and main2
  charter = fetch_charter(CHARTER_URL)

  oracle_pubkeys = []
  oracle_fees = {}
  oracle_bms = []

  for o in charter['nodes']:
    oracle_pubkeys.append(o['pubkey'])
    oracle_fees[o['address']] = o['fee']
    oracle_bms.append(o['bm'])

  oracle_fees[charter['org_address']] = charter['org_fee']

  min_sigs = int(ceil(float(len(oracle_pubkeys))/2))

  key_list = [client_pubkey] + oracle_pubkeys

  response = btc.create_multisig_address(min_sigs, key_list)
  msig_addr = response['address'] # we're using this as an identificator
  redeemScript = response['redeemScript']

  request['message_id'] = "%s-%s" % (msig_addr, str(randrange(1000000000,9000000000)))
  request['pubkey_list'] = key_list

  request['miners_fee_satoshi'] = MINERS_FEE

  print "fetching transactions incoming to %s ..." % msig_addr

  # for production purposes you might want to fetch the data using bitcoind, but that's expensive
  address_json = liburl_wrapper.safe_read("https://blockchain.info/address/%s?format=json" % msig_addr, timeout_time=10)
  try:
    address_history = json.loads(address_json)
  except:
    print "blockchain.info problem"
    print address_json
    return

  prevtxs = []
  sum_satoshi = 0

  for tx in address_history['txs']:
    outputs = []
    if 'out' in tx:
      outputs = outputs + tx['out']
    if 'outputs' in tx:
      outputs = outputs + tx['outputs']

    for vout in tx['out']:
      print vout
      if vout['addr'] == msig_addr:
        prevtx = {
          'scriptPubKey' : vout['script'],
          'vout': vout['n'],
          'txid': tx['hash'],
          'redeemScript': redeemScript,
        }
        sum_satoshi += vout['value']
        prevtxs.append(prevtx)

  if len(prevtxs) == 0:
    print "ERROR: couldn't find transactions sending money to %s" % msig_addr
    #  return


  request['prevtxs'] = prevtxs
  request['outputs'] = oracle_fees

  request["req_sigs"] = min_sigs
  request['operation'] = 'timelock_create'
  request['sum_satoshi'] = sum_satoshi

  pub, priv = generateKey()

  meta_request = {}
  meta_request['source'] = pub
  meta_request['channel'] = 0
  meta_request['signature'] = 0
  meta_request['body'] = json.dumps(request)

  print sendMessage(constructMessage(priv, **meta_request))


def wait_sign(args):

  bm = BitmessageClient()
  while True:
    messages = bm.get_unread_messages()

    print "unread messages: %r" % len(messages)
    for msg in messages:
      if msg.subject[0:10] == 'final-sign':
        try:
          content = json.loads(msg.message)
          print content['pwtxid']
        except:
          print "problem with message parsing"
          time.sleep(5)
        else:
          print "complete signed tx for pwtxid: %s" % content['pwtxid']
          print "please forward this to Eligius pool ( http://eligius.st/~wizkid057/newstats/pushtxn.php ):"
          print content['transaction']
      bm.mark_message_as_read(msg)

    time.sleep(5)

def tx_info(args):
  tx = args[0]
  btc = BitcoinClient()

  prevtxs = '[{"redeemScript": "52210281cf9fa9241f0a9799f27a4d5d60cff74f30eed1d536bf7a72d3dec936c151632102e8e22190b0adfefd0962c6332e74ab68831d56d0bfc2b01b32beccd56e3ef6f021035ff60e6745093b9bcbae93082e1c50ca5b3fcf8bcd186a46da46ded5132530522103a9bd3bfbd9f9b1719d3ecad8658796dc5e778177d77145b5c37247eb3060861854ae", "txid": "10a3ab54e1e19701fcb86c7725621b5b1b26415f94363de35a493ba9ca502b15", "vout": 0, "scriptPubKey": "a914a37ce66d7065157037e90ca4d4b4a20d8d865a2687"}]'
  prevtxs = json.loads(prevtxs)

  pprint.pprint( btc.decode_raw_transaction(tx))

  pprint.pprint (btc.signatures_count(tx, prevtxs))

  pprint.pprint (btc.signatures(tx, prevtxs))


def pushtx(args):
  tx = args[0]
  print safe_pushtx(tx)


OPERATIONS = {
  'main': main,
  'timelock': timelock,
  'main2': main2,
  'wait': wait_sign,
  'txinfo': tx_info,
  'pushtx': pushtx,
}

SHORT_DESCRIPTIONS = {
  'main': "prepares the first multisig",
  'main2': "broadcasts a request for create (timelock/bounty)",
  'wait_sign': "waits for a signature",
  'tx_info': 'information about a signed tx',
  'pushtx': 'pushes tx to eligius',
}

def help():
  print "You can use one of the following functions:"
  for name, desc in SHORT_DESCRIPTIONS.iteritems():
    print "{0} - {1}".format(name, desc)
  print "Learn more by using {0} help functionname".format(START_COMMAND)

def main(args):
  if len(args) == 0:
    print "no arguments given, use {0} help for possible operations".format(START_COMMAND)
    return
  if args[0] == 'help':
    if len(args) == 1:
      help()
    else:
      if args[1] in OPERATIONS:
        print OPERATIONS[args[1]].__doc__
    return

  if args[0] in OPERATIONS:
    operation = OPERATIONS[args[0]]
    operation(args[1:])
  else:
    print "unknown operation, use {} help for possible operations".format(START_COMMAND)



if __name__=="__main__":
  args = sys.argv[1:]
  main(args)

