import os
import web3
import json
from web3 import Web3
from django.conf import settings


class SlpBridge(object):
    
    def __init__(self, contract_address=None, default_account_address=None):
        self.contract_path = os.path.join(settings.BASE_DIR, 'bridge', 'contracts', 'sep20', 'SpiceToken.json')
        rpc_url = 'https://smartbch.greyh.at'
        self.chain_id = 10000
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        self.web3.eth.defaultAccount = default_account_address
        # Build contract abi
        self.contract = None
        with open(self.contract_path) as file:
            contract_json = json.load(file)
            contract_abi = contract_json['abi']
            contract_bytecode = contract_json['bytecode']
            self.contract = self.web3.eth.contract(abi=contract_abi, bytecode=contract_bytecode)
        if contract_address:
            self.contract_address = self.web3.toChecksumAddress(contract_address)
            self.contract = self.web3.eth.contract(address=self.contract_address, abi=contract_abi)
            # Set a default gas limit
            self.gas_limit = 90000

    def transfer(self, recipient, amount, private_key, decimals=18):
        recipient = self.web3.toChecksumAddress(recipient)
        amount_base = amount * (10 ** decimals)
        transaction = self.contract.functions.transfer(recipient, int(amount_base))        
        data = {
            'chainId': self.chain_id,
            'gas': self.gas_limit,
            'gasPrice': self.web3.toWei('1.047', 'gwei'),
            'nonce': self.web3.eth.getTransactionCount(self.web3.eth.defaultAccount)
        }                                 
        transaction = transaction.buildTransaction(data)                                                                                                          
        signed_txn = self.web3.eth.account.signTransaction(transaction, private_key)                           
        txn_hash = self.web3.eth.sendRawTransaction(signed_txn.rawTransaction)
        return txn_hash.hex()
