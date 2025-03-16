import asyncio
import websockets
import time
import signal
import sys
import secrets

connected_users = {}
stored_users = {
    "user1": "ABC123",
    "user2": "XYZ789",
    "user3": "COMPANY_XYZ78",

}  

# Rate limiting
limitOfMessages = 5  # Maximum number of messages per interval
rateLimSec = 20  # Time in seconds



async def handler(websocket):
    username = None  # To prevent errors if user disconnects early
    try:
        username = await websocket.recv()
        password = await websocket.recv()

        if username in stored_users and password == stored_users[username]:
            connected_users[username] = websocket
            print(f"{username} has connected.")

            # Send updated user list to all clients
            await broadcast_users_list()

            await websocket.send("Authentication successful. You can start chatting.")

            async for message in websocket:
                if message == "disconnecting":
                    print(f"{username} has disconnected.")
                    break

                if message.startswith("@"):  # Private message format: @user message
                    parts = message.split(" ", 1)
                    if len(parts) > 1:
                        target_user = parts[0][1:]  # Remove '@' from username
                        msg_content = parts[1]

                        if target_user in connected_users:
                            try:
                                await connected_users[target_user].send(f"{username}: {msg_content}")
                            except websockets.exceptions.ConnectionClosed:
                                del connected_users[target_user]  # Remove disconnected user
                    else:
                        await websocket.send("Invalid message format. Use @username message")
                else:
                    await websocket.send("To send a message, use @recipient_username message_content.")

        else:
            await websocket.send("Authentication failed. Invalid username or password.")
            await websocket.close()

    except websockets.exceptions.ConnectionClosed:
        print(f"{username} has disconnected.")
    finally:
        if username and username in connected_users:
            del connected_users[username]
            await broadcast_users_list()


async def broadcast_users_list():
    """Sends an updated list of connected users to all clients."""
    user_list = ",".join(connected_users.keys())  # Convert list to comma-separated string
    for user in connected_users.values():
        await user.send(f"USERS:{user_list}")



async def tellClients(message):
    # Sends a message to all clients notifying them what occurred.
    for user, conn in connected_users.items():
        try:
            await conn["websocket"].send(message)
        except websockets.exceptions.ConnectionClosed:
            continue  # Clients no longer connected are ignored.


async def shutServer(server):
    print("Shutting down server...")

    # Notify all clients about shutdown
    tasks = [conn["websocket"].send("Server is shutting down...") for conn in list(connected_users.values())]
    await asyncio.gather(*tasks, return_exceptions=True)  # Send shutdown message to all users

    # Close all connections concurrently
    tasks = [conn["websocket"].close() for conn in list(connected_users.values())]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Clear the dictionary AFTER iteration
    connected_users.clear()

    # Close the WebSocket server
    server.close()
    await server.wait_closed()
    
    print("Server successfully shut down.")

    # Stop the event loop safely
    try:
        loop = asyncio.get_running_loop()
        loop.stop()
    except RuntimeError:
        pass  


async def main():
    print("Starting WebSocket server on ws://localhost:9000")

    async def handler_wrapper(*args):
        return await handler(args[0])

    server = await websockets.serve(handler_wrapper, "localhost", 9000)

    stop_event = asyncio.Event()

    def shutDown(signal_received, frame):
        print("Received shutdown signal...")
        stop_event.set()  
        asyncio.create_task(shutServer(server))  

    signal.signal(signal.SIGINT, shutDown)  

    await stop_event.wait()  


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down...")