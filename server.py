import asyncio
import websockets
import time

connected_users = {}

# Rate limiting 
limitOfMessages = 5  # Maximum number of messages per interval
rateLimSec = 20  # Time in seconds
beatSec = 15  #Users are checked for active status every 15 sec

async def handler(websocket):
    username = None  # Initialize to avoid NameError
    try:
        username = await websocket.recv()
        password = await websocket.recv()

        if username in ["user1", "user2"] and password == "password":
            connected_users[username] = {
                "websocket" : websocket,
                "messages" : [],  #lists the times of messages
                "prevBeat" : time.time(),  #stores the previous beat
            }

            print(f"{username} connected.")
            await websocket.send("Authentication successful. You can start chatting.")

            async for message in websocket:
                #Change time if there's a beat signal.
                if message == "heartbeat":
                    connected_users[username]["prevBeat"] = time.time()
                    continue

                # Rate limiting
                currentTime = time.time()
                userInfo = connected_users[username]

                # Remove messages that are older than rateLimSec
                userInfo["messages"] = [
                    messageTime for messageTime in userInfo["messages"] if currentTime - messageTime < rateLimSec
                ]

                if len(userInfo["messages"]) >= limitOfMessages:
                    await websocket.send("You have gone past the rate limit. Please stop spamming!")
                    continue

                # Save the message time
                userInfo["messages"].append(currentTime)

                print(f"{username}: {message}")

                # Broadcast message to all connected users
                disconnected_users = []
                for user, conn in connected_users.items():
                    if conn != websocket:
                        try:
                            await conn["websocket"].send(f"{username}: {message}")
                        except websockets.exceptions.ConnectionClosed:
                            disconnected_users.append(user)

                for user in disconnected_users:
                    del connected_users[user]

        else:
            await websocket.send("Authentication failed.")
            await websocket.close()

    except websockets.exceptions.ConnectionClosed:
        if username:
            print(f"{username} disconnected.")
        else:
            print("A connection closed before authentication.")
    finally:
        if username and username in connected_users:
            del connected_users[username]

async def beatAnalyze():
    #Users that don't send beats are removed after a period of time.
    while True:
        await asyncio.sleep(beatSec)
        presentTime = time.time()
        removedUsers = {
            user for user, conn in connected_users.items()
            if presentTime - conn["prevBeat"] > beatSec + 8
        }

        for user in removedUsers:
            print(f"{user} is no longer connected because our system detects that you're not active.")
            del connected_users[user]


async def main():
    print("Starting WebSocket server on ws://localhost:9000")

    # Define a wrapper that accepts any number of arguments.
    async def handler_wrapper(*args):
        # We assume the websocket is always the first argument.
        return await handler(args[0])

    server = await websockets.serve(handler_wrapper, "localhost", 9000)

    #Create the task to keep track of beats
    asyncio.create_task(beatAnalyze())

    await asyncio.Future()  # Keeps the server running indefinitely

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down...")