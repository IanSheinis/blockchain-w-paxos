import asyncio
import json

async def handle_client(reader, writer, proccess_name): # TODO implement logic for all processes
    """This function is called when a client connects"""
    
    # Keep reading data as it arrives
    while True:
        data = await reader.readline()  # Wait for data
        
        if not data:
            break  # Connection closed
        
        # Manipulate the data here!
        message = json.loads(data.decode('utf-8'))
        print(f"Received: {message}")
        
        # Do something with it
        response = {"status": "received", "echo": message}
        
        # Send response
        writer.write((json.dumps(response) + '\n').encode('utf-8'))
        await writer.drain()
    
    writer.close()
    await writer.wait_closed()