import json
from dataclasses import dataclass, asdict
import config
import asyncio
from enum import Enum
@dataclass
class Transaction:
    sender_id: str
    receiver_id: str
    amount: int

    def __post_init__(self):
        if self.sender_id not in config.CORRECT_PROCESS_NAMES or self.receiver_id not in config.CORRECT_PROCESS_NAMES:
            raise ValueError('sender or receiver id not a correct process name')
class enum_transaction(Enum):
    TRANSACTION = 'transaction'
    FAIL_PROCESS = 'fail_process'
    FIX_PROCESS = 'fix_process'
    PRINT_BLOCKCHAIN = 'print_blockchain'
    PRINT_BALANCE = 'print_balance'
    TYPE = 'type'
    
class master:
    async def _send(self, process: str, msg_dict: dict):
        """
        Send message to one process
        messages are one-way - no response expected
        """
        try:
            port = config.PORT_NUMBERS.get(process)

            # Connect with timeout
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=1.0
            )
        
            msg_dict['from'] = 'master'
            writer.write((json.dumps(msg_dict) + '\n').encode('utf-8'))
            await writer.drain()
        
            # Close connection (no response expected)
            writer.close()
            await writer.wait_closed()
        
            print(f"Master: Sent msg to process {process}: {msg_dict}")
        
        except asyncio.TimeoutError:
            print(f"Master: Timed out in sending to {process}")
    
        except Exception as e:
            print(f"Master: Error sending to {process}: {e}")

    async def _send_with_response(self, process: str, msg_dict:dict) -> dict:
        """
        Send messages with response
        """
        try:
            port = config.PORT_NUMBERS.get(process)
        
            # Connect with timeout
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=1.0
            )
        
            msg_dict['from'] = 'master'
            writer.write((json.dumps(msg_dict) + '\n').encode('utf-8'))
            await writer.drain()
        
            # Close connection (no response expected)
            writer.close()
            await writer.wait_closed()
        
            print(f"Master: Sent msg to process {process}: {msg_dict}")

            response_data = await asyncio.wait_for(
                reader.readline(),
                timeout=config.DELAY + 1
            )

            # Close connection
            writer.close()
            await writer.wait_closed()
        
            # Parse response
            if response_data:
                response = json.loads(response_data.decode('utf-8'))
                if not isinstance(response, dict):
                    raise ValueError(f'process {process} should respond with dict')
                return response
            else:
                # Connection closed without response
                print (f"Master did not receive response from: {process}")
                return {
                    'from' : process,
                    'empty' : True
                }
        
        except asyncio.TimeoutError:
            raise ValueError(f"Master: Timed out in sending to {process}")
    
        except Exception as e:
            raise ValueError(f"Master: Error sending to {process}: {e}") 

    async def moneyTransfer(self, debit_node, credit_node, amount):
        """
        moneyTransfer(debit node, credit node, amount): The transaction transfers amount of money
        from debit node to credit node.
        Note that we assume that the debit node is always the node where the transaction is initiated
        and your interface should not allow the user to input a value that exceeds the balance available
        in that node.
        """
        if debit_node not in config.CORRECT_PROCESS_NAMES or credit_node not in config.CORRECT_PROCESS_NAMES:
            raise ValueError(f'Debit_node and credit_node need to be valid names: {config.CORRECT_PROCESS_NAMES}')
        transaction: Transaction = Transaction(debit_node, credit_node, amount)
        print(f"Master: Sending {transaction}")
    
        
        await self._send(debit_node, {
        enum_transaction.TYPE.value: enum_transaction.TRANSACTION.value,
        enum_transaction.TRANSACTION.value: asdict(transaction)
        })
    
        print(f"Master: Sent transaction ${transaction}")

    async def fail_process(self, process):
        """
        failProcess: This input kills the process to which the input is provided.
        """

        if process not in config.CORRECT_PROCESS_NAMES:
            raise ValueError(f'Process needs to have correct file name {config.CORRECT_PROCESS_NAMES}')
        print(f"Master: Failing process {process}")
        await self._send(process, {
            enum_transaction.TYPE.value: enum_transaction.FAIL_PROCESS.value,
        })
    
        print(f"Master: Sent fail process to ${process}")
        
    async def fix_process(self, process):
        """
        fixProcess: This input will restart the process after it has failed. The process should resume
        from where the failure had happened and the way to do this would be to store the state of a
        process on disk and reading from it when the process starts back 
        """

        if process not in config.CORRECT_PROCESS_NAMES:
            raise ValueError(f'Process needs to have correct file name {config.CORRECT_PROCESS_NAMES}')
        print(f"Master: fixing process {process}")
        await self._send(process, {
            enum_transaction.TYPE.value: enum_transaction.FIX_PROCESS.value,
        })
    
        print(f"Master: Sent fix process to ${process}")

    async def printBlockchain(self, process):
        """
        printBlockchain: This command should print the copy of blockchain on that node.
        """
        if process not in config.CORRECT_PROCESS_NAMES:
            raise ValueError(f'Process needs to have correct file name {config.CORRECT_PROCESS_NAMES}')
    
        print(f"Master: sending printBlockchain to process {process}")
    
        result = await self._send_with_response(process, {
            enum_transaction.TYPE.value: enum_transaction.PRINT_BLOCKCHAIN.value,
        })
    
        empty = result.get('empty')
        if empty:
            print(f"{process} gave no response for printBlockchain")
            return
    
        blockchain = result.get("blockchain")
        if not blockchain:
            raise ValueError(f"Master: {process} did not have blockchain in returned dict")
    
        print(f"Blockchain for process {process} is:")
        print(json.dumps(blockchain, indent=2))

    async def printBalance(self):
        """
        printBalance: This command should print the balance of all 5 accounts on that node.
        """

        print(f"Master: sending printBalance to all processes")
        tasks = {}
        for process in config.CORRECT_PROCESS_NAMES:
            task = asyncio.create_task(
                self._send_with_response(process,
                            { 
                                enum_transaction.TYPE.value: enum_transaction.PRINT_BALANCE.value,

                            }
                            )
            )
            tasks[process] = task
    
        blockchain_list = []
        for coro in asyncio.as_completed(tasks.values()):
            try:
                result = await coro
            
                from_process = result.get('from', '')
                if not from_process:
                    raise ValueError(f"Master: No 'from' in accept response")
            
                empty = result.get('empty')
                if empty:
                    blockchain_list.append((from_process, 'No response'))
                    continue
                # Check if it's a valid dict
                if not isinstance(result, dict):
                    raise ValueError(f"Master: Non-dict response in accept from {from_process}")
                
                balance = enum_transaction.PRINT_BALANCE.value
                if not balance:
                    raise ValueError(f"Master: ${from_process} did not have print_balance")
                blockchain_list.append((from_process, balance))

            except Exception as e:
                raise ValueError(f"Master: Exception in accept: {e}")
    
        print(f"Printing all balances for each process")
        for p,b in blockchain_list:
            print(f"{p}: {b}")

    


    