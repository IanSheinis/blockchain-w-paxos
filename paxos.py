import json
import queue
import config
from enum import Enum
import asyncio
import json
import math
import block
import transaction
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

class proposer:
    # Prepare variables
    ballotNum: int # If -1 then it is not currently trying to be leader
    acceptNum: int
    acceptVal: dict
    def __init__(self, process, external_process) -> None:
        self.process_id: str = process
        self.external_process_id: list[str] = external_process
        self.ballotNum = -1
        self.acceptNum = -1
        self.acceptVal = {}
        self.active_tasks: set[asyncio.Task] = set()
        self.decision_lock = asyncio.Lock()  # Prevent concurrent decision processing

    async def prepare(self, transaction: transaction.Transaction, current_blockchain: block.Block) -> bool:
        """
        Phase 1: Send PREPARE to all acceptors, wait for majority PROMISE
        Returns as soon as majority is reached (doesn't wait for all)
        """
        self.ballotNum += 1
    
        print(f"Process {self.process_id}: Starting PREPARE with ballot {self.ballotNum}")
    
        # Calculate majority needed
        majority_needed = math.ceil(len(self.external_process_id) / 2)
    
        depth = current_blockchain.length()
        # Create tasks for all processes
        tasks = {}
        for process in self.external_process_id:
            task = asyncio.create_task(
                self._send_prepare_to_process(process, self.ballotNum, depth)
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
                result = await coro
                completed += 1

                from_process = result.get(paxos_enum.json.FROM.value, '')
                if not from_process:
                    raise ValueError(f'No from for process: {self.process_id}')
                # Check if it's a valid PROMISE
                if isinstance(result, dict):
                    if result.get(paxos_enum.json.TYPE.value) == paxos_enum.acceptor.PREPARE_PROMISE.value:
                        promises.append(result)
                        print(f"Process {self.process_id}: Got promise #{len(promises)} from {from_process}")
                
                        if len(promises) >= majority_needed:
                            print(f"Process {self.process_id}: Got majority ({len(promises)}/{majority_needed})!")
                            break

                    if result.get(paxos_enum.json.TYPE.value) == paxos_enum.acceptor.PREPARE_REJECT.value:
                        promise_ballot = int(result.get(paxos_enum.json.PROMISED_BALLOT.value,-1)) #type error if no -1
                        if promise_ballot == -1:
                            raise ValueError(f"Process {self.process_id}: should not be -1 here")
                        max_seen_ballot = max(promise_ballot, max_seen_ballot)
                else:
                    raise ValueError(f"Process {self.process_id} did not receive a dict in proposer prepare")
            
                # Check if it's impossible to get majority
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
            accept_success: bool = await self.accept(self.ballotNum, acceptVal, depth)
            if accept_success: 
                return accept_success # Bool chain
            else:
                print(f"{self.process_id} failed to propose accept, new ballot number is: {self.ballotNum}")
                return False
        else:
            print(f"Process {self.process_id}: PREPARE failed ({len(promises)}/{majority_needed})\n Highest ballot received: {max_seen_ballot}")
            self.ballotNum = max_seen_ballot
    
        return False


    async def _send_prepare_to_process(self, process: str, ballot_num: int, depth: int) -> dict:
        """
        Send PREPARE to one process and wait for PROMISE response
        Handles crashes, timeouts, network failures gracefully
        """
        
        port = config.PORT_NUMBERS.get(process)
        
        # Connect with timeout
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection('localhost', port),
            timeout=1.0  # 1 second to connect
        )
        
        # Send PREPARE
        prepare_msg = {
            paxos_enum.json.TYPE.value : paxos_enum.proposer.PREPARE.value,
            paxos_enum.json.BALLOT_NUM.value : ballot_num,
            paxos_enum.json.FROM.value: self.process_id,
            paxos_enum.json.DEPTH.value: depth
        }
        
        writer.write((json.dumps(prepare_msg) + '\n').encode('utf-8'))
        await writer.drain()
        
        # Wait for PROMISE response with timeout
        response_data = await asyncio.wait_for(
            reader.readline(),
            timeout= config.DELAY + 1
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
            print(f"Process {self.process_id}: No response from {process}")
            return {paxos_enum.json.TYPE.value:
                    paxos_enum.acceptor.NO_RESPONSE.value,
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
                result = await coro
                completed += 1
            
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
                        print(f"Process {self.process_id}: Got majority accepts ({len(accepted)}/{majority_needed})!")
                        break
            
                elif result_type == paxos_enum.acceptor.ACCEPT_REJECT.value:
                    promised_ballot = result.get(paxos_enum.json.PROMISED_BALLOT.value, -1)
                    highest_promised_ballot = max(promised_ballot, highest_promised_ballot)
                    print(f"Process {self.process_id}: Accept rejected by {from_process}, promised_ballot={promised_ballot}")

                else:
                    raise ValueError(f"Got unexpected response from {from_process}: {result_type}")
            
                # Check if it's impossible to get majority
                remaining = total - completed
                if len(accepted) + remaining < majority_needed:
                    print(f"Process {self.process_id}: Can't reach majority in accept, stopping early")
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
            print(f"Process {self.process_id}: Error contacting {process} in accept: {e}")
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
        
        print(f"Process {self.process_id}: Proposer reset complete")


class acceptor:
    BallotNum: int
    AcceptNum: int
    AcceptVal: dict
    process_id: str
    def __init__(self, process) -> None:
        self.process_id = process
        self.BallotNum = -1
        self.AcceptVal = {}
        self.AcceptNum = -1

    def prepare(self, response: dict, depth: int) -> dict:
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

        if bal > self.BallotNum and proposer_depth > depth:
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
        
    def accept(self, response: dict, depth: int) -> dict:
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
        
            print(f"Process {self.process_id}: ACCEPTED ballot {bal}, value '{val}'")
        
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
        
class paxos:
    def __init__(self, process_name: str):
        if process_name not in config.CORRECT_FILE_NAMES:
            raise ValueError('Incorrect process name')
        self.process = process_name
        self.external_processes = [process for process in config.CORRECT_PROCESS_NAMES if process != self.process]
        self.proposer = proposer(self.process, self.external_processes)
        self.acceptor = acceptor(self.process)
        self.blockchain: block.Block | None = None  # Current blockchain
        self.decision_lock = asyncio.Lock()  # Prevent concurrent decision processing
        self.transaction_queue = queue.Queue() # TODO incorporate proposer logic and have queue added when master sends a request, and removed when proposer makes decision. Make sure to incorporate random waits when retrying. Makesure proposer blockchain is updated too
    
    async def start_server(self):
        """
        Start server to listen for incoming Paxos messages
        """
        port = config.PORT_NUMBERS.get(self.process)
        
        if not port:
            raise ValueError(f"No port configured for process {self.process}")
        
        server = await asyncio.start_server(
            self.handle_client,
            'localhost',
            port
        )
        
        print(f"Process {self.process}: Server listening on port {port}")
        
        async with server:
            await server.serve_forever()

    async def handle_client(self, reader, writer):
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
            
            # Parse message
            message = json.loads(data.decode('utf-8'))
            message_type = message.get(paxos_enum.json.TYPE.value)
            from_process = message.get(paxos_enum.json.FROM.value, 'unknown')
            
            print(f"Process {self.process}: Received {message_type} from {from_process}")
            
            ### Acceptor ###
            # Route to appropriate handler
            depth = self.blockchain.length() if self.blockchain else 0
            if message_type == paxos_enum.proposer.PREPARE.value:
                response = self.acceptor.prepare(message, depth)
                
                # Need to send response back
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                await writer.drain()
            
            elif message_type == paxos_enum.proposer.ACCEPT.value:
                response = self.acceptor.accept(message, depth)
                
                writer.write((json.dumps(response) + '\n').encode('utf-8'))
                await writer.drain()
            
            elif message_type == paxos_enum.proposer.DECISION.value:
                await self.handle_decision(message)
                # No response for DECISION messages
            
            ### Master ###
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
            
            # Check if this is newer than what we have
            if self.blockchain:
                current_length = self.blockchain.length()
                new_length = new_blockchain.length()
                
                if new_length <= current_length:
                    print("old block chain: \n " + json.dumps(self.blockchain.to_json()))
                    print("new block chain: \n " + json.dumps(new_blockchain.to_json()))

                    raise ValueError(f"Process {self.process}: received desision less than current")
                
                print(f"Process {self.process}: Updating blockchain from length {current_length} to {new_length}")
            else:
                print(f"Process {self.process}: Initializing blockchain with length {new_blockchain.length()}")
            
            # Update blockchain
            self.blockchain = new_blockchain
            
            print(f"Process {self.process}: Blockchain updated! New length: {self.blockchain.length()}")
            
            # Save to disk
            try:
                self.blockchain.write_to_json(self.process)
            except Exception as e:
                raise ValueError(f"Process {self.process}: Error saving blockchain: {e}")
            
            # Need to reset everything after decision
            await self.reset_all()

    async def propose_block(self, transaction: transaction.Transaction) -> bool:
        """
        Propose a new block using Paxos consensus
        """
        print(f"Process {self.process}: Proposing new block")
        
        if not self.blockchain:
            raise ValueError(f"{(self.process)} does not have a blockchain")
        success = await self.proposer.prepare(transaction, self.blockchain)
        
        if success:
            print(f"Process {self.process}: Block proposal succeeded!")
        else:
            print(f"Process {self.process}: Block proposal failed")
        
        return success

    async def reset_all(self):
        await self.proposer.reset_all()
        self.acceptor.reset_all()
