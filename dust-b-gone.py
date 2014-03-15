#!/usr/bin/python

# Distributed under the MIT/X11 software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import getpass
import socket
import socks
import sys

import bitcoin
import bitcoin.rpc

from bitcoin.core import COIN, b2x, str_money_value, CTxIn, CTxOut, CTransaction
from bitcoin.core.script import CScript, OP_RETURN


parser = argparse.ArgumentParser(description='Get rid of dust in your wallet')
parser.add_argument('--dust', type=float,
        default=0.0001,
        help='Value considered to be a dust output.')
parser.add_argument('--dry-run', action='store_true',
        help='Stop before actually getting rid of any dust')
parser.add_argument('--connect', type=str,
        default='dust-b-gone.bitcoin.petertodd.org:80',
        help='address:port to connect to to send the dust')
parser.add_argument('--testnet', action='store_true',
        help='Use testnet rather than mainnet')
parser.add_argument('--tor', action='store_true',
        help='connect via local tor proxy (127.0.0.1:9050)')

args = parser.parse_args()
args.dust = int(args.dust * COIN)

addr, port = args.connect.split(':')
args.address = (str(addr), int(port))

if args.testnet:
    bitcoin.SelectParams('testnet')

proxy = bitcoin.rpc.Proxy()

dust_txouts = [unspent for unspent in proxy.listunspent(0) if unspent['amount'] <= args.dust]

sum_dust_after_fees = 0
for dust_txout in dust_txouts:
    sum_dust_after_fees += max(dust_txout['amount'] - 1480, 0)

if not dust_txouts:
    print("Your wallet doesn't have any dust in it!")
    sys.exit(0)

print('You have %d dust txouts, worth %s BTC after fees.' % (
    (len(dust_txouts), str_money_value(sum_dust_after_fees))))

print()
print('Get rid of them? y/n: ', end='')
choice = raw_input().lower().strip()

if choice != 'y':
    print('Canceled!')
    sys.exit(1)

# User gave the ok, create a NONE|ANYONECANPAY tx spending those txouts

txins = [CTxIn(dust_txout['outpoint']) for dust_txout in dust_txouts]
txouts = [CTxOut(0, CScript([OP_RETURN]))]
tx = CTransaction(txins, txouts)

r = None
try:
    r = proxy.signrawtransaction(tx, [], None, 'NONE|ANYONECANPAY')
except bitcoin.rpc.JSONRPCException as exp:
    if exp.error['code'] == -13:
        pwd = getpass.getpass('Please enter the wallet passphrase with walletpassphrase first: ')
        proxy.walletpassphrase(pwd, 10)

        r = proxy.signrawtransaction(tx, [], None, 'NONE|ANYONECANPAY')

    else:
        raise exp


if not r['complete']:
    print("Error! Couldn't sign transaction:")
    print(b2x(r['tx'].serialize()))
    sys.exit(1)

signed_tx = r['tx']

# Do a sanity check on the transaction
sum_value_discarded = 0
for txin in signed_tx.vin:
    r = proxy.gettxout(txin.prevout)
    sum_value_discarded += r['txout'].nValue

# Abort if the amount is excessively large
if sum_value_discarded > 0.01*COIN:
    print('Aborting due to excessively large value being discarded. (>0.01 BTC)')
    sys.exit(1)

if args.dry_run:
    print('Done:\n')
    print(b2x(signed_tx.serialize()))
    sys.exit(0)

# Monkey-patch in socks proxy support if required for tor
if args.tor:
    socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)
    socket.socket = socks.socksocket

    def create_connection(address, timeout=None, source_address=None):
        sock = socks.socksocket()
        sock.connect(address)
        return sock
    socket.create_connection = create_connection

sock = socket.create_connection(args.address)
sock.send(b2x(signed_tx.serialize()))
sock.send('\n')
sock.close()

# lock txouts discarded
proxy.lockunspent(False, [txin.prevout for txin in signed_tx.vin])

print('Done!')
