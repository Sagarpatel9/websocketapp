import asyncio
import websockets

async def chat_client():
    uri = "ws://localhost:9000"
    
    while True:  # Reconnection attempt
        try:
            #establish connection with the websocket server
            async with websockets.connect(uri) as websocket:
                username = await asyncio.to_thread(input, "Enter username: ")
                password = await asyncio.to_thread(input, "Enter password: ")
                
                #send login credentials to the server
                await websocket.send(username)
                await websocket.send(password)

                #wait for auth response from server
                auth_response = await websocket.recv()
                print(auth_response)

                #if auth fails, then exit the program
                if "failed" in auth_response.lower():
                    return  
                
                #Define an asynchronous function to receive and print messages from server.
                async def receive_messages():
                    while True:
                        try:
                            response = await websocket.recv()
                            if response.startswith("USERS:"):
                                users = response[6:].split(",")
                                print("\nOnline Users:")
                                for user in users:
                                    if user.strip():
                                        print(f"- {user}")  
                                print("\n")
                            else:
                                print(response)  
                        except websockets.exceptions.ConnectionClosed:
                            print("Disconnected. Attempting to reconnect...")
                            break  

                # Start receiving messages in the background while user can still type.
                asyncio.create_task(receive_messages())

                # Main loop for sending messages
                while True:
                    message = await asyncio.to_thread(input, "> ")
                    if message.lower() == "exit":
                        print("Exiting chat...")
                        await websocket.send("disconnecting")
                        await websocket.close()
                        return
                    await websocket.send(message)

        except Exception as e:
            print(f"Error: {e}")
            print("Attempt to reestablish connections in 5 seconds...")
            await asyncio.sleep(5)  # Have a five second period before attempting again

asyncio.run(chat_client())