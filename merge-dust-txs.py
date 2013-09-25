#!/usr/bin/python

# Distributed under the MIT/X11 software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

from __future__ import absolute_import, division, print_function, unicode_literals

# Script to merge the dust transactions.

import random
import sys

import bitcoin.rpc

from bitcoin.coredefs import COIN
from bitcoin.core import x, b2x, b2lx, str_money_value, CTxIn, CTxOut, CTransaction
from bitcoin.script import CScript, OP_RETURN

proxy = bitcoin.rpc.Proxy()

txins = []
prevouts = set()
sum_value_in = 0
line = -1
for l in sys.stdin.readlines():
    line += 1

    l = l.strip()

    tx = CTransaction.deserialize(x(l))

    for txin in tx.vin:
        try:
            txout_info = proxy.gettxout(txin.prevout)
        except IndexError:
            print('Already spent! line %d, txid %s %d' % \
                    (line, b2lx(txin.prevout.hash), txin.prevout.n),
                    file=sys.stderr)
            continue

        print('line %d: %s %d: %s' % \
                (line, b2lx(txin.prevout.hash), txin.prevout.n,
                    str_money_value(txout_info['txout'].nValue)),
                file=sys.stderr)

        sum_value_in += txout_info['txout'].nValue

        if txin.prevout not in prevouts:
            prevouts.add(txin.prevout)
            txins.append(txin)
        else:
            print('Dup! line %d, txid %s %d' % \
                    (line, b2lx(txin.prevout.hash), txin.prevout.n),
                    file=sys.stderr)

random.shuffle(txins)
tx = CTransaction(txins, [CTxOut(0, CScript([OP_RETURN]))])

print(b2x(tx.serialize()))

print('Total: %s' % str_money_value(sum_value_in), file=sys.stderr)
