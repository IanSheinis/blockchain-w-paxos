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
    QUEUE = 'queue'
    QUEUE_START = 'queue_start'
    QUEUE_DELETE = 'queue_delete'
    TYPE = 'type'
    RESET_ALL = 'reset_all'
    
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

        except OSError as e:
            print(f"Could not connect to process {process}, possibly down?")
            return {'from': process, 'empty': True}
    
        except Exception as e:
            print(f"Master: Error sending to {process}: {e}")

    async def _send_with_response(self, process: str, msg_dict: dict) -> dict:
        try:
            port = config.PORT_NUMBERS.get(process)
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=1.0
            )
            msg_dict['from'] = 'master'
            writer.write((json.dumps(msg_dict) + '\n').encode('utf-8'))
            await writer.drain()
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
                first = response.get('first')
                if first:
                    print(f"Process {process} is still in first time recovery")
                    return {'from': process, 'empty': True}
                return response
            else:
                print(f"Master did not receive response from: {process}")
                return {'from': process, 'empty': True}
        except asyncio.TimeoutError:
            raise ValueError(f"Master: Timed out in sending to {process}")
        except OSError as e:
            print(f"Could not connect to process {process}, possibly down?")
            return {'from': process, 'empty': True}
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
    
        print(f"Master: Sent transaction {transaction}")

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
    
        print(f"Master: Sent fail process to {process}")

    async def reset_all(self):
        """
        Reset all processes proposer and acceptor
        """

        tasks = []
        for process in config.CORRECT_PROCESS_NAMES:
            task = asyncio.create_task(
                self._send(process,
                            {
                                enum_transaction.TYPE.value: enum_transaction.RESET_ALL.value
                            }),
                name=process
            )
        await asyncio.gather(*tasks, return_exceptions=True)
        print("Sent reset all to all processes")

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
    
        # TODO print tentative also
        print(f"Blockchain for process {process} is:")
        print(json.dumps(blockchain, indent=2))

    async def printBalance(self, process):
        """
        printBalance: This command should print the balance a specific node.
        """

        if process not in config.CORRECT_PROCESS_NAMES:
            raise ValueError(f'Process needs to have correct file name {config.CORRECT_PROCESS_NAMES}')
    
        print(f"Master: sending printBalance to process {process}")
    
        result = await self._send_with_response(process, {
            enum_transaction.TYPE.value: enum_transaction.PRINT_BALANCE.value,
        })
    
        empty = result.get('empty')
        if empty:
            print(f"{process} gave no response for printBalance")
            return
    
        balance = result.get(enum_transaction.PRINT_BALANCE.value)
        if not balance:
            raise ValueError(f"Master: {process} did not have balance in returned dict")
    
        print(f"Balance for process {process} is:")
        print(balance)

    async def printBalanceAll(self):
        """
        printBalance: prints balance of all nodes
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
            
                from_process = result.get('from')
                if not from_process:
                    raise ValueError(f"Master: No 'from' in accept response")
            
                empty = result.get('empty')
                if empty:
                    blockchain_list.append((from_process, 'No response'))
                    continue
                # Check if it's a valid dict
                if not isinstance(result, dict):
                    raise ValueError(f"Master: Non-dict response in accept from {from_process}")
                
                balance = result.get(enum_transaction.PRINT_BALANCE.value)
                if balance is None:
                    raise ValueError(f"Master: {from_process} did not have print_balance")
                blockchain_list.append((from_process, balance))

            except Exception as e:
                raise ValueError(f"Master: Exception in accept: {e}")
            
        print(f"Printing all balances for each process")
        for p,b in blockchain_list:
            print(f"Bank account for Process {p}: {b}")

    async def queue(self, process: str):
        """
        Get and print the queue of a single process
        """
        if process not in config.CORRECT_PROCESS_NAMES:
            print(f"Invalid process name. Valid names: {config.CORRECT_PROCESS_NAMES}")
            return
        print(f"Master: requesting queue from {process}")
        result = await self._send_with_response(process, {
        enum_transaction.TYPE.value: enum_transaction.QUEUE.value,
        })
        empty = result.get('empty')
        if empty:
            print(f"{process} gave no response for queue")
            return
        queue_data = result.get(enum_transaction.QUEUE.value)
        if queue_data is None:
            raise ValueError(f"Master: {process} did not have queue in returned dict")
        print(f"Queue for process {process}:")
        print(json.dumps(queue_data, indent=2))

    async def queue_start(self, process: str):
        """
        Start back up the queue of a single process (No return msg)
        """
        if process not in config.CORRECT_PROCESS_NAMES:
            print(f"Invalid process name. Valid names: {config.CORRECT_PROCESS_NAMES}")
            return
        print(f"Master: sending queue_start to {process}")
        await self._send(process, {
            enum_transaction.TYPE.value: enum_transaction.QUEUE_START.value,
        })

    async def queue_delete(self, process: str):
        """
        Delete the queue of a single process (No return msg)
        """
        if process not in config.CORRECT_PROCESS_NAMES:
            print(f"Invalid process name. Valid names: {config.CORRECT_PROCESS_NAMES}")
            return
        print(f"Master: sending queue_delete to {process}")
        await self._send(process, {
            enum_transaction.TYPE.value: enum_transaction.QUEUE_DELETE.value,
        })
        print(f"Master: Sent queue_delete to {process}")

    


    