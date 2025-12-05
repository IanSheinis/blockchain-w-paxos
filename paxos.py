import json
import config
from enum import Enum
import asyncio
import json
import math
class paxos_enum():
    class proposer(Enum):
        PREPARE = 'PREPARE'
        ACCEPT = 'ACCEPT'
        DECISION = 'DECISION'
    class acceptor(Enum):
        PREPARE_REJECT = 'PREPARE_REJECT'
        PREPARE_PROMISE = 'PREPARE_PROMISE'
        NO_RESPONSE = 'NO_RESPONSE'
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
        BALLOT_NUM = 'ballot_num'
        ACCEPTED_BALLOT = 'accepted_ballot'
        ACCEPTED_VALUE = 'accepted_value'
        PROMISED_BALLOT = 'promised_ballot'

class proposer:
    # Prepare variables
    ballotNum: int # If -1 then it is not currently trying to be leader
    # Accept variables
    acceptNum: int
    acceptVal: str
    val: str #Val trying to be sent
    def __init__(self, process, external_process) -> None:
        self.process_id: str = process
        self.external_process_id: list[str] = external_process
        self.ballotNum = -1

    async def prepare(self) -> bool:
        """
        Phase 1: Send PREPARE to all acceptors, wait for majority PROMISE
        Returns as soon as majority is reached (doesn't wait for all)
        """
        self.ballotNum += 1
    
        print(f"Process {self.process_id}: Starting PREPARE with ballot {self.ballotNum}")
    
        # Calculate majority needed
        majority_needed = math.ceil(len(self.external_process_id) / 2)
    
        # Create tasks for all processes
        tasks = {}
        for process in self.external_process_id:
            task = asyncio.create_task(
                self._send_prepare_to_process(process, self.ballotNum)
            )
            tasks[process] = task
    
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
                print(f"Process {self.process_id}: Exception in prepare: {e}")
                completed += 1
    
        # Cancel remaining tasks (they're still running in background)
        for task in tasks.values():
            if not task.done():
                task.cancel()
    
        # Check if we got majority
        got_majority = len(promises) >= majority_needed
    
        if got_majority:
            print(f"Process {self.process_id}: PREPARE succeeded with {len(promises)} promises")
        
            # incorporate (AcceptNum, AcceptVal) logic from acceptors
            acceptNum: int = -1
            acceptVal: str = ""
            for promise in promises:
                promise_from = promise.get(paxos_enum.json.FROM.value)
                promise_acceptNum = promise.get(paxos_enum.json.ACCEPTED_BALLOT.value, -1)
                promise_acceptVal: str = promise.get(paxos_enum.json.ACCEPTED_VALUE.value, '')
                if promise_acceptNum > acceptNum:
                    acceptNum = promise_acceptNum
                    acceptVal = promise_acceptVal

            # TODO self.accept(acceptNum + 1, acceptVal)
        else:
            print(f"Process {self.process_id}: PREPARE failed ({len(promises)}/{majority_needed})\n Highest ballot received: {max_seen_ballot}")
            self.ballotNum = max_seen_ballot
    
        return got_majority


    async def _send_prepare_to_process(self, process: str, ballot_num: int) -> dict:
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
            paxos_enum.json.FROM.value: self.process_id
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
    
        
    

    def accept(self) -> None:
        """
        Before it can propose the block, the node should compute the acceptable hash value (the last
        character of the hash must be a digit between 0 and 4) by finding an appropriate nonce. Note
        that if a process takes too long to compute the acceptable hash, another process might time
        out and start leader election

        Once the node becomes a leader after performing the last two steps, it proposes the block using
        accept messages. After a majority of nodes accept the block, the leader appends the block to its
        chain, updates the local Bank Accounts Table.

        If nodes come back w/ an accept value then use that accept value
        """

    def decision(self) -> None:
        """
        The leader then sends out decision messages to all
        the nodes, upon which they append the block to their blockchain and update the balances in the
        local Bank Accounts Table depending on the transaction in the block.
        """

class acceptor:
    BallotNum: int
    AcceptVal: str

    def __init__(self) -> None:
        pass

    def prepare(self) -> None:
        """
        Upon receive (“prepare”, bal) from i
        if bal >= BallotNum then
        BallotNum <- bal
        send (“promise”, bal, AcceptNum, AcceptVal) to i
        """
        
class paxos:
    def __init__(self, process_name: str):
        if process_name not in config.CORRECT_FILE_NAMES:
            raise ValueError('Incorrect process name')
        self.process = process_name
        self.external_processes = [process for process in config.CORRECT_PROCESS_NAMES if process != self.process]
        self.proposer = proposer(self.process, self.external_processes)
        self.acceptor = acceptor()
