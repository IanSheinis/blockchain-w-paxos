# Simulated Blockchain

This project implemented a blockchain across five different processes which communicate through the paxos consensus protocol.

## Testing Instructions

Here are the available make commands for testing:

- **make start**: Start up the five processes and master; processes' stdout is logged in `logs/`.
- **make stop**: Kill the five processes and master.
- **make clean**: Clean all logs and JSON files.

To test it out, run `make start` in the root directory.