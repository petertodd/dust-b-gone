#!/usr/bin/python

# Distributed under the MIT/X11 software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import socket
import sys

import bitcoin.rpc
from bitcoin.coredefs import COIN
from bitcoin.core import b2x, str_money_value, CTxIn, CTxOut, CTransaction
from bitcoin.script import CScript, OP_RETURN


parser = argparse.ArgumentParser(description='Get rid of dust in your wallet')
parser.add_argument('--dust', type=float,
        default=0.0001,
        help='Value considered to be a dust output.')
parser.add_argument('--dry-run', action='store_true',
        help='Stop before actually getting rid of any dust')
parser.add_argument('--connect', type=str,
        default='198.199.87.4:80',
        help='address:port to connect to to send the dust')

args = parser.parse_args()
args.dust = int(args.dust * COIN)

addr, port = args.connect.split(':')
args.address = (addr, int(port))


proxy = bitcoin.rpc.Proxy()

dust_txouts = [unspent for unspent in proxy.listunspent() if unspent['amount'] <= args.dust]

sum_dust_after_fees = 0
for dust_txout in dust_txouts:
    sum_dust_after_fees += max(dust_txout['amount'] - 1480, 0)

if not dust_txouts:
    print("You're wallet doesn't have any dust in it!")
    sys.exit(0)

print('You have %d dust txouts, worth %s BTC after fees.' % (
    (len(dust_txouts), str_money_value(sum_dust_after_fees))))

print()
print('Get rid of them? y/n: ', end='')
choice = raw_input().lower().strip()

if choice != 'y':
    print('Canceled!')
    sys.exit(1)

# User gave the ok, create a ALL|ANYONECANPAY tx spending those txouts

txins = [CTxIn(dust_txout['outpoint']) for dust_txout in dust_txouts]
txouts = [CTxOut(0, CScript([OP_RETURN]))]
tx = CTransaction(txins, txouts)

r = proxy.signrawtransaction(tx, [], None, 'ALL|ANYONECANPAY')

if not r['complete']:
    print("Error! Couldn't sign transaction:")
    print(b2x(r['tx'].serialize()))
    sys.exit(1)

signed_tx = r['tx']

if args.dry_run:
    print('Done:\n')
    print(b2x(signed_tx.serialize()))
    sys.exit(0)

# Do a sanity check on the transaction
sum_value_discarded = 0
for txin in signed_tx.vin:
    r = proxy.gettxout(txin.prevout)
    sum_value_discarded += r['txout'].nValue

# Abort if the amount is excessively large
if sum_value_discarded > 0.5*COIN:
    print('Aborting due to excessively large value being discarded. (>0.5 BTC)')
    sys.exit(1)

sock = socket.create_connection(args.address)
sock.send(b2x(signed_tx.serialize()))
sock.send('\n')

# lock txouts discarded
proxy.lockunspent(False, [txin.prevout for txin in signed_tx.vin])

print('Done!')
