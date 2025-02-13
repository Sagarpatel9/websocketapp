import asyncio
import websockets
import time
import signal
import sys

connected_users = {}

# Rate limiting
limitOfMessages = 5  # Maximum number of messages per interval
rateLimSec = 20  # Time in seconds

async def handler(websocket):
    username = None  # Initialize to avoid NameError
    try:
        username = await websocket.recv()
        password = await websocket.recv()

        if username in ["user1", "user2"] and password == "password":
            connected_users[username] = {
                "websocket": websocket,
                "messages": [],  # List of message timestamps
            }

            print(f"{username} has been connected.")
            await websocket.send("Authentication successful. You can start chatting.")
            
            # Tell the other clients that a user has successfully connected.
            await tellClients(f"{username} has been connected.")

            async for message in websocket:

                if message == "disconnecting":
                    print(f"{username} has disconnected.")
                    await tellClients(f"{username} has disconnected.")
                    break 
                
                # Ignore heartbeat messages silently
                if message == "heartbeat":
                    continue

                # Rate limiting
                currentTime = time.time()
                userInfo = connected_users[username]

                # Remove messages older than 'rateLimSec'
                userInfo["messages"] = [
                    messageTime for messageTime in userInfo["messages"] if currentTime - messageTime < rateLimSec
                ]

                if len(userInfo["messages"]) >= limitOfMessages:
                    await websocket.send("You have exceeded the rate limit. Please stop spamming!")
                    continue

                # Save the message timestamp
                userInfo["messages"].append(currentTime)

                print(f"{username}: {message}")

                # Broadcast message to all connected users
                disconnected_users = []
                for user, conn in connected_users.items():
                    if user != username:  # Don't send the message back to the sender
                        try:
                            await conn["websocket"].send(f"{username}: {message}")
                        except websockets.exceptions.ConnectionClosed:
                            disconnected_users.append(user)

                # Remove disconnected users
                for user in disconnected_users:
                    del connected_users[user]

        else:
            await websocket.send("Authentication failed.")
            await websocket.close()

    except websockets.exceptions.ConnectionClosed:
        print(f"We have detected that {username} has disconnected.")
        await tellClients(f"{username} has unfortunately disconnected.")  # Tell all clients that a user has disconnected.
    finally:
        if username and username in connected_users:
            del connected_users[username]

async def tellClients(message):
    # Sends a message to all clients notifying them what occurred.
    for user, conn in connected_users.items():
        try:
            await conn["websocket"].send(message)
        except websockets.exceptions.ConnectionClosed:
            continue  # Clients no longer connected are ignored.

async def main():
    print("Starting WebSocket server on ws://localhost:9000")
    
    async def handler_wrapper(*args):
        return await handler(args[0])

    server = await websockets.serve(handler_wrapper, "localhost", 9000)

    def shutDown(signal, frame):
        print("Server shutting down...")
        asyncio.create_task(shutServer(server))

    signal.signal(signal.SIGINT, shutDown)

    await asyncio.Future()  # Keeps the server running indefinitely

async def shutServer(server):
    # Tells all users that server is shutting down.
    await tellClients("Server is unfortunately down right now.")
    server.close()
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down...")