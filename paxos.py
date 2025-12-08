from typing import cast 
import sys
import random
import json
from collections import deque
import config
from enum import Enum
import asyncio
import json
import math
import block
import transaction
import bank_account
class paxos_enum():
    class proposer(Enum):
        PREPARE = 'PREPARE'
        ACCEPT = 'ACCEPT'
        DECISION = 'DECISION'
    class acceptor(Enum):
        PREPARE_REJECT = 'PREPARE_REJECT'
        PREPARE_PROMISE = 'PREPARE_PROMISE'
        NO_RESPONSE = 'NO_RESPONSE'
        ACCEPT_REJECT = 'ACCEPT_REJECT'    
        ACCEPT_ACCEPTED = 'ACCEPT_ACCEPTED'
    class json(Enum):
        """
        Acceptor should be
            {
            'type': 'PROMISE',
            'from': self.node_id,
            'ballot_num': ballot_num,
            'accepted_ballot': self.accepted_ballot,
            'accepted_value': self.accepted_value
            }
        """
        TYPE = 'type'
        FROM = 'from'
        BALLOT_NUM = 'ballot_num' # What proposer sends
        ACCEPTED_BALLOT = 'accepted_ballot'
        ACCEPTED_VALUE = 'accepted_value'
        PROMISED_BALLOT = 'promised_ballot' # What acceptor sends back
        DEPTH = 'depth' #block depth
        RECOVERY = 'recovery'
        FIRST_RECOVERY = 'first_recovery'
        NO_RESPONSE = 'NO_RESPONSE'

class proposer:
    # Prepare variables
    ballotNum: int # If -1 then it is not currently trying to be leader
    acceptNum: int
    acceptVal: dict
    reset: bool # Check if state is clean for recovery algorithm
    def __init__(self, process, external_process, outer: paxos) -> None:
        self.outer = outer
        self.reset = True
        self.process_id: str = process
        self.external_process_id: list[str] = external_process
        self.ballotNum = -1
        self.acceptNum = -1
        self.acceptVal = {}
        self.active_tasks: set[asyncio.Task] = set()
        self.decision_lock = asyncio.Lock()  # Prevent concurrent decision processing

    async def prepare(self, transaction: transaction.Transaction, current_blockchain: block.Block | None) -> bool:
        """
        Phase 1: Send PREPARE to all acceptors, wait for majority PROMISE
        Returns as soon as majority is reached (doesn't wait for all)
        """
        self.reset = False # Initiating algorithms now
        async with self.outer.reset_condition:
            self.outer.reset_condition.notify_all()

        self.ballotNum += 1
    
        print(f"Process {self.process_id}: Starting PREPARE with ballot {self.ballotNum}")
    
        # Calculate majority needed
        majority_needed = math.ceil(len(self.external_process_id) / 2)
    
        depth: int
        if not current_blockchain:
            depth = 1 # Add 1 because it would be the same as a blockchain otherwise
        else:
            depth = current_blockchain.length() + 1 #"An acceptor does not accept prepare or accept messages from a contending leader if the depth of the block being proposed is lower than the acceptor's depth of its copy of the blockchain."
        # Create tasks for all processes
        tasks = {}
        for process in self.external_process_id:
            task = asyncio.create_task(
                self._send_prepare_to_process(process, self.ballotNum, depth),
                name = process
            )
            tasks[process] = task
            self.active_tasks.add(task)
    
        # Wait for majority (or all to finish)
        promises = []
        completed = 0
        max_seen_ballot: int = 0 # max ballot incase of higher existing ballot
        total = len(tasks)
    
        # Use as_completed to process responses as they arrive
        for coro in asyncio.as_completed(tasks.values()):
            try:
                completed += 1
                result = await coro


                from_process = result.get(paxos_enum.json.FROM.value, '')
                if not from_process:
                    raise ValueError(f'No from for process: {self.process_id}')
                # Check if it's a valid PROMISE
                if isinstance(result, dict):
                    result_type = result.get(paxos_enum.json.TYPE.value)
                    if result_type == paxos_enum.acceptor.PREPARE_PROMISE.value:
                        promises.append(result)
                        print(f"Process {self.process_id}: Got promise #{len(promises)} from {from_process}")
                
                        if len(promises) >= majority_needed:
                            print(f"Process {self.process_id}: Got majority ({len(promises) + 1}/ {len(config.CORRECT_PROCESS_NAMES)})!")
                            break

                    elif result_type == paxos_enum.acceptor.PREPARE_REJECT.value:
                        promise_ballot = int(result.get(paxos_enum.json.PROMISED_BALLOT.value, -100)) #type error if no -100
                        if promise_ballot == -100:
                            raise ValueError(f"Process {self.process_id}: should not be -1 here")
                        max_seen_ballot = max(promise_ballot, max_seen_ballot)

                    elif result_type == paxos_enum.acceptor.NO_RESPONSE.value:
                        print(f"Process {self.process_id} No response from {from_process} in accept")

                    else:
                        raise ValueError(f"Got unexpected response from {from_process}: {result_type}")

                    
                else:
                    raise ValueError(f"Process {self.process_id} did not receive a dict in proposer prepare")
            
                # Check if it's impossible to get majority
                remaining = total - completed
                if len(promises) + remaining < majority_needed:
                    print(f"Process {self.process_id}: Can't reach majority, stopping early")
                    break
        
            except OSError as e:
                task = cast(asyncio.Task, coro)
                print(f"{self.process_id}: Tried connecting to {task.get_name()}, but it is down")

                # Check if it's impossible to get majority (same as above)
                remaining = total - completed
                if len(promises) + remaining < majority_needed:
                    print(f"Process {self.process_id}: Can't reach majority, stopping early")
                    break
            except Exception as e:
                raise ValueError(f"Process {self.process_id}: Exception in prepare: {e}")
    
        # Cancel remaining tasks (they're still running in background)
        for task in tasks.values():
            self.active_tasks.discard(task)
            if not task.done():
                task.cancel()
    
        # Check if we got majority
        got_majority = len(promises) >= majority_needed
    
        if got_majority:
            print(f"Process {self.process_id}: PREPARE succeeded with {len(promises)} promises")
        
            # incorporate (AcceptNum, AcceptVal) logic from acceptors
            acceptNum: int = -1
            acceptVal: dict = {}
            for promise in promises:
                promise_from = promise.get(paxos_enum.json.FROM.value)
                promise_acceptNum = promise.get(paxos_enum.json.ACCEPTED_BALLOT.value, -1)
                promise_acceptVal: dict = promise.get(paxos_enum.json.ACCEPTED_VALUE.value, {})
                if promise_acceptNum > acceptNum:
                    acceptNum = promise_acceptNum
                    acceptVal = promise_acceptVal

            if not acceptVal or acceptNum == -1:
                new_blockchain: block.Block = block.Block(transaction, current_blockchain)
                acceptVal = new_blockchain.to_json() # Send whole new block chain each time
                print(f"Created new block: ")
                print(new_blockchain) # You are expected to print the nonce and the hash values once the correct hash is computed... Also, print the hash pointers in the blockchain."

            accept_success: bool = await self.accept(self.ballotNum, acceptVal, depth)
            if accept_success: 
                return accept_success # Bool chain
            else:
                print(f"{self.process_id}'s proposer prepare phase: Failed to propose accept, new ballot number is: {self.ballotNum}")
                return False
        else:
            print(f"Process {self.process_id}: PREPARE failed ({len(promises)}/{majority_needed})\n Highest ballot received: {max_seen_ballot}")
            self.ballotNum = max_seen_ballot
    
        return False


    async def _send_prepare_to_process(self, process: str, ballot_num: int, depth: int) -> dict:
        try:
            port = config.PORT_NUMBERS.get(process)
        
            # Connect with timeout
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=1.0  # 1 second to connect
            )
        
            # Send PREPARE
            prepare_msg = {
                paxos_enum.json.TYPE.value: paxos_enum.proposer.PREPARE.value,
                paxos_enum.json.BALLOT_NUM.value: ballot_num,
                paxos_enum.json.FROM.value: self.process_id,
                paxos_enum.json.DEPTH.value: depth
            }
        
            writer.write((json.dumps(prepare_msg) + '\n').encode('utf-8'))
            await writer.drain()
        
            # Wait for PROMISE response with timeout
            response_data = await asyncio.wait_for(
                reader.readline(),
                timeout=config.DELAY + 1
            )
        
            # Close connection
            writer.close()
            await writer.wait_closed()
        
            await asyncio.sleep(config.DELAY)  # Wait a certain time
        
            # Parse response
            if response_data:
                response = json.loads(response_data.decode('utf-8'))
                if not isinstance(response, dict):
                    raise ValueError(f'process {process} should respond with dict')
                return response
            else:
                # Connection closed without response
                print(f"Process {self.process_id}: No response from {process}")
                return {paxos_enum.json.TYPE.value: paxos_enum.acceptor.NO_RESPONSE.value,
                        paxos_enum.json.FROM.value: process}
    
        except asyncio.TimeoutError:
            print(f"Process {self.process_id}: Timeout from {process} in prepare")
            return {paxos_enum.json.TYPE.value: paxos_enum.acceptor.NO_RESPONSE.value,
                    paxos_enum.json.FROM.value: process}
    
        except Exception as e:
            print(f"Process {self.process_id}: Error contacting {process} in prepare")
            return {paxos_enum.json.TYPE.value: paxos_enum.acceptor.NO_RESPONSE.value,
                    paxos_enum.json.FROM.value: process}
    
        
    

    async def accept(self, ballot_num: int, accept_val: dict, depth: int) -> bool:
        """
        Phase 2: Send ACCEPT to all acceptors, wait for majority ACCEPTED
        Returns True if majority accepts, False otherwise
    
        Args:
            ballot_num: The ballot number from successful PREPARE phase
            accept_val: The value to propose (from PREPARE phase or new value)
        """
        print(f"Process {self.process_id}: Starting ACCEPT with ballot {ballot_num}, value '{accept_val}'")
    
        # Calculate majority needed
        majority_needed = math.ceil(len(self.external_process_id) / 2)
    
        # Create tasks for all processes
        tasks = {}
        for process in self.external_process_id:
            task = asyncio.create_task(
                self._send_accept_to_process(process, ballot_num, accept_val, depth)
            )
            tasks[process] = task
            self.active_tasks.add(task)
    
        # Wait for majority (or all to finish)
        accepted = []
        completed = 0
        total = len(tasks)
    
        highest_promised_ballot: int = -1
        # Use as_completed to process responses as they arrive
        for coro in asyncio.as_completed(tasks.values()):
            try:
                completed += 1
                result = await coro

            
                from_process = result.get(paxos_enum.json.FROM.value, '')
                if not from_process:
                    raise ValueError(f"Process {self.process_id}: No 'from' in accept response")
            
                # Check if it's a valid dict
                if not isinstance(result, dict):
                    raise ValueError(f"Process {self.process_id}: Non-dict response in accept from {from_process}")
            
                result_type = result.get(paxos_enum.json.TYPE.value)
            
                # Check if it's ACCEPTED
                if result_type == paxos_enum.acceptor.ACCEPT_ACCEPTED.value:
                    accepted.append(result)
                    print(f"Process {self.process_id}: Got accepted #{len(accepted)} from {from_process}")
                
                    # Got majority?
                    if len(accepted) >= majority_needed:
                        print(f"Process {self.process_id}: Got majority accepts ({len(accepted) + 1}/ {len(config.CORRECT_PROCESS_NAMES)})!")
                        break
            
                elif result_type == paxos_enum.acceptor.ACCEPT_REJECT.value:
                    promised_ballot = result.get(paxos_enum.json.PROMISED_BALLOT.value, -1)
                    highest_promised_ballot = max(promised_ballot, highest_promised_ballot)
                    print(f"Process {self.process_id}: Accept rejected by {from_process}, promised_ballot={promised_ballot}")

                elif result_type == paxos_enum.acceptor.NO_RESPONSE.value:
                    print(f"Process {self.process_id} No response from {from_process} in accept")
                else:
                    raise ValueError(f"Got unexpected response from {from_process}: {result_type}")
            
                # Check if it's impossible to get majority
                remaining = total - completed
                if len(accepted) + remaining < majority_needed:
                    print(f"Process {self.process_id}: Can't reach majority in accept, stopping early")
                    break

            except OSError as e:
                task = cast(asyncio.Task, coro)
                print(f"{self.process_id}'s proposer accept phase: Tried connecting to {task.get_name()}, but it is down")

                # Check if it's impossible to get majority (same as above)
                remaining = total - completed
                if len(accepted) + remaining < majority_needed:
                    print(f"Process {self.process_id}: Can't reach majority, stopping early")
                    break

            except Exception as e:
                raise ValueError(f"Process {self.process_id}: Exception in accept: {e}")
        
        # Cancel remaining tasks
        for task in tasks.values():
            self.active_tasks.discard(task)
            if not task.done():
                task.cancel()
    
        # Check if we got majority
        got_majority = len(accepted) >= majority_needed
    
        if got_majority:
            print(f"Process {self.process_id}: ACCEPT succeeded with {len(accepted)} accepts")
            # Store the accepted value
            self.acceptNum = ballot_num
            self.acceptVal = accept_val

            return await self.decision(self.acceptNum, self.acceptVal)
        else:
            self.ballotNum = highest_promised_ballot
            print(f"Process {self.process_id}: ACCEPT failed ({len(accepted)}/{majority_needed})")
    
        return False


    async def _send_accept_to_process(self, process: str, ballot_num: int, accept_val: dict, depth: int) -> dict:
        """
        Send ACCEPT to one process and wait for ACCEPTED/REJECT response
        Handles crashes, timeouts, network failures gracefully
        """
        try:
            port = config.PORT_NUMBERS.get(process)
        
            # Connect with timeout
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=1.0  # 1 second to connect
            )
        
            # Send ACCEPT
            accept_msg = {
                paxos_enum.json.TYPE.value: paxos_enum.proposer.ACCEPT.value,
                paxos_enum.json.BALLOT_NUM.value: ballot_num,
                paxos_enum.json.ACCEPTED_VALUE.value: accept_val,
                paxos_enum.json.FROM.value: self.process_id,
                paxos_enum.json.DEPTH.value: depth
            }
        
            writer.write((json.dumps(accept_msg) + '\n').encode('utf-8'))
            await writer.drain()
        
            # Wait for ACCEPTED/REJECT response with timeout
            response_data = await asyncio.wait_for(
                reader.readline(),
                timeout=config.DELAY + 1
            )
        
            # Close connection
            writer.close()
            await writer.wait_closed()
        
            await asyncio.sleep(config.DELAY) # Wait a certain time
            # Parse response
            if response_data:
                response = json.loads(response_data.decode('utf-8'))
                if not isinstance(response, dict):
                    raise ValueError(f'process {process} should respond with dict')
                return response
            else:
                # Connection closed without response
                print(f"Process {self.process_id}: No response from {process} in accept")
                return {
                    paxos_enum.json.TYPE.value: paxos_enum.acceptor.NO_RESPONSE.value,
                    paxos_enum.json.FROM.value: process
                }
    
        except asyncio.TimeoutError:
            print(f"Process {self.process_id}: Timeout from {process} in accept")
            return {
                paxos_enum.json.TYPE.value: paxos_enum.acceptor.NO_RESPONSE.value,
                paxos_enum.json.FROM.value: process
            }
    
        except Exception as e:
            print(f"Process {self.process_id}: Error contacting {process} in accept")
            return {
                paxos_enum.json.TYPE.value: paxos_enum.acceptor.NO_RESPONSE.value,
                paxos_enum.json.FROM.value: process
            }

    async def decision(self, b: int, v: dict) -> bool:
        """
        The leader then sends out decision messages to all
        the nodes, upon which they append the block to their blockchain and update the balances in the
        local Bank Accounts Table depending on the transaction in the block.
        Reset all variables, make process change its block
        send (“decide”, b, v) to all
        """
        async with self.decision_lock:
            print(f"Process {self.process_id}: Sending DECISION messages with ballot {b}")
    
            # Create tasks for all processes
            tasks = []
            for process in self.external_process_id:
                task = asyncio.create_task(
                    self._send_decision_to_process(process, b, v)
                )
                tasks.append(task)
    
            # Send to all processes (fire and forget - don't wait for responses)
            await asyncio.gather(*tasks, return_exceptions=True)
    
            print(f"Process {self.process_id}: All DECISION messages sent")
    
            # Reset ballot number for next consensus round
            self.ballotNum = -1
    
            return True


    async def _send_decision_to_process(self, process: str, ballot_num: int, value: dict):
        """
        Send DECISION message to one process
        DECISION messages are one-way - no response expected
        """
        try:
            port = config.PORT_NUMBERS.get(process)
        
            # Connect with timeout
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=1.0
            )
        
            # Send DECISION message
            decision_msg = {
                paxos_enum.json.TYPE.value: paxos_enum.proposer.DECISION.value,
                paxos_enum.json.BALLOT_NUM.value: ballot_num,
                paxos_enum.json.ACCEPTED_VALUE.value: value,
                paxos_enum.json.FROM.value: self.process_id
            }
        
            writer.write((json.dumps(decision_msg) + '\n').encode('utf-8'))
            await writer.drain()
        
            # Close connection (no response expected)
            writer.close()
            await writer.wait_closed()
        
            print(f"Process {self.process_id}: Sent DECISION to {process}")
        
        except asyncio.TimeoutError:
            print(f"Process {self.process_id}: Timeout sending DECISION to {process}")
    
        except Exception as e:
            print(f"Process {self.process_id}: Error sending DECISION to {process}: {e}")
    
    async def reset_all(self):
        """
        Should be called after every decision
        """
        print(f"Process {self.process_id}: Resetting proposer state and cancelling tasks")
        
        # Delete any processes running, this ensures no weird bugs
        for task in self.active_tasks:
            if not task.done():
                task.cancel()

        if self.active_tasks:
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

        self.active_tasks.clear()

        self.ballotNum = -1
        self.acceptNum = -1
        self.acceptVal = {}
        self.reset = True
        
        print(f"Process {self.process_id}: Proposer reset complete")


class acceptor:
    BallotNum: int
    AcceptNum: int
    AcceptVal: dict
    process_id: str
    reset: bool # Check if state is clean for recovery algorithm
    def __init__(self, process, outer: paxos) -> None:
        self.outer = outer
        self.process_id = process
        self.BallotNum = -1
        self.AcceptVal = {}
        self.AcceptNum = -1
        self.reset = True

    async def prepare(self, response: dict, depth: int) -> dict:
        """
        Upon receive ("prepare", bal) from i
        if bal > BallotNum then
            BallotNum <- bal
            send ("promise", bal, AcceptNum, AcceptVal) to i
        else
            send ("reject", promised_ballot) to i

        Also if and only if current depth is lower than block's depth then accept
    
        Returns: Dictionary to send back to proposer
        """
        process_from = response.get(paxos_enum.json.FROM.value)
        if not process_from:
            raise ValueError(f"{self.process_id} did not get from in prepare acceptor")
    
        bal = response.get(paxos_enum.json.BALLOT_NUM.value)
        if bal is None:
            raise ValueError(f"{self.process_id} does not have bal, received json from {process_from}")
        
        proposer_depth = response.get(paxos_enum.json.DEPTH.value)
        if proposer_depth is None:
            raise ValueError(f"{self.process_id} got no depth from {process_from}")
        print(f"Current acceptor.prepare\nbal: {bal}\nself.BallotNum: {self.BallotNum}\nproposer_depth: {proposer_depth}\ndepth: {depth}")
        if bal > self.BallotNum and proposer_depth > depth:
            self.reset = False # Transaction can happen from here
            async with self.outer.reset_condition:
                self.outer.reset_condition.notify_all()
            # Accept the prepare - send PROMISE
            self.BallotNum = bal
        
            return {
                paxos_enum.json.TYPE.value: paxos_enum.acceptor.PREPARE_PROMISE.value,
                paxos_enum.json.FROM.value: self.process_id,
                paxos_enum.json.BALLOT_NUM.value: bal,
                paxos_enum.json.ACCEPTED_BALLOT.value: self.AcceptNum,
                paxos_enum.json.ACCEPTED_VALUE.value: self.AcceptVal
            }
        else:
            # Reject the prepare - send REJECT
            return {
                paxos_enum.json.TYPE.value: paxos_enum.acceptor.PREPARE_REJECT.value,
                paxos_enum.json.FROM.value: self.process_id,
                paxos_enum.json.BALLOT_NUM.value: bal,
                paxos_enum.json.PROMISED_BALLOT.value: self.BallotNum
            }
        
    async def accept(self, response: dict, depth: int) -> dict:
        """
        Upon receive ("accept", bal, val) from i
        if bal >= BallotNum then
            BallotNum <- bal
            AcceptNum <- bal
            AcceptVal <- val
            send ("accepted", bal, val) to i
        else
            send ("reject", promised_ballot) to i
    
        Returns: Dictionary to send back to proposer
        """
        process_from = response.get(paxos_enum.json.FROM.value)
        if not process_from:
            raise ValueError(f"{self.process_id} did not get from in accept acceptor")
    
        bal = response.get(paxos_enum.json.BALLOT_NUM.value)
        if bal is None:
            raise ValueError(f"{self.process_id} does not have bal in accept, from {process_from}")
    
        val = response.get(paxos_enum.json.ACCEPTED_VALUE.value)
        if val is None:
            raise ValueError(f"{self.process_id} does not have value in accept, from {process_from}")
    
        proposer_depth = response.get(paxos_enum.json.DEPTH.value)
        if proposer_depth is None:
            raise ValueError(f"{self.process_id} got no depth from {process_from}")

        if bal >= self.BallotNum and proposer_depth > depth:  # if it's > then it wouldn't accept its previous value
            # Accept the value
            self.BallotNum = bal
            self.AcceptNum = bal
            self.AcceptVal = val
        
            print(f"Process {self.process_id}: ACCEPTED ballot {bal}, value (full blockchain not just block): '{val}'")
        
            return {
                paxos_enum.json.TYPE.value: paxos_enum.acceptor.ACCEPT_ACCEPTED.value,
                paxos_enum.json.FROM.value: self.process_id,
                paxos_enum.json.BALLOT_NUM.value: bal,
                paxos_enum.json.ACCEPTED_VALUE.value: val,
            }
        else:
            # Reject the accept
            print(f"Process {self.process_id}: REJECTED accept ballot {bal}, promised {self.BallotNum}")
        
            return {
                paxos_enum.json.TYPE.value: paxos_enum.acceptor.ACCEPT_REJECT.value,
                paxos_enum.json.FROM.value: self.process_id,
                paxos_enum.json.BALLOT_NUM.value: bal,
                paxos_enum.json.PROMISED_BALLOT.value: self.BallotNum
            }
        
    def reset_all(self):
        """
        Called after decision
        """

        self.BallotNum = -1
        self.AcceptNum = -1
        self.AcceptVal = {}
        self.reset = True
        
class paxos:
    def __init__(self, process_name: str):
        if process_name not in config.CORRECT_PROCESS_NAMES:
            raise ValueError('Incorrect process name')
        self.process = process_name
        self.external_processes = [process for process in config.CORRECT_PROCESS_NAMES if process != self.process]
        self.proposer = proposer(self.process, self.external_processes, outer=self)
        self.acceptor = acceptor(self.process, outer=self)
        self.filename = config.CORRECT_FILE_NAMES_DICT.get(self.process)
        if not self.filename: raise ValueError("self.filename is None")
        self.blockchain: block.Block | None = block.Block.load_from_json(self.filename)  # Current blockchain
        self.bankaccount: bank_account.Bank_Account = bank_account.Bank_Account(self.blockchain) # Initialized bank account
        self.decision_lock = asyncio.Lock()  # Prevent concurrent decision processing
        self.proposer_lock = asyncio.Lock()  # Prevent concurrent decision processing
        self.transaction_queue = deque()
        self.reset_condition = asyncio.Condition()
        
    async def _reboot(self):
        if len(sys.argv) > 2:
            raise ValueError('There should only be at max one argument')
        elif len(sys.argv) == 2:
            if sys.argv[1] == 'fix':
                print('========= Initiating recovery algorithm (runs when master calls fix) ============')
                await self.recovery_algorithm()
            else:
                raise ValueError(f'Unknown argument: {sys.argv[1]}')
        else:
            await self._first_time_recovery()

    async def _first_time_recovery(self):
        """
        Handles recovery when first initiated
        """
        print("================= Initiating FIRST time recovery algorithm (runs only on start up) =======================")
        port = config.PORT_NUMBERS.get(self.process)
        if not port:
            raise ValueError(f"No port configured for process {self.process}")

        server = await asyncio.start_server(
            self._listen_first_time,
            'localhost',
            port
        )

        async with server:
            # Run serving in background
            serve_task = asyncio.create_task(server.serve_forever())

            # Recovery logic (runs concurrently with server)
            await asyncio.sleep(config.DELAY)
            print(f"{self.process}: sending recovery msg to all processes")
            tasks = {}
            for process in self.external_processes:  # Exclude self
                task = asyncio.create_task(
                    self._send_with_response(process,
                        {
                            paxos_enum.json.TYPE.value: paxos_enum.json.FIRST_RECOVERY.value,
                        },
                    ), name=process
                )
                tasks[process] = task

            timeout = 0  # If timeout is 4 abort
            biggest_block_chain = self.blockchain
            biggest_block_chain_length = 0
            if biggest_block_chain:
                biggest_block_chain_length = biggest_block_chain.length()

            recovered = False
            await asyncio.sleep(config.DELAY) # Make sure it receives msg
            for coro in asyncio.as_completed(tasks.values()):
                try:
                    result = await coro
                    from_process = result.get('from')
                    if not from_process:
                        raise ValueError('No from_process in recovery algorithm')
                    if result.get('empty'):
                        print(f'Could not connect to {from_process}, continuing first time recovery algorithm')
                        continue
                    blockchain_dict = result.get('blockchain')
                    new_blockchain = block.Block._blockchain_from_json(blockchain_dict)
                    if not new_blockchain:
                        print(f"No blockchain has been found from {from_process}, continuing first time recovery algorithm")
                        continue
                    blockchain_length = new_blockchain.length()
                    print(f"blockchain found from {from_process} with length {blockchain_length}")
                    if blockchain_length < biggest_block_chain_length:
                        print(f"blockchain from {from_process} has less length than max: {blockchain_length} < {biggest_block_chain_length}")
                    else:
                        biggest_block_chain_length = blockchain_length
                        biggest_block_chain = new_blockchain
                        print(f"New blockchain found from {from_process} with length {biggest_block_chain_length}")
                        recovered = True

                except ValueError:
                    task = cast(asyncio.Task, coro)
                    print(f"{self.process}: Tried connecting to {task.get_name()}, but timed out, continuing algorithm")
                    timeout += 1
                except OSError as e:
                    task = cast(asyncio.Task, coro)
                    print(f"{self.process}: Tried connecting to {task.get_name()}, but it is down, continuing recovery algorithm")
                except Exception as e:
                    task = cast(asyncio.Task, coro)
                    print(f"{self.process}: Error from {task.get_name()}: {e}, continuing")  # Continue instead of raise

            if timeout == 4:
                print("All processes timedout when trying to retrieve their blockchain, shutting down process")
                sys.exit(0)

            if not biggest_block_chain:
                print(f"All blockchains were empty, starting normally")
            elif recovered:
                print(f"Changing current blockchain to length {biggest_block_chain_length}")
                self.update_blockchain(biggest_block_chain)
            else:
                print("No valid blockchain recovered, starting normally")

            # Shutdown server after recovery
            print(f"Process {self.process}: Recovery complete, terminating first-time listener...")
            serve_task.cancel()
            try:
                await serve_task
            except asyncio.CancelledError:
                pass
            server.close()
            await server.wait_closed()
            print(f"Process {self.process}: First-time listener terminated.")
        


    async def _listen_first_time(self, reader, writer):
        try:
            # Read incoming message
            data = await reader.readline()
            
            if not data:
                print(f"Process {self.process}: Received empty message")
                return
            
            # "All message exchanges should have a constant delay (e.g., 3 seconds)."
            await asyncio.sleep(config.DELAY)

            # Parse message
            message = json.loads(data.decode('utf-8'))
            message_type = message.get(paxos_enum.json.TYPE.value)
            from_process = message.get(paxos_enum.json.FROM.value, 'unknown')
            blockchain_dict = None
            if self.blockchain:
                blockchain_dict = self.blockchain.to_json()

            print(f"Process {self.process}: Received {message_type} from {from_process}, message: {message}")


            # Listen
            if from_process == 'master':
                response = {
                    'from' : self.process,
                    'first' : True
                }
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                print(f"Sending response: {response}")
                await writer.drain()
            elif message_type == paxos_enum.json.FIRST_RECOVERY.value:
                response = {
                    'from' : self.process,
                    'blockchain' : blockchain_dict
                }
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                print(f"Sending response: {response}")
                await writer.drain()

            else:
                await writer.drain() # Send empty msg


        except json.JSONDecodeError as e:
            print(f"Process {self.process}: Invalid JSON received: {e}")
        
        except Exception as e:
            print(f"Process {self.process}: Error handling message: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Always close the connection
            writer.close()
            await writer.wait_closed()
    async def recovery_algorithm(self):
        """
        FAIL/ recovery, make this process in limbo while waiting, 
        sends messages to all processes asking for their blockchain
        first process that does not have any acceptval or ballot in both proposer and acceptor (guarantees safety)
        will send back its block chain for this process to update, will ignore every future response from other processes
        """

        print(f"{self.process}: sending recovery msg to all processes")
        tasks = {}
        for process in self.external_processes:
            task = asyncio.create_task(
                self._send_with_response(process,
                            { 
                                paxos_enum.json.TYPE.value: paxos_enum.json.RECOVERY.value,

                            },
                            ), name= process
            )
            tasks[process] = task

        timeout = 0 # If timeout is 4 abort
        for coro in asyncio.as_completed(tasks.values()):
            try:
                result = await coro
                from_process = result.get('from')
                if not from_process:
                    raise ValueError('No from_process in recovery algorithm')
                empty = result.get('empty')
                if empty:
                    print(f'Could not connect to {from_process}, continuing recovery algorithm')
                    continue

                blockchain_dict = result.get('blockchain')
                new_blockchain = block.Block._blockchain_from_json(blockchain_dict)
                if not new_blockchain:
                    print(f"No blockchain has been found from {from_process}, continuing recovery algorithm")
                    continue
                print(f"blockchain found, initiating recovery for blockchain: {new_blockchain}")
                self.update_blockchain(new_blockchain)
                print("------------- BLOCK RECOVERED -----------------")
                return
            
            except ValueError:
                task = cast(asyncio.Task, coro)
                print(f"{self.process}: Tried connecting to {task.get_name()}, but timed out, continuing algorithm")
                timeout += 1
            except OSError as e:
                task = cast(asyncio.Task, coro)
                print(f"{self.process}: Tried connecting to {task.get_name()}, but it is down, continuing recovery algorithm")

            except Exception as e:
                raise ValueError(f"{self.process}: Exception in accept: {e}")
        
        if timeout == 4:
            print("All processes timedout when trying to retrieve their blockchain, shutting down process")
            sys.exit(0)
        print("All other processes are down or do not have blockchain, starting normally")


    async def start_server(self):
        """
        Start server to listen for incoming Paxos messages
        """
        await self._reboot()
        port = config.PORT_NUMBERS.get(self.process)
        
        if not port:
            raise ValueError(f"No port configured for process {self.process}")
        
        server = await asyncio.start_server(
            self._handle_client,
            'localhost',
            port
        )
        
        print(f"Process {self.process}: Server listening on port {port}")
        
        async with server:
            await server.serve_forever()

    async def _handle_client(self, reader, writer):
        """
        Handle incoming Paxos messages (as acceptor)
        Routes messages to appropriate acceptor methods
        """
        try:
            # Read incoming message
            data = await reader.readline()
            
            if not data:
                print(f"Process {self.process}: Received empty message")
                return
            
            # "All message exchanges should have a constant delay (e.g., 3 seconds)."
            await asyncio.sleep(config.DELAY)

            # Parse message
            message = json.loads(data.decode('utf-8'))
            message_type = message.get(paxos_enum.json.TYPE.value)
            from_process = message.get(paxos_enum.json.FROM.value, 'unknown')
            
            print(f"Process {self.process}: Received {message_type} from {from_process}, message: {message}")
            
            ############## Acceptor ####################
            # Route to appropriate handler
            depth = self.blockchain.length() if self.blockchain else 0
            if message_type == paxos_enum.proposer.PREPARE.value:
                response = await self.acceptor.prepare(message, depth)
                
                # Need to send response back
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                print(f"Sending response: {response}")
                await writer.drain()
            
            elif message_type == paxos_enum.proposer.ACCEPT.value:
                response = await self.acceptor.accept(message, depth)
                
                temp_block = block.Block._blockchain_from_json(self.acceptor.AcceptVal)
                if not temp_block:
                    raise ValueError(f"For process {self.process}, temp_block is None")
                self.update_blockchain(temp_block, True) # if the node is a participant, when it receives a block from the leader it needs to write the block to the file and tag is as tentative.
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                print(f"Sending response: {response}")
                await writer.drain()
            
            elif message_type == paxos_enum.proposer.DECISION.value:
                await self.handle_decision(message)
                # No response for DECISION messages
            
            elif message_type == paxos_enum.json.RECOVERY.value:
                await self.handle_recovery(message, writer)

            ################ Master ###############

            elif message_type == transaction.enum_transaction.TRANSACTION.value:
                trans_dict = message.get(transaction.enum_transaction.TRANSACTION.value)
                msg_transaction: transaction.Transaction = transaction.Transaction(**trans_dict)
                self.transaction_queue.append(msg_transaction)
                await self.handle_transaction()

            elif message_type == transaction.enum_transaction.PRINT_BLOCKCHAIN.value:
                blockchain_dict: dict
                if not self.blockchain:
                    blockchain_dict = {}
                else:
                    blockchain_dict = self.blockchain.to_json()

                response = {
                    "blockchain" : blockchain_dict
                }
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                await writer.drain()

            elif message_type == transaction.enum_transaction.PRINT_BALANCE.value:
                balance: str = self.bankaccount.get_balances_string()
                response: dict = {
                    paxos_enum.json.FROM.value: self.process,
                    transaction.enum_transaction.PRINT_BALANCE.value: balance
                }

                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                await writer.drain()

            elif message_type == transaction.enum_transaction.FAIL_PROCESS.value:
                print("Received fail process, shutting down")
                sys.exit(0)

            elif message_type == transaction.enum_transaction.QUEUE.value:
                queue_list = [transaction.asdict(t) for t in self.transaction_queue]
                response = {
                    "from": self.process,
                    "queue": queue_list
                }
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                await writer.drain()
            elif message_type == transaction.enum_transaction.QUEUE_START.value:
                await self.handle_transaction()
            elif message_type == transaction.enum_transaction.QUEUE_DELETE.value:
                self.transaction_queue.clear()
            else:
                raise ValueError(f"Process {self.process}: Unknown message type: {message}")
        
        except json.JSONDecodeError as e:
            print(f"Process {self.process}: Invalid JSON received: {e}")
        
        except Exception as e:
            print(f"Process {self.process}: Error handling message: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Always close the connection
            writer.close()
            await writer.wait_closed()

    async def handle_recovery(self, message: dict, writer):
        """
        Only send back blockchain when proposer and acceptor values are clean (initially started with), this is to ensure safety (not sending a blockchain right before a decision)
        """
        from_process = message.get(paxos_enum.json.FROM.value)
        if not from_process:
            raise ValueError('Did not receive from_process in handle_recovery')

        async with self.reset_condition:
            while not (self.proposer.reset and self.acceptor.reset):
                await self.reset_condition.wait()

        # Now it's safe (both resets are True) - proceed to send
        blockchain_dict = None
        if self.blockchain:
            blockchain_dict = self.blockchain.to_json()

        response = {
            paxos_enum.json.FROM.value: self.process,
            'blockchain': blockchain_dict
        }
        writer.write((json.dumps(response) + '\n').encode('utf-8'))
        print(f"Sending response: {response}")
        await writer.drain()

        
    async def handle_decision(self, message: dict):
        """
        Process DECISION message - update local blockchain
        Protected by lock to prevent concurrent updates
        """
        async with self.decision_lock:
            ballot_num = message.get(paxos_enum.json.BALLOT_NUM.value)
            blockchain_dict: dict = message.get(paxos_enum.json.ACCEPTED_VALUE.value, {})
            if not blockchain_dict:
                raise ValueError(f"{self.process}, blockchain_dict did not exist")
            from_process = message.get(paxos_enum.json.FROM.value)
            
            print(f"Process {self.process}: Processing DECISION from {from_process}, ballot {ballot_num}")
            
            new_blockchain = block.Block._blockchain_from_json(blockchain_dict)
            
            if new_blockchain is None:
                raise ValueError(f"Process {self.process}: Failed to parse blockchain from DECISION")
            
            self.update_blockchain(new_blockchain, False)
            
            
            # Need to reset everything after decision
            await self.reset_all()

    async def handle_transaction(self):
        """
        Check queue and try to propose message with retry on failure.
        """
        while True:  # Loop for retries
            async with self.proposer_lock:
                if not self.transaction_queue:
                    print('Queue is empty, returning')
                    return  # Exit if queue is empty (no more work)
                
                success = await self.propose_block()
                if success:
                    print('Success in proposing loop')
            # Retry logic outside the lock to avoid re-acquiring while held
            sleep_time = config.DELAY * 5 + config.DELAY * 3 * random.random() # Random sleep time to ensure termination of paxos
            print(f"{self.process} out of loop, will wait {sleep_time}\nCurrent transaction queue {self.transaction_queue}")
            await asyncio.sleep(sleep_time)


    async def propose_block(self) -> bool:
        """
        Propose a new block using Paxos consensus TODO make this better
        """
        transaction: transaction.Transaction = self.transaction_queue[0]

        # Check if bank account has funds
        # "Once a block is decided on disk, a transfer operation in the block is executed on the Bank Accounts Table"
        if self.bankaccount.get_balance(transaction.sender_id) < transaction.amount:
            print(f"{transaction.sender_id} DOES NOT HAVE THE FUNDS TO MAKE TRANSACTION OF {transaction.amount} TO {transaction.receiver_id}")
            self.transaction_queue.popleft() # Transaction is nullified
            return True
        
        print(f"Process {self.process}: Proposing new block with transaction {transaction}")
        
        if not self.blockchain:
            print(f"${self.process} has blockchain as none")
        success = await self.proposer.prepare(transaction, self.blockchain)
        
        if success:
            print(f"Process {self.process}: Block proposal succeeded! ✅✅✅")
            if self.transaction_queue:
                self.transaction_queue.popleft() # Remove transaction
            accepted_dict = self.proposer.acceptVal
            if not accepted_dict: 
                raise ValueError('AcceptVal is none')
            accepted_block: block.Block | None = block.Block._blockchain_from_json(accepted_dict)
            if not accepted_block:
                raise ValueError('accepted_block is None')
            self.update_blockchain(accepted_block, tentative=False)
            await self.reset_all()
        else:
            print(f"Process {self.process}: Block proposal failed ❌❌❌")
        
        return success

    def update_blockchain(self, new_blockchain: block.Block, tentative: bool = False):
        # Check if this is newer than what we have
        if self.blockchain:
            current_length = self.blockchain.length()
            new_length = new_blockchain.length()
                
            if new_length < current_length:
                print("old block chain: \n " + json.dumps(self.blockchain.to_json()))
                print("new block chain: \n " + json.dumps(new_blockchain.to_json()))

                raise ValueError(f"Process {self.process}: received blockchain less than current")
                
            print(f"Process {self.process}: Updating blockchain from length {current_length} to {new_length}")
        else:
            print(f"Process {self.process}: Initializing blockchain with length {new_blockchain.length()}")
            
        # Update blockchain
        self.blockchain = new_blockchain
        self.bankaccount = bank_account.Bank_Account(self.blockchain) # "Once a block is decided on disk, a transfer operation in the block is executed on the Bank Accounts Table"
        print(f"Process {self.process}: Blockchain updated! New length: {self.blockchain.length()}")
            
        # Save to disk
        try:
            filename = config.CORRECT_FILE_NAMES_DICT.get(self.process)
            if not filename:
                raise ValueError(f'Can not find filename for process {self.process}')
            self.blockchain.write_to_json(filename, tentative)
        except Exception as e:
            raise ValueError(f"Process {self.process}: Error saving blockchain: {e}")

    async def reset_all(self):
        await self.proposer.reset_all()
        self.acceptor.reset_all()

        async with self.reset_condition:
            self.reset_condition.notify_all()

    async def _send_with_response(self, process: str, msg_dict: dict) -> dict:
        try:
            await asyncio.sleep(config.DELAY) # initiate fake delay
            port = config.PORT_NUMBERS.get(process)
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('localhost', port),
                timeout=1.0
            )
            msg_dict['from'] = self.process
            writer.write((json.dumps(msg_dict) + '\n').encode('utf-8'))
            await writer.drain()
            print(f"{self.process}: Sent msg to process {process}: {msg_dict}")
            response_data = await asyncio.wait_for(
                reader.readline(),
                timeout= config.DELAY * 10 # This is only for recovery algorithm, if this actually happens it's cooked
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
                print(f"{self.process} did not receive response from: {process}")
                return {'from': process, 'empty': True}
        except asyncio.TimeoutError:
            raise ValueError(f"{self.process}: Timed out in sending to {process}")
        except OSError as e:
            print(f"Failed to connect to {process}, probably crashed")
            return {'from': process, 'empty': True}
        except Exception as e:
            raise ValueError(f"{self.process}: Error sending to {process}: {e}")
